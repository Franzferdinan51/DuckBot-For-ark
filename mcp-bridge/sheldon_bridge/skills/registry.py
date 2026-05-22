"""DuckBot skill system — openclaw-inspired.

A skill is a discrete workflow unit that the AI can invoke to accomplish
a multi-step task. Skills are discovered at startup from the skills/
directory and injected into the AI's system prompt so it knows what it
can call.

Format:
    skills/
        skill_name/
            SKILL.md          — metadata (name, description, triggers, examples)
            handler.py        — async function to execute the skill
            __init__.py       — registers the skill

Trigger pattern: the AI calls a skill via a tool call (skill_execute).
Events can also auto-trigger skills (e.g., baby_giga_born → auto_feed_workflow).

Self-improving: after a skill completes, the agent can update its SKILL.md
with improved examples based on what worked.
"""

from __future__ import annotations

import asyncio
import logging
import importlib
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class SkillMetadata:
    """Metadata for a skill, defined in SKILL.md."""
    name: str
    description: str
    triggers: list[str] = field(default_factory=list)  # keywords that trigger this skill
    examples: list[str] = field(default_factory=list)  # example prompts that work with this skill
    auto_trigger_on: list[str] = field(default_factory=list)  # game events that auto-trigger
    tier_required: str = "player"  # minimum tier to use this skill
    version: str = "1.0.0"
    author: str = "DuckBot"


@dataclass
class SkillResult:
    """Result of a skill execution."""
    success: bool
    message: str  # human-readable summary
    data: dict[str, Any] = field(default_factory=dict)  # structured output
    skill_name: str = ""
    duration_ms: float = 0.0
    improved: bool = False  # whether skill was self-improved during execution


class Skill:
    """A single skill — workflow unit the AI can invoke.

    A skill wraps a handler function with metadata. The handler is an
    async function that takes a skill context dict and returns a SkillResult.
    """

    def __init__(self, metadata: SkillMetadata, handler: Callable):
        self.meta = metadata
        self.handler = handler  # async function(ctx: dict) -> SkillResult

    async def execute(self, ctx: dict) -> SkillResult:
        """Execute this skill with the given context."""
        import time
        start = time.time()
        try:
            result = await self.handler(ctx)
            if isinstance(result, dict):
                # Wrap raw dict in SkillResult
                return SkillResult(
                    success=result.get("success", True),
                    message=result.get("message", ""),
                    data=result,
                    skill_name=self.meta.name,
                    duration_ms=(time.time() - start) * 1000,
                )
            return result
        except Exception as e:
            logger.error(f"Skill '{self.meta.name}' failed: {e}")
            return SkillResult(
                success=False,
                message=f"Skill failed: {e}",
                skill_name=self.meta.name,
                duration_ms=(time.time() - start) * 1000,
            )


class SkillRegistry:
    """Registry of all available skills.

    Discovers skills from the skills/ directory at startup.
    Provides lookup by name, by trigger keyword, and by game event.

    Skill Snapshot Versioning (openclaw pattern):
        - Each skill has a version field
        - Registry computes a combined hash of all skill versions
        - Snapshot is cached and only refreshed when versions change
        - This prevents stale skill data after updates
    """

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._triggers: dict[str, list[str]] = {}  # trigger_word → [skill_names]
        self._event_handlers: dict[str, list[str]] = {}  # event_type → [skill_names]
        self._snapshot_version: str = ""  # hash of all skill versions
        self._snapshot_valid: bool = False

    def register(self, skill: Skill) -> None:
        """Register a skill and recompute snapshot version."""
        self._skills[skill.meta.name] = skill
        for trigger in skill.meta.triggers:
            if trigger not in self._triggers:
                self._triggers[trigger] = []
            self._triggers[trigger].append(skill.meta.name)
        for event in skill.meta.auto_trigger_on:
            if event not in self._event_handlers:
                self._event_handlers[event] = []
            self._event_handlers[event].append(skill.meta.name)

        # Invalidate cached snapshot — new skill means version changed
        self._snapshot_valid = False

        logger.info(
            f"Registered skill: {skill.meta.name} "
            f"(triggers={skill.meta.triggers}, version={skill.meta.version})"
        )

    def get(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def get_by_trigger(self, trigger: str) -> list[Skill]:
        """Get skills that match a trigger keyword."""
        names = self._triggers.get(trigger.lower(), [])
        return [self._skills[n] for n in names if n in self._skills]

    def get_for_event(self, event_type: str) -> list[Skill]:
        """Get skills that auto-trigger on a game event."""
        names = self._event_handlers.get(event_type, [])
        return [self._skills[n] for n in names if n in self._skills]

    def all(self) -> list[Skill]:
        """List all registered skills."""
        return list(self._skills.values())

    def to_llm_format(self) -> list[dict]:
        """Get all skills formatted for LLM system prompt injection."""
        return [
            {
                "name": s.meta.name,
                "description": s.meta.description,
                "triggers": s.meta.triggers,
                "examples": s.meta.examples,
            }
            for s in self._skills.values()
        ]

    def discover(self, skills_dir: Path | None = None) -> None:
        """Discover and load skills from the skills/ directory.

        Each subdirectory is treated as a skill. It must contain:
        - SKILL.md (metadata)
        - handler.py (async function)

        Example structure:
            skills/
                auto_feed/
                    SKILL.md
                    handler.py
        """
        if skills_dir is None:
            # Default to skills/ in the same directory as this module
            skills_dir = Path(__file__).parent.parent / "skills"

        if not skills_dir.exists():
            logger.warning(f"Skills directory not found: {skills_dir}")
            return

        for skill_path in skills_dir.iterdir():
            if not skill_path.is_dir():
                continue
            skill_name = skill_path.name

            # Load SKILL.md
            meta_path = skill_path / "SKILL.md"
            if not meta_path.exists():
                logger.warning(f"Skill '{skill_name}' missing SKILL.md, skipping")
                continue

            meta = _parse_skill_md(meta_path)

            # Load handler.py
            handler_path = skill_path / "handler.py"
            if not handler_path.exists():
                logger.warning(f"Skill '{skill_name}' missing handler.py, skipping")
                continue

            try:
                # Dynamically import the handler module
                module_name = f"sheldon_bridge.skills.{skill_name}.handler"
                spec = importlib.util.spec_from_file_location(module_name, handler_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Handler must export a 'handle' async function
                if not hasattr(module, "handle"):
                    logger.warning(f"Skill '{skill_name}' handler.py missing 'handle' async function")
                    continue

                skill = Skill(metadata=meta, handler=module.handle)
                self.register(skill)
                logger.info(f"Loaded skill: {skill_name}")

            except Exception as e:
                logger.error(f"Failed to load skill '{skill_name}': {e}")

        # After all skills discovered, compute initial snapshot version
        self._compute_snapshot_version()

    def _compute_snapshot_version(self) -> str:
        """Compute a hash of all skill versions to detect stale data.

        Called after discover() and whenever a skill is registered.
        The hash is stored in _snapshot_version and compared on each
        agent run to detect if a refresh is needed.
        """
        import hashlib

        # Collect all skill version strings
        version_parts = []
        for skill in self._skills.values():
            version_parts.append(f"{skill.meta.name}:{skill.meta.version}")

        # Sort for deterministic output
        version_parts.sort()
        combined = "|".join(version_parts).encode()

        # SHA256 hash — truncated to 12 chars for readability
        self._snapshot_version = hashlib.sha256(combined).hexdigest()[:12]
        self._snapshot_valid = True

        logger.info(f"Skill snapshot version: {self._snapshot_version} ({len(self._skills)} skills)")
        return self._snapshot_version

    def get_snapshot_version(self) -> str:
        """Get current snapshot version, computing if needed."""
        if not self._snapshot_valid:
            self._compute_snapshot_version()
        return self._snapshot_version

    def is_snapshot_valid(self, expected_version: str) -> bool:
        """Check if snapshot version matches expected (from session).

        If the version loaded with a session doesn't match the current
        registry version, the agent should rebuild its skill snapshot.
        """
        return self._snapshot_version == expected_version and self._snapshot_valid

    def check_and_refresh(self, session_snapshot_version: str | None) -> bool:
        """Check if skill snapshot is stale and needs refresh.

        Returns True if snapshot is valid and matches session version.
        Returns False if refresh is needed.

        Call this at the start of each agent run (openclaw pattern).
        """
        if session_snapshot_version is None:
            # No version stored — always refresh
            return False

        if not self._snapshot_valid:
            self._compute_snapshot_version()

        return self._snapshot_version == session_snapshot_version


def _parse_skill_md(path: Path) -> SkillMetadata:
    """Parse a SKILL.md file into a SkillMetadata dataclass.

    Format:
        # Skill Name

        Description of what this skill does.

        ## Triggers
        feed, auto-feed,喂食

        ## Examples
        "feed my baby giga"
        "auto-feed all tribe dinos"

        ## Auto-Trigger-On
        baby_born
        dino_tamed

        ## Tier
        vip
    """
    content = path.read_text()

    lines = content.strip().split("\n")
    name = lines[0].strip().lstrip("# ").strip() if lines else path.parent.name
    description = []
    triggers = []
    examples = []
    auto_trigger_on = []
    tier = "player"

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("## Triggers"):
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("##"):
                trigger_line = lines[i].strip().strip('"')
                if trigger_line:
                    triggers.extend(t for t in trigger_line.split(",") if t.strip())
                i += 1
        elif line.startswith("## Examples"):
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("##"):
                ex = lines[i].strip().strip('"')
                if ex:
                    examples.append(ex)
                i += 1
        elif line.startswith("## Auto-Trigger-On"):
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("##"):
                evt = lines[i].strip()
                if evt:
                    auto_trigger_on.append(evt)
                i += 1
        elif line.startswith("## Tier"):
            i += 1
            if i < len(lines):
                tier = lines[i].strip().lower()
                i += 1
        elif not line.startswith("#") and not line.startswith("##") and description is not None:
            if line:
                description.append(line)
        else:
            i += 1

    return SkillMetadata(
        name=name,
        description=" ".join(description),
        triggers=[t.strip() for t in triggers],
        examples=examples,
        auto_trigger_on=auto_trigger_on,
        tier_required=tier,
    )


# Global registry
_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry