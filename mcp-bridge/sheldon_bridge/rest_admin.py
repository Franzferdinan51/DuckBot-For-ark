"""REST admin endpoints for Ark-DuckBot-Desktop.

HTTP server on admin_port + 1 (e.g., 8445) for polling-style queries
that don't need WebSocket real-time. Desktop app can use these for
server status, player lists, config read/write without maintaining a
WebSocket connection.

Endpoints:
  GET  /health           — server health check
  GET  /status            — full server status (players, uptime, LLM stats)
  GET  /players           — list of all known players
  GET  /players/<id>      — player details
  GET  /events?limit=N    — recent game events
  POST /broadcast         — send broadcast (JSON body: {message: "..."})
  GET  /config/<key>      — get config value
  PUT  /config/<key>      — set config value (JSON body: {value: ...})

Auth: Bearer token in Authorization header (same shared_secret).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from aiohttp import web

from sheldon_bridge.auth import TokenAuthenticator
from sheldon_bridge.config import BridgeConfig

logger = logging.getLogger(__name__)


def create_rest_app(config: BridgeConfig, game_server_ref) -> web.Application:
    """Build the aiohttp REST application for admin endpoints."""
    authenticator = TokenAuthenticator(config.shared_secret)
    game = game_server_ref  # BridgeServer instance

    routes = web.RouteTableDef()

    # ─── Health ──────────────────────────────────────────────────────────

    @routes.get("/health")
    async def health(request: web.Request) -> web.Response:
        """Lightweight health check — can be polled frequently."""
        return web.json_response({
            "status": "ok",
            "time": time.time(),
            "port": config.admin_port,
        })

    # ─── Auth middleware ────────────────────────────────────────────────

    async def auth_middleware(request: web.Request) -> web.Response | None:
        """Validate bearer token. Returns None if valid, error response if not."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return web.json_response({"error": "Missing Authorization header"}, status=401)
        token = auth[7:]
        if not authenticator.validate_token(token):
            return web.json_response({"error": "Invalid token"}, status=401)
        return None

    # ─── Status ─────────────────────────────────────────────────────────

    @routes.get("/status")
    async def status(request: web.Request) -> web.Response:
        err = await auth_middleware(request)
        if err:
            return err

        from sheldon_bridge.metrics import get_metrics
        metrics = get_metrics()
        health = metrics.get_health()

        return web.json_response({
            "server_name": config.ark.get("map", "Unknown"),
            "uptime_seconds": health.get("bridge", {}).get("uptime_seconds", 0),
            "plugin_connected": health.get("bridge", {}).get("plugin_connected", False),
            "active_players": health.get("bridge", {}).get("active_players", 0),
            "total_players_seen": health.get("bridge", {}).get("total_players_seen", 0),
            "llm_requests": health.get("llm", {}).get("total_requests", 0),
            "llm_cost_usd": health.get("llm", {}).get("total_cost_usd", 0),
            "top_players": health.get("top_players", []),
            "event_counts": health.get("event_counts", {}),
            "tool_health": health.get("tool_health", {}),
        })

    # ─── Players ────────────────────────────────────────────────────────

    @routes.get("/players")
    async def players(request: web.Request) -> web.Response:
        err = await auth_middleware(request)
        if err:
            return err

        player_list = []
        if game and hasattr(game, "sessions"):
            for pid, session in game.sessions._sessions.items():
                p = session.player
                player_list.append({
                    "player_id": p.player_id,
                    "display_name": p.display_name,
                    "tier": p.tier,
                    "tribe_id": p.tribe_id or "",
                    "position": p.position,
                })

        return web.json_response({
            "count": len(player_list),
            "players": player_list,
        })

    @routes.get("/players/{player_id}")
    async def player_detail(request: web.Request) -> web.Response:
        err = await auth_middleware(request)
        if err:
            return err

        player_id = request.match_info["player_id"]

        # Check active sessions
        if game and hasattr(game, "sessions"):
            session = game.sessions._sessions.get(player_id)
            if session:
                p = session.player
                return web.json_response({
                    "player_id": p.player_id,
                    "display_name": p.display_name,
                    "tier": p.tier,
                    "tribe_id": p.tribe_id or "",
                    "position": p.position,
                    "online": True,
                })

        # Check metrics for historical data
        from sheldon_bridge.metrics import get_metrics
        summary = get_metrics().get_player_summary(player_id)
        if summary:
            return web.json_response({**summary, "online": False})

        return web.json_response({"error": "Player not found"}, status=404)

    # ─── Events ─────────────────────────────────────────────────────────

    @routes.get("/events")
    async def events(request: web.Request) -> web.Response:
        err = await auth_middleware(request)
        if err:
            return err

        limit = int(request.query.get("limit", 50))
        all_events = []

        if game and hasattr(game, "sessions"):
            for session in game.sessions._sessions.values():
                if hasattr(session, "_events"):
                    for evt in session._events[-limit:]:
                        all_events.append(evt.to_dict())

        all_events.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
        return web.json_response({
            "count": len(all_events),
            "events": all_events[:limit],
        })

    # ─── Session Search ─────────────────────────────────────────────────

    @routes.get("/sessions/search")
    async def sessions_search(request: web.Request) -> web.Response:
        err = await auth_middleware(request)
        if err:
            return err

        player_id = request.query.get("player_id", "")
        query = request.query.get("q", "")

        if not player_id or not query:
            return web.json_response({"error": "player_id and q are required"}, status=400)

        from sheldon_bridge.session_persistence import get_session_store
        store = get_session_store()
        if not store:
            return web.json_response({"error": "Session store not initialized"}, status=503)

        results = await store.search(player_id, query)
        return web.json_response({
            "player_id": player_id,
            "query": query,
            "matches": results,
        })

    # ─── Broadcast ──────────────────────────────────────────────────────

    @routes.post("/broadcast")
    async def broadcast_post(request: web.Request) -> web.Response:
        err = await auth_middleware(request)
        if err:
            return err

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)

        message = body.get("message", "")
        if not message:
            return web.json_response({"error": "No message provided"}, status=400)

        from sheldon_bridge.duckbot_handler import get_command_queue, QueuedCommand
        queue = get_command_queue()
        cmd = QueuedCommand(
            action="console_command",
            command=f"broadcast {message}",
            payload={"source": "admin_rest", "admin": "http"},
        )
        await queue.enqueue(cmd)

        return web.json_response({
            "success": True,
            "message": message,
            "queued": True,
        })

    # ─── Config ─────────────────────────────────────────────────────────

    @routes.get("/config")
    async def config_list(request: web.Request) -> web.Response:
        err = await auth_middleware(request)
        if err:
            return err

        return web.json_response(dict(config.ark))

    @routes.get("/config/{key}")
    async def config_get(request: web.Request) -> web.Response:
        err = await auth_middleware(request)
        if err:
            return err

        key = request.match_info["key"]
        val = config.ark.get(key)
        if val is None:
            return web.json_response({"error": f"Key '{key}' not found"}, status=404)
        return web.json_response({"key": key, "value": val})

    @routes.put("/config/{key}")
    async def config_set(request: web.Request) -> web.Response:
        err = await auth_middleware(request)
        if err:
            return err

        key = request.match_info["key"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)

        value = body.get("value")
        config.ark[key] = value  # Note: in-memory only, not persisted

        return web.json_response({
            "success": True,
            "key": key,
            "value": value,
        })

    # ─── arkduckbot:// Protocol Announce ────────────────────────────────
    # Public endpoint (no auth) so desktop app can discover servers via URL

    @routes.get("/api/v1/announce")
    async def api_v1_announce(request: web.Request) -> web.Response:
        """Server announcement for arkduckbot:// protocol. No auth required.

        Desktop app uses this when user visits arkduckbot://host:port
        to add the server. Returns bridge info, ports, and capabilities.
        """
        from sheldon_bridge.metrics import get_metrics
        metrics = get_metrics()
        health = metrics.get_health()

        return web.json_response({
            "protocol": "arkduckbot",
            "version": "1.0",
            "server": {
                "name": config.ark.get("map", "Unknown"),
                "bridge_host": config.websocket_host,
                "bridge_port": config.websocket_port,
                "admin_ws_port": config.admin_port,
                "admin_http_port": config.admin_port + 1,
                "uptime_seconds": health.get("bridge", {}).get("uptime_seconds", 0),
                "active_players": health.get("bridge", {}).get("active_players", 0),
                "plugin_connected": health.get("bridge", {}).get("plugin_connected", False),
            },
            "llm": {
                "provider": config.llm.provider,
                "model": config.llm.model,
            },
            "capabilities": [
                "websocket_game",
                "websocket_admin",
                "rest_admin",
                "broadcast",
                "skills",
                "skill_bundles",
            ],
        })

    @routes.get("/api/v1/pair/verify")
    async def api_v1_pair_verify(request: web.Request) -> web.Response:
        """Verify a pairing token for arkduckbot:// protocol pairing flow.

        Desktop app sends: ?token=SHARED_SECRET&challenge=RANDOM_STRING
        Bridge validates token and returns signed confirmation.
        """
        token = request.query.get("token", "")
        challenge = request.query.get("challenge", "")

        if not token or not challenge:
            return web.json_response({"error": "Missing token or challenge"}, status=400)

        if not authenticator.validate_token(token):
            return web.json_response({"error": "Invalid token"}, status=401)

        from sheldon_bridge.metrics import get_metrics
        metrics = get_metrics()
        health = metrics.get_health()

        return web.json_response({
            "paired": True,
            "challenge": challenge,
            "server": {
                "name": config.ark.get("map", "Unknown"),
                "bridge_host": config.websocket_host,
                "bridge_port": config.websocket_port,
                "admin_ws_port": config.admin_port,
                "admin_http_port": config.admin_port + 1,
            },
            "llm_provider": config.llm.provider,
        })

    # ─── Shutdown ───────────────────────────────────────────────────────

    @routes.post("/shutdown")
    async def shutdown_post(request: web.Request) -> web.Response:
        err = await auth_middleware(request)
        if err:
            return err

        # Queue graceful shutdown (same as skill)
        try:
            body = await request.json()
        except Exception:
            body = {}

        reason = body.get("reason", "server shutdown")
        delay = body.get("delay_minutes", 10)

        from sheldon_bridge.duckbot_handler import get_command_queue, QueuedCommand
        queue = get_command_queue()

        warnings = [
            (5 * 60, f"⚠️ SERVER NOTICE: Server will shut down in 5 minutes for {reason}."),
            (4 * 60, f"⚠️ SERVER NOTICE: Server will shut down in 4 minutes for {reason}."),
            (3 * 60, f"⚠️ SERVER NOTICE: Server will shut down in 3 minutes."),
            (2 * 60, f"⚠️ SERVER NOTICE: Server will shut down in 2 minutes."),
            (1 * 60, f"⚠️ SERVER NOTICE: Server will shut down in 1 minute."),
            (30, f"🚨 SERVER NOTICE: Shutting down in 30 seconds!"),
            (10, f"🚨 SERVER NOTICE: Shutting down in 10 seconds!"),
        ]

        for delay_s, msg in warnings:
            cmd = QueuedCommand(
                action="console_command",
                command=f"broadcast {msg}",
                scheduled_delay=delay_s,
                payload={"source": "admin_rest"},
            )
            await queue.enqueue(cmd)

        # save + exit
        save_cmd = QueuedCommand(
            action="console_command",
            command="saveworld",
            scheduled_delay=delay * 60 + 5,
            payload={"source": "admin_rest"},
        )
        await queue.enqueue(save_cmd)

        exit_cmd = QueuedCommand(
            action="console_command",
            command="DoExit",
            scheduled_delay=delay * 60 + 10,
            payload={"source": "admin_rest"},
        )
        await queue.enqueue(exit_cmd)

        return web.json_response({
            "success": True,
            "message": f"Shutdown initiated. {len(warnings)} warnings queued.",
            "delay_minutes": delay,
            "reason": reason,
        })

    # ─── Rust+ Server Discovery ─────────────────────────────────────────

    @routes.get("/api/v1/server-info")
    async def api_v1_server_info(request: web.Request) -> web.Response:
        """Rust+ server info endpoint for desktop app discovery.

        Returns the Rust+ API host/port, MCP Bridge host/port, map name,
        and version so Ark-DuckBot-Desktop can verify server authenticity.
        """
        from sheldon_bridge.metrics import get_metrics
        metrics = get_metrics()
        health = metrics.get_health()

        return web.json_response({
            "protocol_version": "1.0",
            "server": {
                "name": config.ark.get("map", "Unknown"),
                "map": config.ark.get("map", "Unknown"),
                "cluster_id": config.ark.get("cluster_id", ""),
                "version": "1.0",
            },
            "rust_plus": {
                # The Rust+ API runs on the game server's RCON port
                # Desktop app should query this via the game server's Rust+ plugin
                "enabled": True,
                "note": "Connect via game server's Rust+ plugin on game query port",
            },
            "mcp_bridge": {
                "host": config.websocket_host,
                "websocket_port": config.websocket_port,
                "admin_ws_port": config.admin_port,
                "admin_http_port": config.admin_port + 1,
            },
            "status": {
                "uptime_seconds": health.get("bridge", {}).get("uptime_seconds", 0),
                "active_players": health.get("bridge", {}).get("active_players", 0),
                "total_players_seen": health.get("bridge", {}).get("total_players_seen", 0),
                "plugin_connected": health.get("bridge", {}).get("plugin_connected", False),
                "llm_requests": health.get("llm", {}).get("total_requests", 0),
                "llm_cost_usd": round(health.get("llm", {}).get("total_cost_usd", 0), 4),
            },
        })

    app = web.Application()
    app.add_routes(routes)
    return app