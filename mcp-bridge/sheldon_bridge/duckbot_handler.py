"""DuckBot game handler — routes tool calls to the C++ plugin via WebSocket.

The Python MCP bridge runs as a WebSocket SERVER. The DuckBot C++ plugin
connects AS A CLIENT and registers itself. When the AI agent calls a tool
(e.g., spawn_dino, give_item), this handler queues the command and the
C++ plugin polls for it via its incoming message handler.

This design keeps the plugin as the client (avoids firewall issues on server)
while still allowing the bridge to send commands to the game.

Flow:
  AI tool call → duckbot_handler.queue_command(cmd) → stored in command_queue
  C++ plugin polls bridge → receives pending commands → executes in-game
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sheldon_bridge.tools.registry import tool

logger = logging.getLogger(__name__)

# ─── Command Queue ───────────────────────────────────────────────────────

@dataclass
class QueuedCommand:
    """A command queued for the DuckBot C++ plugin to execute."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    action: str = ""
    command: str = ""
    payload: dict = field(default_factory=dict)
    callback_id: str | None = None  # for async responses
    enqueued_at: float = 0.0
    scheduled_delay: float = 0.0  # seconds to wait before executing (for timed sequences)


class CommandQueue:
    """Thread-safe command queue for DuckBot plugin commands."""

    def __init__(self, max_size: int = 100):
        self._queue: list[QueuedCommand] = []
        self._max_size = max_size
        self._lock = asyncio.Lock()

    async def enqueue(self, command: QueuedCommand) -> str:
        """Add a command to the queue. Returns command ID."""
        async with self._lock:
            if len(self._queue) >= self._max_size:
                # Drop oldest command
                self._queue.pop(0)
            self._queue.append(command)
            logger.debug(f"Command queued: {command.action} [{command.id}]")
            return command.id

    async def dequeue_all(self) -> list[QueuedCommand]:
        """Get and clear all pending commands (called by plugin polling)."""
        async with self._lock:
            commands = list(self._queue)
            self._queue.clear()
            return commands

    async def size(self) -> int:
        async with self._lock:
            return len(self._queue)


# Global command queue (singleton)
_command_queue: CommandQueue | None = None


def get_command_queue() -> CommandQueue:
    global _command_queue
    if _command_queue is None:
        _command_queue = CommandQueue()
    return _command_queue


# ─── DuckBot Handler ─────────────────────────────────────────────────────

class DuckBotHandler:
    """Game handler that routes commands to the DuckBot C++ plugin.

    The Python bridge queues commands here. The C++ plugin polls this
    bridge over its established WebSocket connection to pick up pending
    commands and execute them in-game.

    Mock mode (no plugin connected): logs commands and returns success.
    """

    def __init__(self):
        self._queue = get_command_queue()
        self._connected = False
        self._plugin_id: str | None = None

    def mark_connected(self, plugin_id: str) -> None:
        """Called when DuckBot C++ plugin connects and registers."""
        self._connected = True
        self._plugin_id = plugin_id
        logger.info(f"DuckBot plugin connected: {plugin_id}")

    def mark_disconnected(self) -> None:
        """Called when plugin disconnects."""
        self._connected = False
        self._plugin_id = None
        logger.info("DuckBot plugin disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def __call__(self, command: dict) -> dict:
        """Route a game command to DuckBot plugin.

        Args:
            command: dict with "action" and action-specific fields.
                Common actions:
                - "console_command": {"command": "SetTimeOfDay 18:00:00"}
                - "spawn_dino": {"blueprint": "...", "level": 150, "x": ..., "y": ..., "z": ...}
                - "teleport": {"steam_id": ..., "x": ..., "y": ..., "z": ...}
                - "give_item": {"player_name": "...", "blueprint": "...", "quantity": 1}

        Returns:
            Result dict with success status and message.
        """
        action = command.get("action", "unknown")

        if action == "console_command":
            cmd_str = command.get("command", "")
            delay = command.get("scheduled_delay", 0.0)
            return await self._queue_console_command(cmd_str, scheduled_delay=delay)

        elif action == "spawn_dino":
            return await self._queue_spawn_dino(command)

        elif action == "teleport_player":
            return await self._queue_teleport(command)

        elif action == "give_item":
            return await self._queue_give_item(command)

        elif action == "slay_dino":
            return await self._queue_slay(command)

        elif action == "feed_tribe":
            return await self._queue_feed_tribe(command)

        else:
            logger.warning(f"Unknown game action: {action}")
            return {"success": False, "error": f"Unknown action: {action}"}

    async def _queue_console_command(self, cmd_str: str, scheduled_delay: float = 0.0) -> dict:
        """Queue a raw console command for the plugin to execute.

        Args:
            cmd_str: The console command string.
            scheduled_delay: Seconds to wait before executing (for timed sequences).
        """
        payload = {"raw": cmd_str}
        if scheduled_delay > 0:
            payload["scheduled_delay"] = scheduled_delay
        cmd = QueuedCommand(
            action="console_command",
            command=cmd_str,
            payload=payload,
            scheduled_delay=scheduled_delay,
        )
        await self._queue.enqueue(cmd)
        return self._make_result(cmd.id, f"Command queued (delay={scheduled_delay}s): {cmd_str}")

    async def _queue_spawn_dino(self, data: dict) -> dict:
        """Queue a dino spawn command."""
        blueprint = data.get("blueprint", "")
        level = data.get("level", 1)
        x = data.get("x", 0)
        y = data.get("y", 0)
        z = data.get("z", 0)
        gender = data.get("gender", "random")
        force_tame = data.get("force_tame", True)

        cmd_str = f'SpawnDino "{blueprint}" {x} {y} {z} {level} {gender} {str(force_tame).lower()}'
        cmd = QueuedCommand(action="spawn_dino", command=cmd_str, payload=data)
        await self._queue.enqueue(cmd)

        species = blueprint.split('.')[-1] if blueprint else "Unknown"
        return self._make_result(cmd.id, f"Spawn queued: {species} level {level}")

    async def _queue_teleport(self, data: dict) -> dict:
        """Queue a player teleport command."""
        steam_id = data.get("steam_id", 0)
        x = data.get("x", 0)
        y = data.get("y", 0)
        z = data.get("z", 0)
        cmd = QueuedCommand(
            action="teleport",
            command=f"TeleportPlayer {steam_id} {x} {y} {z}",
            payload=data,
        )
        await self._queue.enqueue(cmd)
        return self._make_result(cmd.id, f"Teleport queued for Steam {steam_id}")

    async def _queue_give_item(self, data: dict) -> dict:
        """Queue an item give command."""
        player = data.get("player_name", "")
        blueprint = data.get("blueprint", "")
        quantity = data.get("quantity", 1)
        quality = data.get("quality", 0)

        cmd_str = f'GiveItemToPlayer "{player}" "{blueprint}" {quantity} {quality} false'
        cmd = QueuedCommand(action="give_item", command=cmd_str, payload=data)
        await self._queue.enqueue(cmd)
        return self._make_result(cmd.id, f"Item queued: {quantity}x {blueprint.split('.')[-1]}")

    async def _queue_slay(self, data: dict) -> dict:
        """Queue a slay command (kill dinos by owner or player)."""
        target = data.get("target", "")
        cmd = QueuedCommand(action="slay", command=f"Slay {target}", payload=data)
        await self._queue.enqueue(cmd)
        return self._make_result(cmd.id, f"Slay queued: {target}")

    async def _queue_feed_tribe(self, data: dict) -> dict:
        """Queue a tribe feed command."""
        tribe_id = data.get("tribe_id", 0)
        cmd = QueuedCommand(action="feed_tribe", command=f"FeedTribe {tribe_id}", payload=data)
        await self._queue.enqueue(cmd)
        return self._make_result(cmd.id, f"Tribe feed queued for tribe {tribe_id}")

    def _make_result(self, cmd_id: str, message: str) -> dict:
        """Build a success result with command tracking info."""
        return {
            "success": True,
            "queued": True,
            "command_id": cmd_id,
            "message": message,
            "plugin_connected": self._connected,
        }


# ─── Game Handler Factory ───────────────────────────────────────────────

def create_duckbot_handler() -> DuckBotHandler:
    """Create the DuckBot game handler for tool actions."""
    return DuckBotHandler()


# ─── Tool: Get Pending Commands (for plugin polling) ────────────────────

@tool(tier="admin", description="Get pending commands for the plugin (internal use)")
async def get_pending_commands(ctx: dict | None = None) -> dict[str, Any]:
    """Poll for commands queued by the bridge for the C++ plugin to execute.

    This is called by the C++ plugin's polling loop, not by the AI agent.
    Returns a list of pending commands.
    """
    queue = get_command_queue()
    commands = await queue.dequeue_all()
    return {
        "success": True,
        "count": len(commands),
        "commands": [
            {
                "id": cmd.id,
                "action": cmd.action,
                "command": cmd.command,
                "payload": cmd.payload,
            }
            for cmd in commands
        ],
    }