"""Cross-session memory and learning tools.

Provides AI-powered memory that persists across player sessions.
The agent can recall relevant past solutions and learn from successful tasks.

Tools:
    recall_memory — Search cross-session memory for relevant past solutions
    store_memory  — Store a successful task pattern in memory
    learn_from_task — Analyze a completed task and store lessons learned

Usage:
    from sheldon_bridge.tools.memory import recall_memory, store_memory

    result = await recall_memory(query="tribe dino feeding", limit=5)
    # Returns: {"matches": [{"key": "...", "content": "...", "score": 2.5, "tags": [...]}]}
"""

from __future__ import annotations

import logging
from typing import Any

from sheldon_bridge.tools.registry import tool
from sheldon_bridge.skills.improver import get_cross_session_memory

logger = logging.getLogger(__name__)


@tool(tier="player", description="Search cross-session memory for relevant past solutions and patterns")
async def recall_memory(
    query: str,
    limit: int = 5,
    ctx: dict | None = None,
) -> dict[str, Any]:
    """Search cross-session memory for entries matching the query.

    This is useful when a player asks something that was solved before
    in another session. The AI can recall the solution and apply it.

    Args:
        query: Natural language search query (e.g., "how to feed tribe dinos")
        limit: Maximum number of memories to return (default 5)
        ctx: Injected context
    """
    try:
        memory = get_cross_session_memory()
        results = memory.recall(query, limit=limit)

        if not results:
            return {
                "success": True,
                "matches": [],
                "message": "No relevant memories found. This appears to be a new situation.",
            }

        matches = []
        for entry in results:
            matches.append({
                "key": entry.key,
                "content": entry.content,
                "score": entry.access_count,
                "tags": entry.tags,
                "last_accessed": entry.last_accessed,
                "age_hours": round((getattr(entry, 'created_at', 0) or 0) - entry.last_accessed, 1) if entry.last_accessed else 0,
            })

        return {
            "success": True,
            "matches": matches,
            "count": len(matches),
        }
    except Exception as e:
        logger.error(f"recall_memory failed: {e}")
        return {"success": False, "error": str(e)}


@tool(tier="player", description="Store a successful task pattern in cross-session memory for future recall")
async def store_memory(
    key: str,
    content: str,
    tags: str = "",
    ctx: dict | None = None,
) -> dict[str, Any]:
    """Store a new memory entry.

    Use this after a successful multi-step task to save the pattern
    so it can be recalled in similar future situations.

    Args:
        key: Searchable key (e.g., "tribe feeding pattern", "boss fight strategy")
        content: The lesson or pattern to remember
        tags: Comma-separated tags (e.g., "tribe,dino,feeding")
        ctx: Injected context
    """
    try:
        memory = get_cross_session_memory()
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        entry = memory.store(key=key, content=content, tags=tag_list)

        return {
            "success": True,
            "stored_id": entry.id,
            "message": f"Memory stored: [{key}] {content[:60]}...",
        }
    except Exception as e:
        logger.error(f"store_memory failed: {e}")
        return {"success": False, "error": str(e)}


@tool(tier="player", description="Learn from a completed task — analyze and store successful patterns")
async def learn_from_task(
    task_description: str,
    steps_taken: str,
    successful: bool = True,
    player_tier: str = "player",
    ctx: dict | None = None,
) -> dict[str, Any]:
    """Review a completed task and store lessons learned.

    Call this after any non-trivial task (multi-step or notable outcome).
    The system analyzes the pattern and stores it for future recall.

    Args:
        task_description: Brief description of what was accomplished
        steps_taken: Comma-separated list of steps taken (e.g., "1. spawn dino, 2. teleport, 3. feed")
        successful: Whether the task was completed successfully
        player_tier: The permission tier of the player who did the task
        ctx: Injected context
    """
    try:
        from sheldon_bridge.skills.improver import AgentImprover, get_cross_session_memory
        from sheldon_bridge.skills.registry import get_skill_registry

        memory = get_cross_session_memory()
        registry = get_skill_registry()
        improver = AgentImprover(registry, memory)

        steps_list = [s.strip() for s in steps_taken.split(",") if s.strip()]

        improver.review_completed_task(
            task_description=task_description,
            steps=steps_list,
            successful=successful,
            player_tier=player_tier,
        )

        # Also store directly in memory for easier recall
        memory.store(
            key=f"task:{task_description[:50]}",
            content=f"Completed: {task_description}. Steps: {' -> '.join(steps_list)}. Success: {successful}. Tier: {player_tier}",
            tags=["task", "completed" if successful else "failed"],
        )

        nudge = improver.get_nudge()

        return {
            "success": True,
            "message": f"Learned from task: {task_description[:60]}",
            "steps_analyzed": len(steps_list),
            "nudge": nudge if nudge else None,
        }
    except Exception as e:
        logger.error(f"learn_from_task failed: {e}")
        return {"success": False, "error": str(e)}


@tool(tier="admin", description="Get memory statistics and health")
async def memory_stats(ctx: dict | None = None) -> dict[str, Any]:
    """Get cross-session memory statistics."""
    try:
        memory = get_cross_session_memory()

        total_entries = len(memory._entries)
        total_accesses = sum(e.access_count for e in memory._entries.values())
        recent_entries = [
            {"key": e.key, "content": e.content[:80], "access_count": e.access_count}
            for e in sorted(memory._entries.values(), key=lambda x: x.last_accessed, reverse=True)[:10]
        ]

        return {
            "success": True,
            "total_entries": total_entries,
            "total_accesses": total_accesses,
            "recent_entries": recent_entries,
        }
    except Exception as e:
        logger.error(f"memory_stats failed: {e}")
        return {"success": False, "error": str(e)}