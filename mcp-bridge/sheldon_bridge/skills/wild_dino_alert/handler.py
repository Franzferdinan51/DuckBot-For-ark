"""Wild dino alert skill handler.

Checks for dangerous wild dinos and alerts the player/tribe.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


DANGEROUS_SPECIES = {
    "Giganotosaurus", "Titanosaur", "Megalodon", "Tusoteuthis",
    "Rex", "Spino", "Carcha", "Wyvern", "Dragon", "Phoenix",
}

MIN_ALERT_LEVEL = 30


async def handle(ctx: dict) -> dict[str, Any]:
    """Execute the wild dino alert skill.

    Context expected:
        game_handler: DuckBotHandler
        player: PlayerContext
        event_data: dict (from wild_dino_alert event)
    """
    event_data = ctx.get("event_data", {})
    player = ctx.get("player")

    species = event_data.get("species", "Unknown")
    level = event_data.get("level", 0)
    distance = event_data.get("distance", 0)

    if level < MIN_ALERT_LEVEL:
        return {
            "success": True,
            "message": f"Wild {species} (level {level}) detected but below alert threshold.",
            "data": {"species": species, "level": level, "alert_triggered": False},
        }

    is_dangerous = species in DANGEROUS_SPECIES

    message = (
        f"🚨 DANGER: Wild {species} (level {level}) detected "
        f"at distance {distance:.0f}m"
    )
    if is_dangerous:
        message += " — HIGH PRIORITY"

    logger.info(f"Wild dino alert for {player.display_name if player else 'unknown'}: {species} L{level}")

    return {
        "success": True,
        "message": message,
        "data": {
            "species": species,
            "level": level,
            "distance": distance,
            "dangerous": is_dangerous,
            "alert_triggered": True,
        },
    }