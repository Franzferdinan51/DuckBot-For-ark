"""Auto-feed skill handler.

Auto-feeds all tribe dinos when triggered (baby born, manual call, etc.)
"""
from __future__ import annotations

import logging
from typing import Any

from sheldon_bridge.skills.registry import SkillResult

logger = logging.getLogger(__name__)


async def handle(ctx: dict) -> dict[str, Any]:
    """Execute the auto-feed skill.

    Context expected:
        game_handler: DuckBotHandler
        player: PlayerContext
        tribe_data: dict (optional)
        event_data: dict (optional, for event-triggered calls)
    """
    game_handler = ctx.get("game_handler")
    tribe_data = ctx.get("tribe_data", {})
    event_data = ctx.get("event_data", {})

    if not game_handler:
        return {
            "success": False,
            "message": "Game handler not available",
        }

    tribe_id = tribe_data.get("tribe_id", 0)
    tribe_name = tribe_data.get("tribe_name", "Unknown Tribe")

    if not tribe_id:
        return {
            "success": False,
            "message": "Player is not in a tribe",
        }

    # Queue a tribe feed command
    result = await game_handler({
        "action": "feed_tribe",
        "tribe_id": tribe_id,
    })

    logger.info(f"Auto-feed triggered for tribe {tribe_name} (ID: {tribe_id})")

    return {
        "success": True,
        "message": f"Auto-feed initiated for {tribe_name} — all tribe dinos are being fed.",
        "data": {
            "tribe_id": tribe_id,
            "tribe_name": tribe_name,
            "dinos_fed": "all",
        },
    }