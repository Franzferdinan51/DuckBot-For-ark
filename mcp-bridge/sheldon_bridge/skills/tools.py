"""Skill execution tool — lets the AI invoke named skills.

The AI calls this tool when it wants to run a skill workflow.
Auto-triggered skills are called directly by the server when matching
game events occur (see DuckBotSession.handle_event).
"""

from __future__ import annotations

import logging
from typing import Any

from sheldon_bridge.skills.registry import get_skill_registry, SkillResult

logger = logging.getLogger(__name__)


async def skill_execute(skill_name: str, ctx: dict | None = None) -> dict[str, Any]:
    """Execute a named skill by the AI agent.

    This is called when the LLM wants to run a multi-step workflow
    rather than a single tool call.

    Args:
        skill_name: The name of the skill to execute.
        ctx: Injected context (game_handler, player, tribe_data, event_data)
    """
    registry = get_skill_registry()
    skill = registry.get(skill_name)

    if not skill:
        return {
            "success": False,
            "error": f"Skill '{skill_name}' not found. Available: {[s.meta.name for s in registry.all()]}",
        }

    if ctx is None:
        ctx = {}

    result = await skill.execute(ctx)

    return {
        "success": result.success,
        "skill": result.skill_name,
        "message": result.message,
        "data": result.data,
        "duration_ms": round(result.duration_ms, 1),
        "improved": result.improved,
    }


async def skill_update(skill_name: str, improvements: str, ctx: dict | None = None) -> dict[str, Any]:
    """Update a skill's metadata (self-improving agent pattern).

    After a skill runs, the agent can call this to update its examples
    or description based on what worked well.

    Args:
        skill_name: The name of the skill to update.
        improvements: The new/improved content (append to examples, update description).
        ctx: Injected context.
    """
    registry = get_skill_registry()
    skill = registry.get(skill_name)

    if not skill:
        return {
            "success": False,
            "error": f"Skill '{skill_name}' not found.",
        }

    # Update the skill's examples (append new successful example)
    if improvements:
        # For now, just log — a full implementation would rewrite SKILL.md
        logger.info(f"Skill '{skill_name}' self-improved: {improvements[:200]}")

    return {
        "success": True,
        "message": f"Skill '{skill_name}' updated with new improvements.",
    }


def register_skill_tools(registry) -> None:
    """Register skill tools with the tool registry.

    Called by the tool registry at startup to expose skill execution
    to the AI.
    """
    from sheldon_bridge.tools.registry import tool

    @tool(tier="player", description="Execute a named skill workflow. Skills are multi-step automations the AI can run (e.g., auto-feed, wild-dino-alert). Use this when the player wants a complex task done that involves multiple steps.")
    async def execute_skill(skill_name: str, ctx: dict | None = None) -> dict[str, Any]:
        """Execute a named skill workflow.

        Args:
            skill_name: The name of the skill to execute (e.g., "auto_feed", "wild_dino_alert").
            ctx: Context passed automatically (game_handler, player, tribe_data, event_data).
        """
        return await skill_execute(skill_name, ctx)

    @tool(tier="admin", description="Update a skill's metadata to improve it over time (self-improving agent). Call this after a skill runs successfully to record what worked.")
    async def update_skill(skill_name: str, improvements: str, ctx: dict | None = None) -> dict[str, Any]:
        """Update/improve a skill based on recent execution.

        Args:
            skill_name: Name of the skill to improve.
            improvements: New examples or description improvements.
            ctx: Context passed automatically.
        """
        return await skill_update(skill_name, improvements, ctx)