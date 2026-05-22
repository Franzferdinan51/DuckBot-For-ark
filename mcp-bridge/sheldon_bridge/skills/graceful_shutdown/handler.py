"""Graceful shutdown skill handler.

Broadcasts countdown warnings to players at timed intervals, saves the world,
then shuts down. Implements timed countdown: 5, 4, 3, 2, 1 minutes, then 30s, 10s.

Non-blocking: commands are queued immediately, method returns right away.
The C++ plugin polls for pending commands and executes them at scheduled times.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def handle(ctx: dict) -> dict[str, Any]:
    """Execute the graceful shutdown skill with timed player warnings.

    Queues all shutdown commands immediately. The command queue system
    handles timing via the C++ plugin's polling mechanism.

    Args:
        ctx: Expected keys:
            - game_handler: DuckBotHandler
            - delay_minutes: int (default 10)
            - reason: str (default "server maintenance")
    """
    game_handler = ctx.get("game_handler")
    delay_minutes = ctx.get("delay_minutes", 10)
    reason = ctx.get("reason", "server maintenance")

    if not game_handler:
        return {
            "success": False,
            "message": "Game handler not available — cannot perform graceful shutdown",
        }

    # Build the warning schedule
    # The C++ plugin will interpret relative timestamps from command metadata
    warnings = [
        (delay_minutes * 60, f"⚠️ SERVER NOTICE: Server will shut down in {delay_minutes} minutes for {reason}. Please safe your character!"),
        (4 * 60, f"⚠️ SERVER NOTICE: Server will shut down in 4 minutes for {reason}."),
        (3 * 60, f"⚠️ SERVER NOTICE: Server will shut down in 3 minutes for {reason}. Prepare for shutdown!"),
        (2 * 60, f"⚠️ SERVER NOTICE: Server will shut down in 2 minutes for {reason}. Finish up now!"),
        (1 * 60, f"⚠️ SERVER NOTICE: Server will shut down in 1 minute for {reason}. Immediate action required!"),
        (30, f"🚨 SERVER NOTICE: Server shutting down in 30 seconds! Save your character NOW!"),
        (10, f"🚨 SERVER NOTICE: Server shutting down in 10 seconds!"),
    ]

    # Queue each broadcast command with its scheduled time
    for delay, message in warnings:
        cmd = {
            "action": "console_command",
            "command": f'broadcast {message}',
            "scheduled_delay": delay,
        }
        await game_handler(cmd)

    # Queue saveworld and exit at the end
    save_cmd = {
        "action": "console_command",
        "command": "saveworld",
        "scheduled_delay": delay_minutes * 60 + 5,
    }
    await game_handler(save_cmd)

    exit_cmd = {
        "action": "console_command",
        "command": "DoExit",
        "scheduled_delay": delay_minutes * 60 + 10,
    }
    await game_handler(exit_cmd)

    logger.info(f"Graceful shutdown queued — {len(warnings)} warnings, saveworld, DoExit. Reason: {reason}")

    return {
        "success": True,
        "message": (
            f"Graceful shutdown initiated. {len(warnings)} countdown warnings "
            f"will be sent over the next {delay_minutes} minutes. "
            f"World will be saved and server will exit. Reason: {reason}"
        ),
        "data": {
            "warnings_queued": len(warnings),
            "total_duration_seconds": delay_minutes * 60 + 10,
            "reason": reason,
            "delay_minutes": delay_minutes,
        },
    }