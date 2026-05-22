"""DuckBot-specific configuration for the MCP bridge.

Extends sheldon-bridge config with ARK: Survival Ascended specific settings.
"""

from dataclasses import dataclass

from sheldon_bridge.config import BridgeConfig as SheldonBridgeConfig
from sheldon_bridge.providers.llm import LLMConfig

# ─── ARK Game Constants ─────────────────────────────────────────────────────

ARK_SPECIES_BY_TIER = {
    "top": ["Giganotosaurus", "Titanosaur", "Megalodon", "Tusoteuthis"],
    "apex": ["Rex", "Spino", "Carno", "Allosaurus", "Therizinosaurus"],
    "utility": ["Argentavis", "Pteranodon", "Quetzal", "Thylacoleo"],
    "farm": ["Doedicurus", "Bone Fire", "Managarmr", "Mastodon"],
    "breeder": ["Michele", "Yutyrannus", "Lymantria"],
}

MAP_NAMES = [
    "TheIsland", "ScorchedEarth", "Aberration", "Extinction", "Genesis2",
    "LostIsland", "CrystalIsles", "Fjordur", "RTM", "Valguero",
]

KIBBLE_BASE_SPECIES = [
    "Dodo", "Gallimimus", "Compy", "Dimorphodon", "Pachy", "Pelagornis",
    "Archaeopteryx", "Microraptor", "Velona", "Hesperornis",
    "Troodon", "Ichthyornis", "Tapejara", "Cosmo",
]

# ─── DuckBot Config ─────────────────────────────────────────────────────────

@dataclass
class DuckBotConfig:
    """Extended config for DuckBot plugin integration."""

    # Base bridge config
    bridge: SheldonBridgeConfig

    # ARK-specific settings
    ark_map: str = "TheIsland"
    ark_cluster_id: str = ""

    # Wild dino alert settings (from tribealert command)
    wild_dino_alert_enabled: bool = True
    wild_dino_alert_min_level: int = 30
    wild_dino_alert_species: list[str] = None  # empty = all high-level

    # Tribe management
    tribe_member_auto_track: bool = True
    tribe_dino_limit: int = 500

    # AI brain settings
    ai_context_window: int = 50  # number of game events to keep in context
    ai_personality: str = "helpful_assistant"  # or "aggressive_tribe_manager", etc.

    def __post_init__(self):
        if self.wild_dino_alert_species is None:
            self.wild_dino_alert_species = ARK_SPECIES_BY_TIER["top"] + ARK_SPECIES_BY_TIER["apex"]


def load_duckbot_config(path: str = "config.json") -> DuckBotConfig:
    """Load DuckBot config from JSON with ARK-specific defaults."""
    import json
    from pathlib import Path

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    raw = json.loads(config_path.read_text())

    # Load base bridge config
    bridge_config = _load_bridge_config(raw)

    # Load DuckBot-specific config
    ark_config = raw.get("ark", {})

    return DuckBotConfig(
        bridge=bridge_config,
        ark_map=ark_config.get("map", "TheIsland"),
        ark_cluster_id=ark_config.get("cluster_id", ""),
        wild_dino_alert_enabled=ark_config.get("wild_dino_alert_enabled", True),
        wild_dino_alert_min_level=ark_config.get("wild_dino_alert_min_level", 30),
        wild_dino_alert_species=ark_config.get("wild_dino_alert_species"),
        tribe_member_auto_track=ark_config.get("tribe_member_auto_track", True),
        tribe_dino_limit=ark_config.get("tribe_dino_limit", 500),
        ai_context_window=ark_config.get("ai_context_window", 50),
        ai_personality=ark_config.get("ai_personality", "helpful_assistant"),
    )


def _load_bridge_config(raw: dict) -> SheldonBridgeConfig:
    """Load the sheldon bridge portion of the config."""
    from sheldon_bridge.config import BridgeConfig, load_config

    # Delegate to sheldon bridge loader
    return load_config()