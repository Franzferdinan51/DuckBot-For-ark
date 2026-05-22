"""Self-improving agent — hermes-agent-inspired.

The agent can improve itself over time by:
1. Creating new skills after complex multi-step tasks (SkillCreator)
2. Cross-session memory retrieval (CrossSessionMemory)
3. Periodic self-checks (AgentImprover)
4. Nudge system that reminds the AI of learned patterns
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ─── Cross-Session Memory ─────────────────────────────────────────────

@dataclass
class MemoryEntry:
    """A cross-session memory entry."""
    id: str
    key: str  # search key (player name, tribe, pattern, etc.)
    content: str
    created_at: float = field(default_factory=time.time)
    last_accessed: float = 0.0
    access_count: int = 0
    tags: list[str] = field(default_factory=list)

    def touch(self) -> None:
        self.last_accessed = time.time()
        self.access_count += 1


class CrossSessionMemory:
    """Simple full-text search over session memories.

    Provides cross-session recall so the agent doesn't forget
    important patterns across player sessions.
    """

    def __init__(self, storage_path: str | None = None):
        if storage_path is None:
            storage_path = str(Path("data") / "memory" / "cross_session.json")
        self._storage = Path(storage_path)
        self._entries: dict[str, MemoryEntry] = {}
        self._index: dict[str, set[str]] = defaultdict(set)  # word → entry_ids
        self._load()

    def _load(self) -> None:
        """Load memory from disk."""
        if not self._storage.exists():
            return
        try:
            data = json.loads(self._storage.read_text())
            for entry_data in data.get("entries", []):
                entry = MemoryEntry(**entry_data)
                self._entries[entry.id] = entry
                for word in self._tokenize(entry.key):
                    self._index[word].add(entry.id)
                for word in self._tokenize(entry.content):
                    self._index[word].add(entry.id)
        except Exception as e:
            logger.error(f"Failed to load cross-session memory: {e}")

    def _save(self) -> None:
        """Persist memory to disk."""
        self._storage.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "entries": [
                {
                    "id": e.id,
                    "key": e.key,
                    "content": e.content,
                    "created_at": e.created_at,
                    "last_accessed": e.last_accessed,
                    "access_count": e.access_count,
                    "tags": e.tags,
                }
                for e in self._entries.values()
            ]
        }
        self._storage.write_text(json.dumps(data, indent=2))

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization — lowercase, alphanumeric only."""
        return re.findall(r"[a-z0-9]+", text.lower())

    def _score(self, entry: MemoryEntry, query_tokens: list[str]) -> float:
        """Score how well an entry matches a query."""
        content_tokens = self._tokenize(entry.key) + self._tokenize(entry.content)
        score = 0.0
        for qt in query_tokens:
            if qt in content_tokens:
                score += 1.0
        # Boost by access count (frequently accessed = more relevant)
        score += min(entry.access_count * 0.1, 2.0)
        # Recency boost
        age_hours = (time.time() - entry.created_at) / 3600
        score += max(0, 1.0 - age_hours / 168)  # decay over 1 week
        return score

    def recall(self, query: str, limit: int = 5) -> list[MemoryEntry]:
        """Search memory for entries matching the query.

        Returns top `limit` entries sorted by relevance.
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Find candidate entry IDs
        candidates: set[str] | None = None
        for token in query_tokens:
            if candidates is None:
                candidates = set(self._index.get(token, []))
            else:
                candidates &= self._index.get(token, set())
            if not candidates:
                break

        if not candidates:
            return []

        scored = []
        for eid in candidates:
            entry = self._entries.get(eid)
            if entry:
                score = self._score(entry, query_tokens)
                if score > 0:
                    scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [e for _, e in scored[:limit]]
        for e in results:
            e.touch()
        return results

    def store(
        self,
        key: str,
        content: str,
        tags: list[str] | None = None,
    ) -> MemoryEntry:
        """Store a new memory entry."""
        import uuid
        entry = MemoryEntry(
            id=uuid.uuid4().hex[:12],
            key=key,
            content=content,
            tags=tags or [],
        )
        self._entries[entry.id] = entry
        for word in self._tokenize(key):
            self._index[word].add(entry.id)
        for word in self._tokenize(content):
            self._index[word].add(entry.id)
        self._save()
        logger.info(f"Memory stored: [{key}] {content[:80]}")
        return entry

    def update(self, entry_id: str, content: str) -> bool:
        """Update an existing entry's content."""
        entry = self._entries.get(entry_id)
        if not entry:
            return False
        entry.content = content
        self._save()
        return True


# ─── Agent Improver ───────────────────────────────────────────────────

@dataclass
class ImprovementCandidate:
    """A complex task that might warrant a new skill."""
    task_description: str
    steps_taken: list[str]
    successful: bool
    player_tier: str
    timestamp: float = field(default_factory=time.time)


class AgentImprover:
    """Reviews completed tasks and creates new skills when patterns emerge.

    After complex multi-step tasks, the improver checks if a reusable skill
    should be created. It analyzes:
    - Number of steps taken
    - Tool call patterns
    - Success/failure
    - Whether the same pattern could be generalized
    """

    def __init__(self, skill_registry, memory: CrossSessionMemory):
        self._registry = skill_registry
        self._memory = memory
        self._candidates: list[ImprovementCandidate] = []

    def review_completed_task(
        self,
        task_description: str,
        steps: list[str],
        successful: bool,
        player_tier: str,
    ) -> None:
        """Review a completed task for potential skill creation.

        Call this after every multi-step task (3+ tool calls or significant steps).
        """
        if len(steps) < 3 and successful:
            return  # Too simple to warrant a skill

        candidate = ImprovementCandidate(
            task_description=task_description,
            steps_taken=steps,
            successful=successful,
            player_tier=player_tier,
        )
        self._candidates.append(candidate)

        # Analyze when we have 3+ candidates
        if len(self._candidates) >= 3:
            self._analyze_and_create_skills()

    def _analyze_and_create_skills(self) -> None:
        """Look for patterns across recent candidates and create skills."""
        # Simple pattern: find tasks with similar trigger phrases
        by_pattern: dict[str, list[ImprovementCandidate]] = defaultdict(list)
        for cand in self._candidates:
            # Extract key phrase from task description
            trigger = cand.task_description.lower().split()[0:3]
            pattern_key = " ".join(trigger)
            by_pattern[pattern_key].append(cand)

        # Create a skill if we see 3+ similar tasks
        for pattern, cands in by_pattern.items():
            if len(cands) >= 3 and all(c.successful for c in cands):
                # Check if skill already exists
                existing = self._registry.get(pattern.replace(" ", "_"))
                if existing:
                    continue

                # Create new skill from pattern
                self._create_skill_from_pattern(pattern, cands)
                logger.info(f"Agent improver created new skill: {pattern}")

        self._candidates.clear()  # Reset after analysis

    def _create_skill_from_pattern(
        self, pattern: str, candidates: list[ImprovementCandidate]
    ) -> None:
        """Create a new skill from repeated successful task patterns."""
        # This would create the skill directory and files
        # For now, just store in memory
        summary = (
            f"Skill '{pattern}' created from {len(candidates)} similar tasks. "
            f"Steps: {' -> '.join(candidates[0].steps_taken[:5])}"
        )
        self._memory.store(
            key=f"skill:{pattern}",
            content=summary,
            tags=["auto-created", "skill"],
        )

    def get_nudge(self) -> str | None:
        """Get a periodic nudge to remind the AI of learned patterns.

        Called every N interactions to give the AI a chance to use
        cross-session memory.
        """
        # Check for relevant memories periodically
        memories = self._memory.recall("tribe dino feeding pattern", limit=1)
        if memories:
            mem = memories[0]
            return (
                f"Reminder from memory: {mem.content[:200]}. "
                f"(accessed {mem.access_count}x, last accessed {time.strftime('%H:%M', time.localtime(mem.last_accessed))})"
            )
        return None


# ─── Global instances ─────────────────────────────────────────────────

_memory: CrossSessionMemory | None = None


def get_cross_session_memory() -> CrossSessionMemory:
    global _memory
    if _memory is None:
        _memory = CrossSessionMemory()
    return _memory


def get_agent_improver(skill_registry) -> AgentImprover:
    return AgentImprover(skill_registry, get_cross_session_memory())