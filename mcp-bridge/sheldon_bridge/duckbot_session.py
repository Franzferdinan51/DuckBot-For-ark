"""DuckBot session — extends sheldon-bridge Session with ARK game event context.

This layer wraps the base Session to provide:

1. **Game event memory** — the last N game events are kept in the conversation
   context so the AI knows what's happening on the server (e.g., "a Rex was
   tamed", "player X disconnected"). This mirrors how openclaw's memory-host-sdk
   keeps recent context for agent decision-making.

2. **Tribe context** — tribe name, member list, active dinos, breeding status
   are injected into the system prompt so the AI has structured world knowledge.

3. **ARK-aware token budgeting** — when truncating conversation, game events are
   given higher retention priority than older chat messages.

Usage:
    from sheldon_bridge.duckbot_session import DuckBotSession

    session = DuckBotSession(player_context, max_events=50)
    session.add_game_event("dino_tamed", {"species": "Rex", "level": 200, ...})
    session.add_user_message("How are my tribe's dinos?")
    messages = session.get_messages()  # includes game event context + tribe info
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sheldon_bridge.auth import PlayerContext
from sheldon_bridge.session import Session

logger = logging.getLogger(__name__)

# ─── ARK Game Event Types ───────────────────────────────────────────────────

ARK_GAME_EVENTS = [
    "player_connected",
    "player_disconnected",
    "dino_tamed",
    "baby_born",
    "dino_died",
    "player_level_up",
    "wild_dino_alert",
    "tribe_member_joined",
    "tribe_member_left",
    "tribe_ally_joined",
    "structure_damaged",
    "structure_destroyed",
]


@dataclass
class GameEvent:
    """A single game event from the DuckBot C++ plugin."""
    event_type: str          # e.g. "dino_tamed", "player_connected"
    data: dict[str, Any]      # event payload
    timestamp: float = field(default_factory=time.time)
    steam_id: int = 0
    player_name: str = ""

    def to_conversation_string(self) -> str:
        """Format this event as a string for the AI conversation context."""
        return f"[Game Event] {self._format_type()}: {self._format_data()}"

    def _format_type(self) -> str:
        return self.event_type.replace("_", " ").title()

    def _format_data(self) -> str:
        parts = []
        data = dict(self.data)  # copy so we don't modify original
        # Remove internal fields
        data.pop("event", None)
        data.pop("timestamp", None)
        for key, value in data.items():
            parts.append(f"{key}={value}")
        return ", ".join(parts)


class DuckBotSession:
    """Session wrapper that adds ARK game event context to a sheldon-bridge Session.

    DuckBotSession wraps the base Session and adds a game event ring buffer.
    When building conversation context for the LLM, game events are injected
    as system-level observations so the AI can reason about what's happening
    on the server.

    The base Session handles the normal chat conversation. This layer handles
    the ARK-specific world state.
    """

    def __init__(
        self,
        base_session: Session,
        max_events: int = 50,
        tribe_data: dict | None = None,
    ):
        self._base = base_session
        self._events: list[GameEvent] = []
        self._max_events = max_events
        self._tribe_data = tribe_data or {}
        self._persist_events = []  # high-priority events that survive truncation

    # ─── Event Management ──────────────────────────────────────────────────

    def add_game_event(
        self,
        event_type: str,
        data: dict,
        steam_id: int = 0,
        player_name: str = "",
    ) -> None:
        """Record a game event from the DuckBot C++ plugin.

        Events are stored in a ring buffer of max_events. Older events are
        dropped when the buffer is full, unless they were marked as persistent.
        """
        event = GameEvent(
            event_type=event_type,
            data=data,
            steam_id=steam_id,
            player_name=player_name,
        )
        self._events.append(event)

        # Trim if over capacity (unless it's a persistent event)
        if len(self._events) > self._max_events:
            # Keep last max_events, drop oldest
            self._events = self._events[-self._max_events:]

        logger.debug(f"Game event recorded: {event_type} — {data}")

    def mark_event_persistent(self, event_type: str, data: dict) -> None:
        """Mark an event type/data combo as high-priority (survives truncation).

        Use this for events the AI absolutely must remember, like a Giganotosaurus
        alert or a tribe member being offline.
        """
        event = GameEvent(
            event_type=event_type,
            data=data,
            timestamp=time.time(),
        )
        self._persist_events.append(event)

    def get_recent_events(self, count: int = 10) -> list[GameEvent]:
        """Get the N most recent game events."""
        return self._events[-count:] if self._events else []

    # ─── Tribe Context ─────────────────────────────────────────────────────

    def update_tribe_data(self, tribe_data: dict) -> None:
        """Update tribe context (name, members, dinos, etc.).

        This is called when the plugin sends a tribe sync message.
        The data is stored and injected into the system prompt.
        """
        self._tribe_data = tribe_data

    def get_tribe_context(self) -> str:
        """Build a tribe context string for the AI system prompt."""
        if not self._tribe_data:
            return ""

        parts = ["## Tribe Context"]
        if name := self._tribe_data.get("name"):
            parts.append(f"Tribe: {name}")
        if members := self._tribe_data.get("members"):
            parts.append(f"Members: {len(members)}")
            online = [m for m in members if m.get("online")]
            if online:
                parts.append(f"Online: {', '.join(m.get('name', '?') for m in online)}")
        if dinos := self._tribe_data.get("dinos"):
            parts.append(f"Active dinos: {len(dinos)}")
            high_value = [d for d in dinos if d.get("level", 0) >= 150]
            if high_value:
                species = [d.get("species", "?") for d in high_value[:5]]
                parts.append(f"High-level dinos: {', '.join(species)}")
        if alerts := self._tribe_data.get("active_alerts", []):
            parts.append(f"Active alerts: {len(alerts)}")
            for alert in alerts[-3:]:
                parts.append(f"  - {alert}")

        return "\n".join(parts)

    # ─── Conversation Build ───────────────────────────────────────────────

    def build_system_prompt(self, base_prompt: str) -> str:
        """Build the full system prompt including tribe context and game events.

        Order of composition:
        1. Base personality prompt
        2. Tribe context block
        3. Recent game events (last 10)
        4. Persistent events (Giga alerts, etc.)
        """
        parts = [base_prompt]

        # Tribe context
        tribe_ctx = self.get_tribe_context()
        if tribe_ctx:
            parts.append(f"\n\n{tribe_ctx}")

        # Recent game events
        recent = self.get_recent_events(10)
        if recent:
            event_lines = ["## Recent Server Events"]
            for evt in recent:
                event_lines.append(f"- {evt.to_conversation_string()}")
            parts.append("\n" + "\n".join(event_lines))

        # Persistent events
        if self._persist_events:
            persist_lines = ["## Important Events"]
            for evt in self._persist_events[-5:]:  # last 5 persistent
                persist_lines.append(f"- {evt.to_conversation_string()}")
            parts.append("\n" + "\n".join(persist_lines))

        return "\n\n".join(parts)

    def get_messages(self) -> list[dict]:
        """Get conversation history with game events injected as system context."""
        messages = list(self._base.conversation)

        # Find and update the system prompt with ARK context
        system_updated = False
        for i, msg in enumerate(messages):
            if msg.get("role") == "system" and not system_updated:
                # Inject ARK context into existing system message
                original_content = msg.get("content", "")
                ark_context = self._build_ark_context_string()
                if ark_context:
                    msg["content"] = original_content + "\n\n" + ark_context
                    system_updated = True
                break

        if not system_updated:
            # No system message found, inject one at the start
            ark_context = self._build_ark_context_string()
            if ark_context:
                messages.insert(0, {"role": "system", "content": ark_context})

        return messages

    def _build_ark_context_string(self) -> str:
        """Build the ARK-specific context string for the system prompt."""
        parts = ["## ARK Server Context"]

        # Tribe
        if self._tribe_data:
            parts.append(self.get_tribe_context())

        # Recent events
        recent = self.get_recent_events(10)
        if recent:
            event_lines = ["Recent events:"]
            for evt in recent:
                event_lines.append(f"  {evt.to_conversation_string()}")
            parts.append("\n".join(event_lines))

        return "\n".join(parts)

    # ─── Truncation ────────────────────────────────────────────────────────

    def truncate_to_budget(self, max_tokens: int, reserve: int = 8192) -> None:
        """Truncate conversation, prioritizing game events over old chat.

        This is called when the LLM context window is exceeded. Unlike the
        base session truncation, this version:
        1. Always keeps the system prompt
        2. Always keeps recent game events (last 5)
        3. Drops oldest chat messages first
        """
        target = max_tokens - reserve

        def estimate_tokens(msg: dict) -> int:
            content = msg.get("content", "")
            if isinstance(content, str):
                return len(content) // 4
            return 50

        # Collect message buckets
        system_msgs = []
        game_event_msgs = []
        chat_msgs = []

        for msg in self._base.conversation:
            if msg.get("role") == "system":
                # Check if it's a game event system message
                content = msg.get("content", "")
                if "[Game Event]" in content or "ARK Server Context" in content:
                    game_event_msgs.append(msg)
                else:
                    system_msgs.append(msg)
            else:
                chat_msgs.append(msg)

        # Always keep system + recent game events
        system_tokens = sum(estimate_tokens(m) for m in system_msgs)
        game_event_tokens = sum(estimate_tokens(m) for m in game_event_msgs[-5:])

        # Calculate how many chat tokens we can afford
        available = target - system_tokens - game_event_tokens
        if available < 0:
            available = 0

        # Keep newest chat messages that fit
        kept_chat = []
        current_tokens = 0
        for msg in reversed(chat_msgs):
            msg_tokens = estimate_tokens(msg)
            if current_tokens + msg_tokens <= available:
                kept_chat.insert(0, msg)
                current_tokens += msg_tokens
            else:
                break  # keep what fits, drop the rest

        # Rebuild conversation
        self._base.conversation = system_msgs + game_event_msgs[-5:] + kept_chat
        logger.debug(
            f"Truncated: {len(chat_msgs)} → {len(kept_chat)} chat msgs, "
            f"{sum(estimate_tokens(m) for m in chat_msgs)} → {current_tokens} tokens"
        )

    # ─── Delegate to base session ──────────────────────────────────────────

    @property
    def player(self) -> PlayerContext:
        return self._base.player

    @property
    def lock(self):
        return self._base.lock

    def add_user_message(self, content: str) -> None:
        self._base.add_user_message(content)

    def add_assistant_message(self, message: dict) -> None:
        self._base.add_assistant_message(message)

    def add_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        self._base.add_tool_result(tool_call_id, name, content)

    def track_usage(self, input_tokens: int, output_tokens: int, cost: float) -> None:
        self._base.track_usage(input_tokens, output_tokens, cost)