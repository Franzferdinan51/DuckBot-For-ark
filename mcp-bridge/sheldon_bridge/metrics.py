"""DuckBot bridge health and metrics module.

Tracks bridge health, LLM usage, tool call rates, and player engagement.
Mirrors openclaw's observability approach for the MCP bridge layer.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ─── Metrics ─────────────────────────────────────────────────────────────

@dataclass
class LLUMetrics:
    """LLM usage metrics."""
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    errors: int = 0
    last_used: float = 0.0

    def record(self, input_tokens: int, output_tokens: int, cost: float) -> None:
        self.total_requests += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost += cost
        self.last_used = time.time()


@dataclass
class ToolMetrics:
    """Tool call metrics."""
    call_count: int = 0
    error_count: int = 0
    total_duration_ms: float = 0.0
    last_called: float = 0.0

    def record(self, duration_ms: float, error: bool = False) -> None:
        self.call_count += 1
        if error:
            self.error_count += 1
        self.total_duration_ms += duration_ms
        self.last_called = time.time()

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / self.call_count if self.call_count > 0 else 0.0


@dataclass
class PlayerMetrics:
    """Per-player engagement metrics."""
    player_id: str
    messages_sent: int = 0
    tool_calls: int = 0
    commands_used: int = 0
    first_seen: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    total_cost: float = 0.0

    def record_message(self, cost: float = 0.0) -> None:
        self.messages_sent += 1
        self.last_active = time.time()
        if cost > 0:
            self.total_cost += cost

    def record_tool(self) -> None:
        self.tool_calls += 1
        self.last_active = time.time()

    def record_command(self) -> None:
        self.commands_used += 1
        self.last_active = time.time()


class BridgeMetrics:
    """Bridge-wide metrics and health tracking.

    Collects:
    - LLM usage (requests, tokens, cost)
    - Tool call counts and latencies
    - Per-player engagement
    - Event processing rates
    - Bridge health status
    """

    def __init__(self):
        self._llm = LLUMetrics()
        self._tool_metrics: dict[str, ToolMetrics] = defaultdict(ToolMetrics)
        self._player_metrics: dict[str, PlayerMetrics] = defaultdict(
            lambda: PlayerMetrics(player_id="unknown")
        )
        self._event_counts: dict[str, int] = defaultdict(int)
        self._bridge_start = time.time()
        self._connected_players: set[str] = set()
        self._plugin_connected: bool = False

    # ─── LLM ─────────────────────────────────────────────────────────────

    def record_llm(self, input_tokens: int, output_tokens: int, cost: float) -> None:
        self._llm.record(input_tokens, output_tokens, cost)

    def record_llm_error(self) -> None:
        self._llm.errors += 1

    # ─── Tools ────────────────────────────────────────────────────────────

    def record_tool_call(self, tool_name: str, duration_ms: float, error: bool = False) -> None:
        self._tool_metrics[tool_name].record(duration_ms, error)

    # ─── Players ─────────────────────────────────────────────────────────

    def record_player_message(self, player_id: str, cost: float = 0.0) -> None:
        if player_id not in self._player_metrics:
            self._player_metrics[player_id] = PlayerMetrics(player_id=player_id)
        self._player_metrics[player_id].record_message(cost)

    def record_player_tool(self, player_id: str) -> None:
        if player_id not in self._player_metrics:
            self._player_metrics[player_id] = PlayerMetrics(player_id=player_id)
        self._player_metrics[player_id].record_tool()

    def record_player_command(self, player_id: str) -> None:
        if player_id not in self._player_metrics:
            self._player_metrics[player_id] = PlayerMetrics(player_id=player_id)
        self._player_metrics[player_id].record_command()

    def set_player_online(self, player_id: str) -> None:
        self._connected_players.add(player_id)

    def set_player_offline(self, player_id: str) -> None:
        self._connected_players.discard(player_id)

    # ─── Game Events ──────────────────────────────────────────────────────

    def record_game_event(self, event_type: str) -> None:
        self._event_counts[event_type] += 1

    # ─── Plugin Status ────────────────────────────────────────────────────

    def set_plugin_connected(self, connected: bool) -> None:
        self._plugin_connected = connected

    # ─── Health Check ────────────────────────────────────────────────────

    def get_health(self) -> dict[str, Any]:
        """Get bridge health snapshot for /status command and monitoring."""
        uptime_seconds = time.time() - self._bridge_start
        active_players = len(self._connected_players)
        total_players = len(self._player_metrics)

        # Check if LLM was used recently (last 5 minutes)
        llm_stale = (time.time() - self._llm.last_used) > 300 if self._llm.last_used else True

        # Tool health: check for tools with high error rates
        tool_health = {}
        for name, metrics in self._tool_metrics.items():
            error_rate = metrics.error_count / metrics.call_count if metrics.call_count > 0 else 0
            tool_health[name] = {
                "calls": metrics.call_count,
                "error_rate": round(error_rate, 3),
                "avg_ms": round(metrics.avg_duration_ms, 1),
            }

        return {
            "bridge": {
                "uptime_seconds": round(uptime_seconds, 1),
                "plugin_connected": self._plugin_connected,
                "active_players": active_players,
                "total_players_seen": total_players,
            },
            "llm": {
                "total_requests": self._llm.total_requests,
                "total_input_tokens": self._llm.total_input_tokens,
                "total_output_tokens": self._llm.total_output_tokens,
                "total_cost_usd": round(self._llm.total_cost, 4),
                "errors": self._llm.errors,
                "stale": llm_stale,
                "last_used": self._llm.last_used,
            },
            "event_counts": dict(self._event_counts),
            "tool_health": tool_health,
            "top_players": self._get_top_players(5),
        }

    def _get_top_players(self, count: int) -> list[dict]:
        """Get most active players by message count."""
        sorted_players = sorted(
            self._player_metrics.values(),
            key=lambda p: p.messages_sent,
            reverse=True,
        )
        return [
            {
                "player_id": p.player_id,
                "messages": p.messages_sent,
                "tool_calls": p.tool_calls,
                "last_active": round(p.last_active, 1),
            }
            for p in sorted_players[:count]
        ]

    def get_player_summary(self, player_id: str) -> dict[str, Any] | None:
        """Get metrics for a specific player."""
        if player_id not in self._player_metrics:
            return None
        p = self._player_metrics[player_id]
        return {
            "player_id": p.player_id,
            "messages": p.messages_sent,
            "tool_calls": p.tool_calls,
            "commands_used": p.commands_used,
            "total_cost_usd": round(p.total_cost, 4),
            "first_seen": round(p.first_seen, 1),
            "last_active": round(p.last_active, 1),
            "online": player_id in self._connected_players,
        }


# Global metrics instance
_metrics: BridgeMetrics | None = None


def get_metrics() -> BridgeMetrics:
    global _metrics
    if _metrics is None:
        _metrics = BridgeMetrics()
    return _metrics