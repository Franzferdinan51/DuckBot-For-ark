import importlib

import pytest

from sheldon_bridge.tools.registry import ToolRegistry, tool
from sheldon_bridge.world_context import WorldContext


@pytest.mark.asyncio
async def test_get_players_near_tribe_base_includes_players_in_radius():
    ctx = WorldContext()
    await ctx.set_tribe_base("tribe_1", "Alpha", {"x": 0.0, "y": 0.0, "z": 0.0}, radius=150.0)
    await ctx.update_player("p1", display_name="Owner", tribe_id="tribe_1", position={"x": 10.0, "y": 0.0, "z": 0.0})
    await ctx.update_player("p2", display_name="Visitor", tribe_id="tribe_2", position={"x": 20.0, "y": 0.0, "z": 0.0})
    await ctx.update_player("p3", display_name="FarAway", tribe_id="tribe_3", position={"x": 500.0, "y": 0.0, "z": 0.0})

    players = await ctx.get_players_near_tribe_base("tribe_1")

    assert {player.player_id for player in players} == {"p1", "p2"}


@pytest.mark.asyncio
async def test_get_dinos_near_tribe_base_uses_recorded_positions():
    ctx = WorldContext()
    await ctx.set_tribe_base("tribe_1", "Alpha", {"x": 0.0, "y": 0.0, "z": 0.0}, radius=200.0)
    await ctx.record_dino_event(
        event="wild_dino_alert",
        species="Rex",
        tribe_id="tribe_1",
        position={"x": 25.0, "y": 0.0, "z": 0.0},
        level=150,
        actor_id="d1",
    )
    await ctx.record_dino_event(
        event="wild_dino_alert",
        species="Raptor",
        tribe_id="tribe_1",
        position={"x": 500.0, "y": 0.0, "z": 0.0},
        level=30,
        actor_id="d2",
    )

    dinos = await ctx.get_dinos_near_tribe_base("tribe_1", species_filter=["Rex"])

    assert len(dinos) == 1
    assert dinos[0]["species"] == "Rex"
    assert dinos[0]["actor_id"] == "d1"


def test_default_admin_registry_exposes_spatial_tools(clear_tool_registry):
    import sheldon_bridge.tools.registry as registry_mod

    importlib.reload(registry_mod)

    @tool(tier="admin", description="players in radius")
    def get_players_in_radius() -> dict:
        return {}

    @tool(tier="admin", description="players near tribe base")
    def get_players_near_tribe_base() -> dict:
        return {}

    @tool(tier="admin", description="dinos near tribe base")
    def get_dinos_near_tribe_base() -> dict:
        return {}

    registry = ToolRegistry()
    registry.discover()

    admin_tools = {tool.name for tool in registry.get_tools_for_tier("admin")}

    assert "get_players_in_radius" in admin_tools
    assert "get_players_near_tribe_base" in admin_tools
    assert "get_dinos_near_tribe_base" in admin_tools
