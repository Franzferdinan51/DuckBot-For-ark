"""WebSocket server — accepts connections from the game mod and mock clients.

This is the main entry point for the bridge. It:
1. Accepts WebSocket connections
2. Authenticates via shared token
3. Creates a session per player
4. Routes messages to the agent
5. Sends responses back
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal

import websockets
from websockets.asyncio.server import serve, ServerConnection
from aiohttp import web

from sheldon_bridge.agent import Agent
from sheldon_bridge.auth import PlayerContext, RateLimiter, TokenAuthenticator
from sheldon_bridge.config import BridgeConfig
from sheldon_bridge.providers.llm import LLMProvider
from sheldon_bridge.session import SessionManager
from sheldon_bridge.tools.registry import ToolRegistry

# Import tool modules to trigger @tool registration
import sheldon_bridge.tools.knowledge  # noqa: F401
import sheldon_bridge.tools.actions  # noqa: F401
import sheldon_bridge.skills.tools  # noqa: F401
from sheldon_bridge.skills.registry import get_skill_registry

# Discover and register skills at startup
_skills = get_skill_registry()
_skills.discover()

# Discover skill bundles (hermes-agent pattern — group multiple skills under one trigger)
from sheldon_bridge.skills.bundles import get_bundle_registry
_bundles = get_bundle_registry()
_bundles.discover()

logger = logging.getLogger(__name__)


class BridgeServer:
    """The main Sheldon Bridge server."""

    def __init__(self, config: BridgeConfig):
        self.config = config

        # Auth
        self.authenticator = TokenAuthenticator(config.shared_secret)

        # LLM
        self.llm = LLMProvider(config.llm)

        # Tools
        self.registry = ToolRegistry(tier_config=config.tiers or None)
        self.registry.discover()

        # Sessions & rate limiting
        self.sessions = SessionManager()
        self.rate_limiter = RateLimiter()

        # World context for spatial awareness
        from sheldon_bridge.world_context import get_world_context
        self.world = get_world_context()

        # Agent
        self.agent = Agent(
            llm=self.llm,
            registry=self.registry,
            rate_limiter=self.rate_limiter,
        )

        # Track connected clients
        self._connections: dict[str, ServerConnection] = {}

        logger.info(
            f"Bridge initialized: {len(self.registry.all_tools)} tools, "
            f"tiers={self.registry.tier_names}, "
            f"model={config.llm.litellm_model}"
        )

    async def handle_connection(self, websocket: ServerConnection) -> None:
        """Handle a single WebSocket connection from the game mod or mock client."""
        player_id = None
        try:
            # Step 1: Authenticate
            raw = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            auth_msg = json.loads(raw)

            if auth_msg.get("type") != "auth":
                await websocket.close(4001, "First message must be auth")
                return

            token = auth_msg.get("token", "")
            if not self.authenticator.validate_token(token):
                logger.warning(f"Auth failed from {websocket.remote_address}")
                await websocket.close(4001, "Authentication failed")
                return

            # Step 2: Create session
            player_data = auth_msg.get("player", {})
            player = PlayerContext(
                player_id=player_data.get("player_id", "unknown"),
                display_name=player_data.get("display_name", "Unknown"),
                tier=player_data.get("tier", "player"),
                tribe_id=player_data.get("tribe_id", ""),
                position=player_data.get("position", {}),
                facing_yaw=player_data.get("facing_yaw", 0.0),
            )
            player_id = player.player_id

            # Track player in world context immediately on connect
            if player.position:
                await self.world.update_player(
                    player.player_id,
                    display_name=player.display_name,
                    tribe_id=player.tribe_id,
                    position=player.position,
                    facing_yaw=player.facing_yaw,
                )

            # Build system prompt
            system_prompt = self.config.build_system_prompt(
                player_name=player.display_name,
                tier=player.tier,
                tribe=player.tribe_id,
            )

            session = self.sessions.create_duckbot(
                player,
                system_prompt=system_prompt,
                max_events=50,
            )
            self._connections[player_id] = websocket

            # Send auth success
            await websocket.send(json.dumps({
                "type": "auth_success",
                "player_id": player_id,
                "tier": player.tier,
                "tools_available": len(self.registry.get_tools_for_tier(player.tier)),
            }))

            logger.info(
                f"Player connected: {player.display_name} ({player_id[:8]}...) "
                f"tier={player.tier}"
            )

            # Step 3: Message loop
            async for raw_message in websocket:
                try:
                    msg = json.loads(raw_message)
                    await self._handle_message(msg, session, websocket)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid JSON",
                    }))
                except Exception as e:
                    logger.error(f"Error handling message for {player_id}: {e}", exc_info=True)
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Internal error processing your request",
                    }))

        except asyncio.TimeoutError:
            logger.warning(f"Auth timeout from {websocket.remote_address}")
            await websocket.close(4002, "Auth timeout")
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"Connection error: {e}", exc_info=True)
        finally:
            if player_id:
                self._connections.pop(player_id, None)
                await self.sessions.remove(player_id)
                await self.world.remove_player(player_id)

    async def _handle_message(
        self, msg: dict, session, websocket: ServerConnection
    ) -> None:
        """Route an incoming message to the appropriate handler."""
        msg_type = msg.get("type")

        if msg_type == "player_message":
            await self._handle_player_message(msg, session, websocket)

        elif msg_type == "position_update":
            # Update player position (sent periodically by the mod)
            pos = msg.get("position", {})
            session.player.update_position(pos, msg.get("facing_yaw", 0.0))
            # Keep world context in sync for spatial queries
            await self.world.update_player(
                session.player.player_id,
                display_name=session.player.display_name,
                tribe_id=session.player.tribe_id,
                position=pos,
                facing_yaw=msg.get("facing_yaw", 0.0),
            )

        elif msg_type == "tool_response":
            # Game mod responding to a tool request (future use)
            pass

        elif msg_type == "event":
            # Game event broadcast from DuckBot C++ plugin
            # e.g. dino_tamed, baby_born, dino_died, player_connected, player_disconnected, level_up
            await self._handle_game_event(msg, session, websocket)

        elif msg_type == "ping":
            await websocket.send(json.dumps({"type": "pong"}))

        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def _handle_player_message(
        self, msg: dict, session, websocket: ServerConnection
    ) -> None:
        """Handle a player chat message — run the agentic loop."""
        text = msg.get("message", "").strip()
        if not text:
            return

        # Update position if included in the message
        pos = msg.get("position")
        if pos:
            session.player.update_position(pos, msg.get("facing_yaw", 0.0))
            await self.world.update_player(
                session.player.player_id,
                display_name=session.player.display_name,
                tribe_id=session.player.tribe_id,
                position=pos,
                facing_yaw=msg.get("facing_yaw", 0.0),
            )

        # Echo request_id from client (for server-side request tracking)
        request_id = msg.get("request_id")

        # Send "thinking" indicator
        thinking_msg = {"type": "thinking"}
        if request_id is not None:
            thinking_msg["request_id"] = request_id
        await websocket.send(json.dumps(thinking_msg))

        # Wrapper to tag stream tokens with request_id for routing
        async def stream_send(msg: dict) -> None:
            if request_id is not None:
                msg["request_id"] = request_id
            await websocket.send(json.dumps(msg))

        # Run the agentic loop (prefer streaming for instant-feel responses)
        # Note: streaming sends tokens in-flight, no separate reply message sent
        try:
            result = await self.agent.run_streaming(session, text, stream_send)
        except Exception:
            # Fall back to regular non-streaming if streaming fails
            async with session.lock:
                result = await self.agent.run(session, text)
            # For non-streaming, send the final reply explicitly
            reply_msg = {
                "type": "reply",
                "message": result.response_text,
                "stats": {
                    "tool_calls": result.tool_calls_made,
                    "iterations": result.iterations,
                    "input_tokens": result.total_input_tokens,
                    "output_tokens": result.total_output_tokens,
                    "cost": round(result.total_cost, 6),
                    "duration_ms": round(result.duration_ms, 1),
                },
            }
            if request_id is not None:
                reply_msg["request_id"] = request_id
            await websocket.send(json.dumps(reply_msg))
            return

        # For streaming, stats are already reflected during token stream.
        # Log summary to bridge log only (not sent as a message to widget).
        logger.info(
            f"[{session.player.display_name}] "
            f"'{text[:50]}...' → "
            f"{result.iterations} iters, "
            f"{result.tool_calls_made} tools, "
            f"${result.total_cost:.4f}, "
            f"{result.duration_ms:.0f}ms"
        )

    async def _handle_game_event(
        self, msg: dict, session, websocket: ServerConnection
    ) -> None:
        """Handle game event messages from the DuckBot C++ plugin.

        Events are broadcast to the AI agent so it can maintain situational
        awareness (e.g. 'a Rex was tamed', 'player X disconnected',
        'a baby Giganotosaurus was born'). The agent decides whether to
        react — it doesn't auto-respond to every event.
        """
        event_data = msg.get("data", {})
        event_type = event_data.get("event", "unknown")

        logger.debug(f"Game event: {event_type} — {event_data}")

        # Build a notification for the agent's conversation context
        event_description = _format_game_event(event_type, event_data)
        if event_description:
            # Inject the event as a system-level observation into the session
            session.add_assistant_message({
                "role": "system",
                "content": f"[Game Event] {event_description}",
            })

        # Check for auto-triggered skills (openclaw-inspired)
        from sheldon_bridge.skills.registry import get_skill_registry
        registry = get_skill_registry()
        auto_skills = registry.get_for_event(event_type)
        for skill in auto_skills:
            logger.info(f"Auto-triggering skill '{skill.meta.name}' on event '{event_type}'")
            try:
                ctx = {
                    "game_handler": self._game_handler,
                    "player": session.player,
                    "tribe_data": getattr(session, "_tribe_data", {}),
                    "event_data": event_data,
                }
                result = await skill.execute(ctx)
                # Inject skill result as system observation
                session.add_assistant_message({
                    "role": "system",
                    "content": f"[Skill '{skill.meta.name}' triggered automatically] {result.message}",
                })
            except Exception as e:
                logger.error(f"Auto-trigger skill '{skill.meta.name}' failed: {e}")

    async def _cleanup_loop(self) -> None:
        """Periodically clean up expired sessions and rate limiter data."""
        while True:
            await asyncio.sleep(60)
            expired = await self.sessions.cleanup_expired()
            self.rate_limiter.cleanup()
            if expired:
                logger.info(f"Cleaned up {expired} expired sessions")


async def run_server(config: BridgeConfig) -> None:
    """Start the bridge server."""
    # Initialize SQLite session store and restore any persisted sessions
    from sheldon_bridge.session_persistence import init_session_store
    from sheldon_bridge.cache import init_cache

    store = await init_session_store()
    restored = await store.restore_all()
    for player_id, session in restored.items():
        logger.info(f"Restored session: {session.player.display_name} ({player_id[:8]}...)")

    # Initialize semantic cache for LLM response caching
    cache = await init_cache()
    logger.info(f"Semantic cache ready: {cache.stats().hit_rate:.1%} hit rate")

    server = BridgeServer(config)
    server.sessions.set_store(store)
    # Seed restored sessions into the session manager so they can be continued
    for player_id, session in restored.items():
        server.sessions._sessions[player_id] = session

    # Set up graceful shutdown
    stop = asyncio.get_event_loop().create_future()

    def handle_signal():
        if not stop.done():
            stop.set_result(None)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    # Start cleanup task
    cleanup_task = asyncio.create_task(server._cleanup_loop())

    # Start admin API server for desktop companion app
    from sheldon_bridge.admin_api import start_admin_server
    admin_server = start_admin_server(config, server)
    logger.info(f"Admin API for desktop app: ws://0.0.0.0:{getattr(config, 'admin_port', 8444)}")

    logger.info(
        f"Sheldon Bridge starting on "
        f"ws://{config.websocket_host}:{config.websocket_port}"
    )

    # Start REST admin API server for desktop companion app (HTTP on admin_port+1, e.g. 8445)
    from sheldon_bridge.rest_admin import create_rest_app
    rest_app = create_rest_app(config, server)
    rest_runner = web.AppRunner(rest_app)
    await rest_runner.setup()
    rest_site = web.TCPSite(rest_runner, config.websocket_host, config.admin_port + 1)
    await rest_site.start()
    logger.info(f"Admin REST API: http://{config.websocket_host}:{config.admin_port + 1}")

    async with serve(
        server.handle_connection,
        host=config.websocket_host,
        port=config.websocket_port,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=10,
        max_size=2**20,  # 1MB max message
    ) as ws_server:
        logger.info("Sheldon Bridge is running. Press Ctrl+C to stop.")
        await stop

    await rest_runner.cleanup()
    cleanup_task.cancel()
    logger.info("Sheldon Bridge stopped.")


def _format_game_event(event_type: str, data: dict) -> str | None:
    """Format a game event into a human-readable description for the AI."""

    descriptions = {
        "player_connected": f"Player '{data.get('name', '?')}' (Steam: {data.get('steam_id', '?')}) connected.",
        "player_disconnected": f"Player '{data.get('name', '?')}' (Steam: {data.get('steam_id', '?')}) disconnected.",
        "dino_tamed": f"A {data.get('species', '?')} (level {data.get('level', '?')}) was tamed by Steam {data.get('steam_id', '?')}.",
        "baby_born": f"A baby {data.get('species', '?')} (level {data.get('level', '?')}) was born! Mother: {data.get('mother', '?')}, Father: {data.get('father', '?')}.",
        "dino_died": f"A {data.get('species', '?')} (level {data.get('level', '?')}) died. Owner Steam: {data.get('steam_id', '?')}.",
        "player_level_up": f"Player '{data.get('name', '?')}' leveled up to level {data.get('level', '?')}.",
        "wild_dino_alert": f"Wild {data.get('species', '?')} (level {data.get('level', '?')}) detected near tribe base!",
    }

    return descriptions.get(event_type)
