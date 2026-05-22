"""Admin API — WebSocket endpoint for the Ark-DuckBot-Desktop companion app.

The desktop app connects via WebSocket on a separate port (8444) using
admin authentication (shared secret + admin tier). This provides:
- Server status, player list, tribe info
- Command submission (broadcast, config, shutdown)
- Real-time event stream
- Session/query access without going through the game plugin

Protocol:
1. Client connects and sends auth message with admin token
2. Server responds with auth_success + server info
3. Client sends command messages; server responds with results
4. Bidirectional events (player_join, player_leave, dino_events) pushed to client

arkduckbot:// protocol: clients launch with arkduckbot://SERVER:PORT which
opens the connection URL in the desktop app. The bridge parses this to
auto-connect.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.asyncio.server import serve, ServerConnection

from sheldon_bridge.auth import TokenAuthenticator
from sheldon_bridge.config import BridgeConfig
from sheldon_bridge.duckbot_handler import get_command_queue

logger = logging.getLogger(__name__)


@dataclass
class AdminSession:
    """An active desktop admin connection."""
    id: str
    websocket: ServerConnection
    connected_at: float = field(default_factory=time.time)
    subscription: str = "all"  # "all", "events", "players", "commands"
    authorized: bool = False


class AdminServer:
    """Separate WebSocket server for the desktop companion app.

    Runs on port 8444 (configurable) to separate admin traffic from
    game plugin traffic on 8443.

    Features:
    - Admin auth via shared secret
    - Server status (players, dinos, uptime, map)
    - Player/tribe info queries
    - Command submission (broadcast, config, shutdown)
    - Real-time event stream (player_join/leave, dino_events)
    - Health/readiness endpoints
    """

    def __init__(self, config: BridgeConfig, game_server_ref):
        """
        Args:
            config: BridgeConfig with shared_secret, admin_port, etc.
            game_server_ref: Reference to BridgeServer for querying state.
        """
        self.config = config
        self.authenticator = TokenAuthenticator(config.shared_secret)
        self._game = game_server_ref  # BridgeServer instance
        self._port = getattr(config, "admin_port", 8444)

        # Connected admin sessions
        self._sessions: dict[str, AdminSession] = {}
        self._running = False

    async def start(self) -> None:
        """Start the admin WebSocket server."""
        self._running = True
        server = serve(
            self._handle_connection,
            "0.0.0.0",
            self._port,
            ping_interval=20,
            ping_timeout=10,
        )
        asyncio.create_task(server)
        logger.info(f"Admin API WebSocket server started on port {self._port}")

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        """Handle a single desktop app connection."""
        session_id = None
        try:
            # Auth message required first
            raw = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            auth_msg = json.loads(raw)

            if auth_msg.get("type") != "admin_auth":
                await websocket.close(4001, "First message must be admin_auth")
                return

            token = auth_msg.get("token", "")
            if not self.authenticator.validate_token(token):
                logger.warning(f"Admin auth failed from {websocket.remote_address}")
                await websocket.close(4001, "Authentication failed")
                return

            session_id = auth_msg.get("session_id") or f"admin-{int(time.time())}"
            session = AdminSession(id=session_id, websocket=websocket, authorized=True)
            self._sessions[session_id] = session

            # Send server info snapshot
            server_info = await self._get_server_info()
            await websocket.send(json.dumps({
                "type": "auth_success",
                "session_id": session_id,
                "server": server_info,
                "capabilities": [
                    "server_status", "player_list", "tribe_info", "command_submit",
                    "event_stream", "config_get", "config_set", "broadcast",
                    "ai_chat", "skill_list", "skill_trigger", "world_stats",
                    "llm_stats", "session_recall",
                ],
            }))

            logger.info(f"Admin desktop connected: {session_id} from {websocket.remote_address}")

            # Message loop
            async for raw_message in websocket:
                try:
                    msg = json.loads(raw_message)
                    await self._handle_message(msg, session)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "type": "error", "error": "Invalid JSON"
                    }))
                except Exception as e:
                    logger.error(f"Admin message error for {session_id}: {e}")
                    await websocket.send(json.dumps({
                        "type": "error", "error": str(e)
                    }))

        except asyncio.TimeoutError:
            logger.warning(f"Admin auth timeout from {websocket.remote_address}")
            await websocket.close(4002, "Auth timeout")
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"Admin connection error: {e}")
        finally:
            if session_id:
                self._sessions.pop(session_id, None)

    async def _handle_message(self, msg: dict, session: AdminSession) -> None:
        """Route an admin command message."""
        cmd = msg.get("cmd")

        if cmd == "ping":
            await session.websocket.send(json.dumps({"type": "pong", "time": time.time()}))
            return

        if cmd == "subscribe":
            # Subscribe to event categories: all, events, players, commands
            session.subscription = msg.get("category", "all")
            await session.websocket.send(json.dumps({
                "type": "subscribed", "category": session.subscription
            }))
            return

        if cmd == "server_status":
            status = await self._get_server_info()
            await session.websocket.send(json.dumps({"type": "server_status", "data": status}))
            return

        if cmd == "player_list":
            players = self._get_connected_players()
            await session.websocket.send(json.dumps({"type": "player_list", "data": players}))
            return

        if cmd == "player_info":
            player_id = msg.get("player_id", "")
            info = await self._get_player_info(player_id)
            await session.websocket.send(json.dumps({"type": "player_info", "data": info}))
            return

        if cmd == "tribe_info":
            tribe_id = msg.get("tribe_id", "")
            info = await self._get_tribe_info(tribe_id)
            await session.websocket.send(json.dumps({"type": "tribe_info", "data": info}))
            return

        if cmd == "command_submit":
            # Admin submits a command to be executed via the game handler
            command = msg.get("command", {})
            result = await self._submit_command(command)
            await session.websocket.send(json.dumps({"type": "command_result", "data": result}))
            return

        if cmd == "broadcast":
            message = msg.get("message", "")
            if message:
                from sheldon_bridge.duckbot_handler import get_command_queue
                queue = get_command_queue()
                cmd_obj = QueuedCommand(
                    action="console_command",
                    command=f"broadcast {message}",
                    payload={"source": "admin_desktop", "admin": session.id},
                )
                await queue.enqueue(cmd_obj)
                await session.websocket.send(json.dumps({
                    "type": "broadcast_queued", "message": message
                }))
            return

        if cmd == "config_get":
            key = msg.get("key", "")
            value = self._get_config(key)
            await session.websocket.send(json.dumps({
                "type": "config_value", "key": key, "value": value
            }))
            return

        if cmd == "event_history":
            # Return recent events from the session manager
            events = await self._get_recent_events(msg.get("limit", 50))
            await session.websocket.send(json.dumps({
                "type": "event_history", "events": events
            }))
            return

        if cmd == "kill_session":
            # Kill a player session (kick player)
            player_id = msg.get("player_id", "")
            await self._kill_session(player_id)
            await session.websocket.send(json.dumps({
                "type": "session_killed", "player_id": player_id
            }))
            return

        if cmd == "ai_chat":
            # Free-form AI chat from desktop admin (bypasses game mod)
            query = msg.get("query", "")
            stream = msg.get("stream", False)
            if query:
                if stream:
                    # Streaming AI chat — send tokens as they arrive
                    await self._ai_chat_stream(session, query)
                else:
                    result = await self._ai_chat(query)
                    await session.websocket.send(json.dumps({
                        "type": "ai_chat_result", "query": query, "result": result
                    }))
            return

        if cmd == "ai_tool_execute":
            # Execute a specific tool via AI intent (desktop app can request tool execution)
            tool_name = msg.get("tool", "")
            args = msg.get("args", {})
            if tool_name:
                result = await self._ai_tool_execute(tool_name, args)
                await session.websocket.send(json.dumps({
                    "type": "ai_tool_result", "tool": tool_name, "result": result
                }))
            return

        if cmd == "ai_intent":
            # Classify intent of a message without executing (for UI hints)
            text = msg.get("text", "")
            if text:
                from sheldon_bridge.intent import IntentClassifier, IntentType
                classifier = IntentClassifier()
                result = classifier.classify(text)
                await session.websocket.send(json.dumps({
                    "type": "ai_intent_result",
                    "text": text,
                    "intent": result.intent_type.value,
                    "confidence": result.confidence,
                    "entities": result.entities,
                    "reasoning": result.reasoning,
                }))
            return

        if cmd == "memory_search":
            # Search cross-session memory with scoring
            query = msg.get("query", "")
            limit = msg.get("limit", 5)
            if query:
                from sheldon_bridge.skills.improver import CrossSessionMemory
                memory = CrossSessionMemory()
                results = memory.search(query, limit=limit)
                await session.websocket.send(json.dumps({
                    "type": "memory_search_result", "query": query,
                    "matches": [
                        {
                            "key": r.key,
                            "content": r.content,
                            "access_count": r.access_count,
                            "tags": r.tags,
                        }
                        for r in results
                    ]
                }))
            return

        if cmd == "skill_list":
            # List all available skills and their auto-triggers
            from sheldon_bridge.skills.registry import get_skill_registry
            registry = get_skill_registry()
            skills = []
            for skill in registry._skills.values():
                skills.append({
                    "name": skill.meta.name,
                    "description": skill.meta.description,
                    "auto_triggers": skill.meta.auto_trigger_on or [],
                    "tier": skill.meta.tier,
                })
            await session.websocket.send(json.dumps({
                "type": "skill_list", "skills": skills
            }))
            return

        if cmd == "skill_trigger":
            # Manually trigger a skill by name
            skill_name = msg.get("skill_name", "")
            context = msg.get("context", {})
            result = await self._trigger_skill(skill_name, context)
            await session.websocket.send(json.dumps({
                "type": "skill_trigger_result", "skill": skill_name, "result": result
            }))
            return

        if cmd == "world_stats":
            # Live world state: tracked players, tribe bases, spatial data
            from sheldon_bridge.world_context import get_world_context
            ctx = get_world_context()
            stats = await ctx.get_stats()
            await session.websocket.send(json.dumps({
                "type": "world_stats", "data": stats
            }))
            return

        if cmd == "llm_stats":
            # Detailed LLM usage stats
            from sheldon_bridge.metrics import get_metrics
            metrics = get_metrics()
            health = metrics.get_health()
            await session.websocket.send(json.dumps({
                "type": "llm_stats",
                "data": {
                    "total_requests": health.get("llm", {}).get("total_requests", 0),
                    "total_cost_usd": health.get("llm", {}).get("total_cost_usd", 0),
                    "total_input_tokens": health.get("llm", {}).get("total_input_tokens", 0),
                    "total_output_tokens": health.get("llm", {}).get("total_output_tokens", 0),
                    "top_players": health.get("top_players", []),
                }
            }))
            return

        if cmd == "session_recall":
            # Search cross-session memory
            query = msg.get("query", "")
            if query:
                from sheldon_bridge.skills.improver import CrossSessionMemory
                memory = CrossSessionMemory()
                results = memory.search(query, limit=5)
                await session.websocket.send(json.dumps({
                    "type": "session_recall", "query": query,
                    "matches": [
                        {"key": r.key, "content": r.content, "access_count": r.access_count}
                        for r in results
                    ]
                }))
            return

        if cmd == "subscribe_world":
            # Subscribe to real-time world state push events
            session.subscription = "world"
            await session.websocket.send(json.dumps({
                "type": "subscribed", "category": "world"
            }))
            return

        await session.websocket.send(json.dumps({
            "type": "error", "error": f"Unknown command: {cmd}"
        }))

    async def _get_server_info(self) -> dict[str, Any]:
        """Get server status snapshot."""
        from sheldon_bridge.metrics import get_metrics
        metrics = get_metrics()
        health = metrics.get_health()

        return {
            "server_name": self.config.ark.get("map", "Unknown"),
            "uptime_seconds": health.get("bridge", {}).get("uptime_seconds", 0),
            "plugin_connected": health.get("bridge", {}).get("plugin_connected", False),
            "active_players": health.get("bridge", {}).get("active_players", 0),
            "total_players_seen": health.get("bridge", {}).get("total_players_seen", 0),
            "llm_requests": health.get("llm", {}).get("total_requests", 0),
            "llm_cost_usd": health.get("llm", {}).get("total_cost_usd", 0),
            "top_players": health.get("top_players", []),
        }

    def _get_connected_players(self) -> list[dict[str, Any]]:
        """Get list of connected players from BridgeServer sessions."""
        players = []
        if self._game and hasattr(self._game, "sessions"):
            for player_id, session in self._game.sessions._sessions.items():
                p = session.player
                players.append({
                    "player_id": p.player_id,
                    "display_name": p.display_name,
                    "tier": p.tier,
                    "tribe_id": p.tribe_id or "",
                    "position": p.position,
                })
        return players

    async def _get_player_info(self, player_id: str) -> dict[str, Any]:
        """Get detailed player info."""
        if self._game and hasattr(self._game, "sessions"):
            session = self._game.sessions._sessions.get(player_id)
            if session:
                p = session.player
                return {
                    "player_id": p.player_id,
                    "display_name": p.display_name,
                    "tier": p.tier,
                    "tribe_id": p.tribe_id or "",
                    "position": p.position,
                    "online": True,
                }

        from sheldon_bridge.metrics import get_metrics
        summary = get_metrics().get_player_summary(player_id)
        if summary:
            summary["online"] = False
            return summary
        return {"error": "Player not found"}

    async def _get_tribe_info(self, tribe_id: str) -> dict[str, Any]:
        """Get tribe info from DuckBotSession context."""
        if not tribe_id:
            return {"error": "No tribe_id provided"}

        # Look in active sessions for tribe data
        if self._game and hasattr(self._game, "sessions"):
            for session in self._game.sessions._sessions.values():
                if hasattr(session, "_tribe_data") and session._tribe_data:
                    td = session._tribe_data
                    if str(td.get("tribe_id", "")) == str(tribe_id):
                        return td

        return {
            "tribe_id": tribe_id,
            "name": "Unknown",
            "online_members": [],
            "dino_count": 0,
        }

    async def _submit_command(self, command: dict) -> dict[str, Any]:
        """Submit a game command via DuckBotHandler."""
        from sheldon_bridge.duckbot_handler import get_command_queue, DuckBotHandler

        handler = DuckBotHandler()
        return await handler(command)

    async def _kill_session(self, player_id: str) -> None:
        """Remove a player's session (kick them)."""
        if self._game and hasattr(self._game, "sessions"):
            self._game.sessions.remove(player_id)

    async def _ai_chat(self, query: str) -> dict[str, Any]:
        """Run a free-form AI query from the desktop admin.

        Creates a minimal session context and runs the agent so admins
        can ask AI questions without being in-game. Useful for server
        management, config help, skill creation, etc.
        """
        if not self._game:
            return {"error": "Game server not connected"}

        from sheldon_bridge.agent import Agent

        # Create a minimal admin session context
        class AdminPlayer:
            player_id = "admin-desktop"
            display_name = "Admin"
            tier = "superadmin"
            tribe_id = ""
            position = {}
            facing_yaw = 0.0

        class AdminSessionCtx:
            """Lightweight session for admin AI queries — no persistence."""
            player = AdminPlayer()
            conversation = [
                {
                    "role": "system",
                    "content": (
                        "You are Sheldon, an AI assistant for an ARK: Survival Ascended "
                        "server running on DuckBot. You help server admins manage the "
                        "server, answer questions about game mechanics, and can execute "
                        "admin commands. Be concise and helpful."
                    ),
                },
                {"role": "user", "content": query},
            ]
            system_prompt = ""
            total_input_tokens = 0
            total_output_tokens = 0
            total_cost = 0.0
            created_at = 0.0
            last_active = 0.0
            lock = asyncio.Lock()

            def get_messages(self):
                return self.conversation

            def track_usage(self, i, o, c):
                self.total_input_tokens += i
                self.total_output_tokens += o
                self.total_cost += c

            def add_assistant_message(self, msg):
                self.conversation.append(msg)

        session_ctx = AdminSessionCtx()
        agent = Agent(
            llm=self._game.llm,
            registry=self._game.registry,
            rate_limiter=self._game.rate_limiter,
        )

        try:
            result = await agent.run(session_ctx, query)
            return {
                "response": result.response_text,
                "stats": {
                    "iterations": result.iterations,
                    "tool_calls": result.tool_calls_made,
                    "cost": round(result.total_cost, 6),
                    "duration_ms": round(result.duration_ms, 1),
                }
            }
        except Exception as e:
            logger.error(f"Admin AI chat failed: {e}", exc_info=True)
            return {"error": str(e)}

    async def _ai_chat_stream(self, session: AdminSession, query: str) -> None:
        """Streaming AI chat — sends tokens in-flight to the desktop app.

        Uses run_streaming() to provide real-time typewriter effect.
        Tokens are sent as stream_token messages, followed by ai_chat_result.
        """
        if not self._game:
            await session.websocket.send(json.dumps({
                "type": "error", "error": "Game server not connected"
            }))
            return

        from sheldon_bridge.agent import Agent

        class AdminPlayer:
            player_id = "admin-desktop"
            display_name = "Admin"
            tier = "superadmin"
            tribe_id = ""
            position = {}
            facing_yaw = 0.0

        class AdminSessionCtx:
            player = AdminPlayer()
            conversation = [
                {"role": "system", "content": (
                    "You are Sheldon, an AI assistant for an ARK: Survival Ascended "
                    "server running on DuckBot. You help server admins manage the "
                    "server, answer questions about game mechanics, and can execute "
                    "admin commands. Be concise and helpful."
                )},
                {"role": "user", "content": query},
            ]
            system_prompt = ""
            total_input_tokens = 0
            total_output_tokens = 0
            total_cost = 0.0
            created_at = 0.0
            last_active = 0.0
            lock = asyncio.Lock()

            def get_messages(self):
                return self.conversation

            def track_usage(self, i, o, c):
                self.total_input_tokens += i
                self.total_output_tokens += o
                self.total_cost += c

            def add_assistant_message(self, msg):
                self.conversation.append(msg)

        session_ctx = AdminSessionCtx()
        agent = Agent(
            llm=self._game.llm,
            registry=self._game.registry,
            rate_limiter=self._game.rate_limiter,
        )

        async def stream_send(msg: dict) -> None:
            msg["type"] = "stream_token"
            await session.websocket.send(json.dumps(msg))

        try:
            result = await agent.run_streaming(session_ctx, query, stream_send)
            await session.websocket.send(json.dumps({
                "type": "ai_chat_result",
                "query": query,
                "result": {
                    "response": result.response_text,
                    "stats": {
                        "iterations": result.iterations,
                        "tool_calls": result.tool_calls_made,
                        "cost": round(result.total_cost, 6),
                        "duration_ms": round(result.duration_ms, 1),
                    },
                },
            }))
        except Exception as e:
            logger.error(f"Admin AI chat streaming failed: {e}", exc_info=True)
            await session.websocket.send(json.dumps({
                "type": "error", "error": str(e)
            }))

    async def _ai_tool_execute(self, tool_name: str, args: dict) -> dict[str, Any]:
        """Execute a specific tool directly (for structured admin commands).

        Use this when the desktop app knows exactly which tool to call
        rather than going through AI intent routing.
        """
        if not self._game:
            return {"error": "Game server not connected"}

        registry = self._game.registry
        tool_def = registry._tools.get(tool_name)

        if not tool_def:
            return {"error": f"Tool '{tool_name}' not found"}

        # Verify tool is available to admin tier
        if tool_def.tier not in ("admin", "superadmin"):
            return {"error": f"Tool '{tool_name}' requires {tool_def.tier} tier, not admin"}

        try:
            result = await tool_def.function(**args)
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"Admin tool execution '{tool_name}' failed: {e}")
            return {"success": False, "error": str(e)}

    async def _trigger_skill(self, skill_name: str, context: dict) -> dict[str, Any]:
        """Manually trigger a named skill with given context."""
        from sheldon_bridge.skills.registry import get_skill_registry
        registry = get_skill_registry()

        skill = registry._skills.get(skill_name)
        if not skill:
            return {"error": f"Skill '{skill_name}' not found"}

        try:
            ctx = {
                "game_handler": None,
                "player": context.get("player"),
                "tribe_data": context.get("tribe_data", {}),
                "event_data": context.get("event_data", {}),
            }
            result = await skill.execute(ctx)
            return {"message": result.message, "success": True}
        except Exception as e:
            return {"error": str(e), "success": False}

    async def _get_recent_events(self, limit: int = 50) -> list[dict]:
        """Get recent game events from DuckBotSessions."""
        events = []
        if self._game and hasattr(self._game, "sessions"):
            for session in self._game.sessions._sessions.values():
                if hasattr(session, "_events"):
                    for evt in session._events[-limit:]:
                        events.append(evt.to_dict())
        return events[-limit:]

    def _get_config(self, key: str) -> Any:
        """Get a config value by key."""
        if not key:
            return dict(self.config.ark)
        # Navigate nested keys: "ark.map", "llm.provider"
        parts = key.split(".")
        val = self.config.ark
        for part in parts:
            if isinstance(val, dict):
                val = val.get(part)
            else:
                return None
        return val

    async def broadcast_to_all(self, msg_type: str, data: dict) -> None:
        """Push an event to all connected admin sessions.

        Called by BridgeServer when game events occur so the desktop app
        receives real-time updates.
        """
        for session in list(self._sessions.values()):
            if session.authorized:
                try:
                    await session.websocket.send(json.dumps({
                        "type": msg_type,
                        "data": data,
                        "timestamp": time.time(),
                    }))
                except Exception:
                    pass


# Global admin server instance
_admin_server: AdminServer | None = None


def get_admin_server() -> AdminServer | None:
    return _admin_server


def start_admin_server(config: BridgeConfig, game_server) -> AdminServer:
    """Start the admin API server."""
    global _admin_server
    _admin_server = AdminServer(config, game_server)
    asyncio.create_task(_admin_server.start())
    return _admin_server