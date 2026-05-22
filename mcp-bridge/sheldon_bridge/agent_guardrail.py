"""Tool loop guardrail — hermes-agent-inspired.

Prevents the agent from getting stuck in loops by detecting:
- Exact failure loops: same tool + identical args failing repeatedly
- Same-tool failure accumulation: any failure from the same tool family
- No-progress loops: idempotent read tools returning the same result repeatedly

Two enforcement levels:
- WARN: logs a warning but continues (default)
- HALT: stops the loop after consecutive failures (opt-in per tool)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class GuardrailDecision(Enum):
    """Decision returned by the guardrail controller."""
    ALLOW = "allow"       # Continue normally
    WARN = "warn"         # Continue but log warning
    HALT = "halt"         # Stop the loop


@dataclass
class ToolCallSignature:
    """Fingerprint of a tool call for loop detection."""
    tool_name: str
    args_hash: str  # SHA-256 of arguments (stable identifier)
    args_preview: str  # First 80 chars for logging
    timestamp: float = field(default_factory=time.time)


@dataclass
class GuardrailConfig:
    """Configurable thresholds for loop detection."""
    max_consecutive_failures: int = 3       # Same tool + same args → HALT
    max_same_tool_failures: int = 5       # Same tool (any args) → WARN then HALT
    max_no_progress_cycles: int = 3        # Idempotent tools returning same → WARN
    warn_threshold: float = 0.6            # After this fraction → start warning
    halt_enabled: bool = True             # Set False to only WARN
    # Tools that are "idempotent read" — same result means no progress
    idempotent_tools: frozenset[str] = frozenset({
        "get_player_info", "get_tribe_info", "get_server_status",
        "get_knowledge", "get_config", "search_knowledge",
    })


@dataclass
class GuardrailResult:
    """Result of a guardrail check."""
    decision: GuardrailDecision
    reason: str
    tool_name: str
    consecutive_failures: int = 0
    total_same_tool_failures: int = 0


class ToolLoopGuardrail:
    """Detects and prevents tool call loops.

    Thread-safe, stateless (no session state needed).
    Call check() before each tool execution, record() after each result.
    """

    def __init__(self, config: GuardrailConfig | None = None):
        self._config = config or GuardrailConfig()
        self._exact_loops: dict[str, int] = {}       # args_hash → failure count
        self._tool_failures: dict[str, int] = {}    # tool_name → failure count
        self._no_progress: dict[str, tuple[str, int]] = {}  # tool_name → (last_result_hash, count)
        self._last_result: dict[str, str] = {}       # tool_name → last result hash
        self._last_failure_time: dict[str, float] = {}  # tool_name → timestamp

    def _hash_args(self, args: dict) -> str:
        """Create a stable hash of tool arguments."""
        try:
            serialized = json.dumps(args, sort_keys=True, default=str)
            return hashlib.sha256(serialized.encode()).hexdigest()[:16]
        except Exception:
            return hashlib.sha256(str(args).encode()).hexdigest()[:16]

    def _preview_args(self, args: dict) -> str:
        """Create a short preview of arguments for logging."""
        try:
            serialized = json.dumps(args, sort_keys=True, default=str)
            return serialized[:80]
        except Exception:
            return str(args)[:80]

    def check(self, tool_name: str, args: dict) -> GuardrailResult:
        """Check if a tool call should be allowed.

        Call this BEFORE executing a tool. Returns a GuardrailResult
        with the decision and reason.
        """
        args_hash = self._hash_args(args)
        signature = f"{tool_name}:{args_hash}"

        # Check exact-loop failures (same tool + same args)
        exact_count = self._exact_loops.get(signature, 0)

        # Check same-tool accumulation
        tool_count = self._tool_failures.get(tool_name, 0)

        # Check no-progress (idempotent tools returning same result)
        no_progress_count = 0
        if tool_name in self._config.idempotent_tools:
            last_result = self._last_result.get(tool_name, "")
            if last_result and args_hash == last_result:
                no_progress_count = self._no_progress.get(tool_name, ("", 0))[1]
                no_progress_count += 1

        # Decision logic
        if exact_count >= self._config.max_consecutive_failures:
            self._log_warning(tool_name, "EXACT_LOOP", f"Same tool+args failed {exact_count}x consecutively")
            return GuardrailResult(
                decision=GuardrailDecision.HALT if self._config.halt_enabled else GuardrailDecision.WARN,
                reason=f"Same tool '{tool_name}' with identical arguments failed {exact_count}x. Stopping to prevent infinite loop.",
                tool_name=tool_name,
                consecutive_failures=exact_count,
                total_same_tool_failures=tool_count,
            )

        if tool_count >= self._config.max_same_tool_failures:
            self._log_warning(tool_name, "TOOL_ACCUMULATION", f"Tool '{tool_name}' failed {tool_count}x total")
            return GuardrailResult(
                decision=GuardrailDecision.HALT if self._config.halt_enabled else GuardrailDecision.WARN,
                reason=f"Tool '{tool_name}' has failed {tool_count}x across different calls. Circuit breaker triggered.",
                tool_name=tool_name,
                consecutive_failures=exact_count,
                total_same_tool_failures=tool_count,
            )

        if no_progress_count >= self._config.max_no_progress_cycles:
            self._log_warning(tool_name, "NO_PROGRESS", f"Idempotent tool '{tool_name}' returned same result {no_progress_count}x")
            return GuardrailResult(
                decision=GuardrailDecision.WARN,
                reason=f"Tool '{tool_name}' is returning the same result repeatedly (no progress after {no_progress_count} cycles). Continuing but flagging.",
                tool_name=tool_name,
                consecutive_failures=exact_count,
                total_same_tool_failures=tool_count,
            )

        if exact_count >= self._config.max_consecutive_failures * self._config.warn_threshold:
            return GuardrailResult(
                decision=GuardrailDecision.WARN,
                reason=f"Tool '{tool_name}' has failed {exact_count}x with same args — watching closely.",
                tool_name=tool_name,
                consecutive_failures=exact_count,
                total_same_tool_failures=tool_count,
            )

        return GuardrailResult(
            decision=GuardrailDecision.ALLOW,
            reason="Allowed",
            tool_name=tool_name,
        )

    def record(self, tool_name: str, args: dict, result: str | dict, error: bool) -> None:
        """Record a tool execution result for loop tracking.

        Call this AFTER a tool executes, with the result or error message.
        """
        args_hash = self._hash_args(args)
        signature = f"{tool_name}:{args_hash}"

        if error:
            # Increment exact loop counter
            self._exact_loops[signature] = self._exact_loops.get(signature, 0) + 1
            # Increment tool accumulation counter
            self._tool_failures[tool_name] = self._tool_failures.get(tool_name, 0) + 1
            self._last_failure_time[tool_name] = time.time()
        else:
            # Success — reset exact loop counter (not tool accumulation)
            self._exact_loops.pop(signature, None)
            # For idempotent tools, track result hash for no-progress detection
            if tool_name in self._config.idempotent_tools:
                result_hash = self._hash_args({"result": str(result)[:200]})
                if self._last_result.get(tool_name) == result_hash:
                    current = self._no_progress.get(tool_name, ("", 0))
                    self._no_progress[tool_name] = (result_hash, current[1] + 1)
                else:
                    self._no_progress[tool_name] = (result_hash, 0)
                self._last_result[tool_name] = result_hash

    def reset(self, tool_name: str | None = None) -> None:
        """Reset failure counters for a tool (call on successful execution).

        If tool_name is None, resets all.
        """
        if tool_name is None:
            self._exact_loops.clear()
            self._tool_failures.clear()
            self._no_progress.clear()
            self._last_result.clear()
            self._last_failure_time.clear()
        else:
            # Reset all signatures for this tool
            self._exact_loops = {k: v for k, v in self._exact_loops.items() if not k.startswith(f"{tool_name}:")}
            self._tool_failures.pop(tool_name, None)
            self._no_progress.pop(tool_name, None)
            self._last_result.pop(tool_name, None)
            self._last_failure_time.pop(tool_name, None)

    def _log_warning(self, tool_name: str, loop_type: str, detail: str) -> None:
        logger.warning(f"[Guardrail] {loop_type} — {detail}")

    def get_stats(self) -> dict[str, Any]:
        """Get current guardrail stats for debugging/monitoring."""
        return {
            "exact_loops": dict(self._exact_loops),
            "tool_failures": dict(self._tool_failures),
            "no_progress": {k: v[1] for k, v in self._no_progress.items()},
            "config": {
                "max_consecutive_failures": self._config.max_consecutive_failures,
                "max_same_tool_failures": self._config.max_same_tool_failures,
                "max_no_progress_cycles": self._config.max_no_progress_cycles,
                "halt_enabled": self._config.halt_enabled,
            },
        }


# Global instance per player — stored in agent's run context
_guardrails: dict[str, ToolLoopGuardrail] = {}


def get_guardrail(player_id: str, config: GuardrailConfig | None = None) -> ToolLoopGuardrail:
    """Get or create a guardrail for a player session."""
    if player_id not in _guardrails:
        _guardrails[player_id] = ToolLoopGuardrail(config)
    return _guardrails[player_id]


def clear_guardrail(player_id: str) -> None:
    """Clear a player's guardrail (call on session end/reset)."""
    _guardrails.pop(player_id, None)