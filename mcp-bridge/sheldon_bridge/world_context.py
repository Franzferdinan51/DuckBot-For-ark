"""Global world state tracker for spatial awareness.

Tracks all connected players and their positions, plus tribe bases,
so that spatial query tools can answer "dinos near tribe base" or
"players within 500u of me" style questions.

This runs entirely in-memory in the bridge. It is not persisted
across restarts (player positions update on reconnect).

Usage:
    from sheldon_bridge.world_context import WorldContext, get_world_context

    ctx = get_world_context()
    ctx.update_player_position(player_id, position, facing_yaw)
    ctx.get_players_in_radius(position, radius=1000)
    ctx.get_tribe_base(tribe_id)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TrackedPlayer:
    """A player with live position data."""
    player_id: str
    display_name: str
    tribe_id: str
    position: dict[str, float]  # {"x": ..., "y": ..., "z": ...}
    facing_yaw: float = 0.0
    last_update: float = field(default_factory=time.time)
    steam_id: str = ""


@dataclass
class TrackedDinoEvent:
    """A dino-related event with optional location data."""
    event: str
    species: str
    tribe_id: str
    position: dict[str, float]
    level: int = 0
    actor_id: str = ""
    observed_at: float = field(default_factory=time.time)


@dataclass
class TribeBase:
    """A tribe's home base center (set by tribe leader or auto-detected)."""
    tribe_id: str
    tribe_name: str
    position: dict[str, float]  # center point
    radius: float = 500.0  # default tribe territory radius in game units


class WorldContext:
    """Thread-safe global world state tracker."""

    def __init__(self):
        self._players: dict[str, TrackedPlayer] = {}
        self._tribe_bases: dict[str, TribeBase] = {}
        self._dino_events: list[TrackedDinoEvent] = []
        self._lock = asyncio.Lock()

    # ─── Player Tracking ─────────────────────────────────────────────────

    async def update_player(
        self,
        player_id: str,
        display_name: str = "",
        tribe_id: str = "",
        position: dict[str, float] | None = None,
        facing_yaw: float = 0.0,
        steam_id: str = "",
    ) -> None:
        """Update or insert a player's tracked state."""
        async with self._lock:
            if player_id in self._players:
                p = self._players[player_id]
                p.position = position if position is not None else p.position
                p.facing_yaw = facing_yaw
                p.tribe_id = tribe_id or p.tribe_id
                p.display_name = display_name or p.display_name
                p.last_update = time.time()
            else:
                self._players[player_id] = TrackedPlayer(
                    player_id=player_id,
                    display_name=display_name or "Unknown",
                    tribe_id=tribe_id or "",
                    position=position or {"x": 0, "y": 0, "z": 0},
                    facing_yaw=facing_yaw,
                    steam_id=steam_id,
                )

    async def remove_player(self, player_id: str) -> None:
        async with self._lock:
            self._players.pop(player_id, None)

    async def get_player(self, player_id: str) -> TrackedPlayer | None:
        async with self._lock:
            return self._players.get(player_id)

    async def get_all_players(self) -> list[TrackedPlayer]:
        async with self._lock:
            return list(self._players.values())

    async def get_players_in_radius(
        self,
        center: dict[str, float],
        radius: float,
        tribe_id: str | None = None,
    ) -> list[TrackedPlayer]:
        """Find all tracked players within radius game-units of center.

        Args:
            center: {"x": ..., "y": ..., "z": ...}
            radius: distance in game units (ARK uses Unreal Units, ~1u ≈ 1cm)
            tribe_id: optional filter to only players in a specific tribe
        """
        results = []
        cx, cy, cz = center.get("x", 0), center.get("y", 0), center.get("z", 0)
        r2 = radius * radius

        async with self._lock:
            for p in self._players.values():
                if tribe_id and p.tribe_id != tribe_id:
                    continue
                dx = p.position.get("x", 0) - cx
                dy = p.position.get("y", 0) - cy
                dz = p.position.get("z", 0) - cz
                if dx * dx + dy * dy + dz * dz <= r2:
                    results.append(p)

        return results

    async def get_nearest_players(
        self,
        center: dict[str, float],
        count: int = 5,
        exclude_player_id: str = "",
    ) -> list[TrackedPlayer]:
        """Get the N nearest players to a position."""
        async with self._lock:
            players = [p for p in self._players.values() if p.player_id != exclude_player_id]

        cx, cy, cz = center.get("x", 0), center.get("y", 0), center.get("z", 0)
        players.sort(
            key=lambda p: (p.position.get("x", 0) - cx) ** 2
            + (p.position.get("y", 0) - cy) ** 2
            + (p.position.get("z", 0) - cz) ** 2
        )
        return players[:count]

    # ─── Tribe Base ──────────────────────────────────────────────────────

    async def set_tribe_base(
        self,
        tribe_id: str,
        tribe_name: str,
        position: dict[str, float],
        radius: float = 500.0,
    ) -> None:
        """Set or update a tribe's base location."""
        async with self._lock:
            self._tribe_bases[tribe_id] = TribeBase(
                tribe_id=tribe_id,
                tribe_name=tribe_name,
                position=position,
                radius=radius,
            )

    async def get_tribe_base(self, tribe_id: str) -> TribeBase | None:
        async with self._lock:
            return self._tribe_bases.get(tribe_id)

    async def get_dinos_near_tribe_base(
        self,
        tribe_id: str,
        species_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return dinos near a tribe's base (from game event history).

        This queries recent dino_tamed/baby_born events from all sessions
        that have position data near the tribe base. Only works for dinos
        the bridge has seen through game events.
        """
        base = await self.get_tribe_base(tribe_id)
        if not base:
            return []

        species_allow = {species.lower() for species in species_filter or []}
        cx = base.position.get("x", 0.0)
        cy = base.position.get("y", 0.0)
        cz = base.position.get("z", 0.0)
        r2 = base.radius * base.radius
        results: list[dict[str, Any]] = []

        async with self._lock:
            for event in self._dino_events:
                if species_allow and event.species.lower() not in species_allow:
                    continue
                dx = event.position.get("x", 0.0) - cx
                dy = event.position.get("y", 0.0) - cy
                dz = event.position.get("z", 0.0) - cz
                if dx * dx + dy * dy + dz * dz > r2:
                    continue
                results.append(
                    {
                        "event": event.event,
                        "species": event.species,
                        "tribe_id": event.tribe_id,
                        "position": event.position,
                        "level": event.level,
                        "actor_id": event.actor_id,
                        "observed_at": event.observed_at,
                    }
                )

        return results

    async def get_players_near_tribe_base(
        self,
        tribe_id: str,
    ) -> list[TrackedPlayer]:
        """Get all players within tribe base territory."""
        base = await self.get_tribe_base(tribe_id)
        if not base:
            return []
        return await self.get_players_in_radius(
            base.position,
            base.radius,
        )

    async def record_dino_event(
        self,
        event: str,
        species: str,
        tribe_id: str,
        position: dict[str, float] | None = None,
        level: int = 0,
        actor_id: str = "",
    ) -> None:
        """Store a dino event so spatial tools can inspect recent sightings."""
        if not position:
            return

        async with self._lock:
            self._dino_events.append(
                TrackedDinoEvent(
                    event=event,
                    species=species,
                    tribe_id=tribe_id,
                    position=position,
                    level=level,
                    actor_id=actor_id,
                )
            )
            if len(self._dino_events) > 500:
                self._dino_events = self._dino_events[-500:]

    # ─── Stats ────────────────────────────────────────────────────────────

    async def get_stats(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "tracked_players": len(self._players),
                "tribe_bases": len(self._tribe_bases),
                "tracked_dino_events": len(self._dino_events),
                "players": [
                    {
                        "player_id": p.player_id[:8] + "...",
                        "display_name": p.display_name,
                        "tribe_id": p.tribe_id,
                        "position": p.position,
                    }
                    for p in self._players.values()
                ],
            }


# Global instance
_world_ctx: WorldContext | None = None


def get_world_context() -> WorldContext:
    global _world_ctx
    if _world_ctx is None:
        _world_ctx = WorldContext()
    return _world_ctx
