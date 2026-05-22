"""Skill bundles — hermes-agent-inspired.

A skill bundle is a YAML file that groups multiple skills under one
slash-command trigger. When the AI invokes a bundle, all contained
skills are loaded together.

Example: /tribe-management loads all tribe-related tools at once.
Bundle files live in skills/bundles/ and are discovered at startup.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

BUNDLE_DIR = Path(__file__).parent.parent / "skills" / "bundles"

# Characters invalid in bundle slugs (for sanitization)
_SLUG_INVALID = re.compile(r"[^a-z0-9\-]")
_MULTI_HYPHEN = re.compile(r"-+")


@dataclass
class SkillBundle:
    """A named collection of skills that load together."""
    name: str
    slug: str  # normalized trigger (e.g., "tribe-management")
    description: str
    skills: list[str]  # list of skill names to load
    instruction: str = ""  # optional extra guidance injected above skill bodies
    author: str = "DuckBot"
    version: str = "1.0.0"


@dataclass
class BundleManifest:
    """Parsed bundle file (raw structure)."""
    name: str
    slug: str
    description: str = ""
    skills: list[str] = field(default_factory=list)
    instruction: str = ""


def _slugify(name: str) -> str:
    """Normalize a bundle name into a URL-safe slug.

    'Tribe Management' -> 'tribe-management'
    'RAID!!Alert!!' -> 'raid-alert'
    """
    slug = name.lower().replace(" ", "-").replace("_", "-")
    slug = _SLUG_INVALID.sub("", slug)
    slug = _MULTI_HYPHEN.sub("-", slug).strip("-")
    return slug


class BundleRegistry:
    """Registry of skill bundles discovered from YAML files.

    Bundles are loaded at startup from skills/bundles/.
    Each bundle maps to one AI-callable trigger (e.g., /tribe-management).
    """

    def __init__(self):
        self._bundles: dict[str, SkillBundle] = {}  # slug → SkillBundle
        self._by_name: dict[str, SkillBundle] = {}  # original name → SkillBundle

    def discover(self, bundle_dir: Path | None = None) -> None:
        """Discover and load all bundle YAML files from the bundles directory."""
        if bundle_dir is None:
            bundle_dir = BUNDLE_DIR

        if not bundle_dir.exists():
            logger.info(f"Bundle directory not found: {bundle_dir}")
            return

        for path in bundle_dir.glob("*.yaml"):
            try:
                bundle = self._load_bundle(path)
                if bundle:
                    self._bundles[bundle.slug] = bundle
                    self._by_name[bundle.name] = bundle
                    logger.info(f"Loaded bundle: {bundle.slug} ({len(bundle.skills)} skills)")
            except Exception as e:
                logger.error(f"Failed to load bundle {path}: {e}")

    def _load_bundle(self, path: Path) -> SkillBundle | None:
        """Load a single bundle YAML file."""
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not raw:
            return None

        name = raw.get("name", path.stem)
        slug = raw.get("slug") or _slugify(name)
        description = raw.get("description", "")
        skills = raw.get("skills", [])
        instruction = raw.get("instruction", "") or raw.get("guidance", "")

        if not skills:
            logger.warning(f"Bundle '{slug}' has no skills, skipping")
            return None

        return SkillBundle(
            name=name,
            slug=slug,
            description=description,
            skills=skills,
            instruction=instruction,
        )

    def get(self, slug: str) -> SkillBundle | None:
        """Get a bundle by slug."""
        return self._bundles.get(slug)

    def get_by_name(self, name: str) -> SkillBundle | None:
        """Get a bundle by original name (case-insensitive)."""
        return self._by_name.get(name)

    def all(self) -> list[SkillBundle]:
        """List all registered bundles."""
        return list(self._bundles.values())

    def to_llm_format(self) -> list[dict]:
        """Format all bundles for LLM injection."""
        return [
            {
                "name": b.slug,
                "description": b.description,
                "skills": b.skills,
                "example": f'"/{b.slug}"',
            }
            for b in self._bundles.values()
        ]

    def resolve_bundle(self, slug: str) -> tuple[list[dict], list[str]]:
        """Resolve a bundle slug to (skill_metadata_list, missing_skills).

        Returns a tuple of:
        - List of skill metadata dicts for each valid skill
        - List of skill names that weren't found

        The skill metadata is used to inject skill content into the prompt.
        """
        bundle = self.get(slug)
        if not bundle:
            return [], [slug]

        from sheldon_bridge.skills.registry import get_skill_registry

        registry = get_skill_registry()
        valid_skills = []
        missing = []

        for skill_name in bundle.skills:
            skill = registry.get(skill_name)
            if skill:
                valid_skills.append({
                    "name": skill.meta.name,
                    "description": skill.meta.description,
                    "triggers": skill.meta.triggers,
                    "examples": skill.meta.examples,
                })
            else:
                missing.append(skill_name)

        return valid_skills, missing


# Global registry
_bundle_registry: BundleRegistry | None = None


def get_bundle_registry() -> BundleRegistry:
    global _bundle_registry
    if _bundle_registry is None:
        _bundle_registry = BundleRegistry()
    return _bundle_registry