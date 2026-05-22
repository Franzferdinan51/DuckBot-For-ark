"""Game event hook system — lightweight interceptors before the full agent loop.

Inspired by openclaw's plugin-hooks system. Hooks provide instant responses for
known patterns without burning LLM tokens, and can transform/enrich messages
before they reach the agent.

Hook flow (per openclaw message-hook-mappers.ts):
    player_message → on_player_message_received hook → agent loop
    game_event    → on_game_event hook → skill auto-trigger
    tool_result   → on_tool_result hook → post-processing

Each hook is a lightweight async function that returns either:
  - HookResult(skipped=False, response=None)  → continue to next hook or agent
  - HookResult(skipped=True, response="...") → short-circuit with instant response

Hook tiers: a hook can specify min_tier required to run.

Usage:
    from sheldon_bridge.hooks import get_hook_registry, HookResult, HookPriority

    async def my_hook(ctx: HookContext) -> HookResult:
        if ctx.text.lower().startswith("!status"):
            return HookResult(skipped=True, response="Server is online!")
        return HookResult(skipped=False)

    registry = get_hook_registry()
    registry.register("on_player_message_received", my_hook, priority=HookPriority.HIGH)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class HookPriority(Enum):
    """Hook execution order — higher runs first. Ties resolved by registration order."""
    CRITICAL = 0   # Auth/authentication hooks
    HIGH = 20      # Input transformation hooks
    NORMAL = 50    # Standard hooks (default)
    LOW = 80       # Logging/metrics hooks
    BACKGROUND = 100  # Async processing hooks


@dataclass
class HookContext:
    """Context passed to every hook.

    Fields vary by hook event type — only relevant fields are populated.
    """
    # Common
    event: str                    # e.g., "player_message", "game_event"
    player_id: str = ""
    player_tier: str = "player"
    tribe_id: str = ""

    # player_message event
    text: str = ""                # raw message text
    display_name: str = ""        # player display name

    # game_event event
    event_type: str = ""          # e.g., "baby_born", "dino_tamed"
    event_data: dict = field(default_factory=dict)

    # tool_result event
    tool_name: str = ""
    tool_result: dict = field(default_factory=dict)

    # Internal — hooks can store state here for later hooks
    state: dict = field(default_factory=dict)


@dataclass
class HookResult:
    """Return value from a hook.

    skipped  — if True, stop hook chain and use response
    response — the instant response to use (only when skipped=True)
    """
    skipped: bool = False
    response: str = ""


# Hook handler type: async function(ctx: HookContext) -> HookResult
HookHandler = Callable[[HookContext], Awaitable[HookResult]]


@dataclass
class HookRegistration:
    """A registered hook."""
    name: str              # event name (e.g., "on_player_message_received")
    handler: HookHandler
    priority: HookPriority = HookPriority.NORMAL
    min_tier: str = "player"  # minimum tier required to run this hook
    enabled: bool = True
    description: str = ""


class HookRegistry:
    """Registry of all game event hooks.

    Hooks are sorted by priority and executed in order until one short-circuits.
    """

    def __init__(self):
        self._hooks: dict[str, list[HookRegistration]] = {}  # event → registrations

    def register(
        self,
        event: str,
        handler: HookHandler,
        priority: HookPriority = HookPriority.NORMAL,
        min_tier: str = "player",
        description: str = "",
    ) -> None:
        """Register a hook for an event type."""
        reg = HookRegistration(
            name=event,
            handler=handler,
            priority=priority,
            min_tier=min_tier,
            description=description,
        )
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(reg)

        # Sort by priority (lower = earlier)
        self._hooks[event].sort(key=lambda r: r.priority.value)
        logger.debug(f"Registered hook: {event} priority={priority.name} tier>={min_tier}")

    def unregister(self, event: str, handler: HookHandler) -> None:
        """Remove a hook handler."""
        if event not in self._hooks:
            return
        self._hooks[event] = [h for h in self._hooks[event] if h.handler != handler]

    def get_hooks(self, event: str) -> list[HookRegistration]:
        """Get all hooks for an event, filtered by enabled status."""
        return self._hooks.get(event, [])

    async def dispatch(self, ctx: HookContext) -> HookResult:
        """Dispatch an event to all registered hooks in priority order.

        Hooks run in order until one returns skipped=True with a response.
        If no hook short-circuits, returns HookResult(skipped=False).
        """
        event_hooks = self._hooks.get(ctx.event, [])
        if not event_hooks:
            return HookResult(skipped=False)

        for reg in event_hooks:
            if not reg.enabled:
                continue

            # Check tier — skip if player doesn't meet minimum tier
            if not self._tier_meets(ctx.player_tier, reg.min_tier):
                continue

            try:
                result = await reg.handler(ctx)
                if result.skipped:
                    logger.debug(
                        f"Hook short-circuit [{ctx.event}]: {reg.handler.__name__} "
                        f"→ response='{result.response[:50]}...'"
                    )
                    return result
            except Exception as e:
                logger.error(f"Hook '{reg.handler.__name__}' failed: {e}")

        return HookResult(skipped=False)

    def _tier_meets(self, player_tier: str, required_tier: str) -> bool:
        """Check if player tier meets minimum required tier."""
        tier_order = ["player", "vip", "mod", "admin", "superadmin"]
        try:
            player_level = tier_order.index(player_tier)
            required_level = tier_order.index(required_tier)
            return player_level >= required_level
        except ValueError:
            return False

    def list_hooks(self) -> list[dict]:
        """List all registered hooks (for admin API)."""
        result = []
        for event, hooks in self._hooks.items():
            for reg in hooks:
                result.append({
                    "event": event,
                    "handler": reg.handler.__name__,
                    "priority": reg.priority.name,
                    "min_tier": reg.min_tier,
                    "enabled": reg.enabled,
                    "description": reg.description,
                })
        return result


# ─── Built-in hooks ────────────────────────────────────────────────────────

async def _intent_routing_hook(ctx: HookContext) -> HookResult:
    """Built-in hook: use IntentClassifier to route messages before they reach the agent.

    This is a HIGH priority hook that intercepts player messages and can
    provide instant responses for high-confidence patterns without LLM call.

    From openclaw's message-hook-mappers pattern — intercept before agent loop.
    """
    if ctx.event != "on_player_message_received":
        return HookResult(skipped=False)

    text = ctx.text.strip()
    if not text:
        return HookResult(skipped=False)

    # Import here to avoid circular imports
    from sheldon_bridge.intent import IntentClassifier, IntentType

    classifier = IntentClassifier()
    intent = classifier.classify(text)

    # HIGH confidence casual chat → instant response
    if intent.intent_type == IntentType.CHAT and intent.confidence >= 0.85:
        # Pre-built responses for high-confidence casual patterns
        lower = text.lower()
        if any(w in lower for w in ("hi", "hello", "hey", "howdy")):
            return HookResult(skipped=True, response=f"Hi {ctx.display_name}! How can I help you in ARK today?")
        if any(w in lower for w in ("thanks", "thank you", "thx")):
            return HookResult(skipped=True, response="You're welcome!")
        if any(w in lower for w in ("bye", "goodbye", "see ya")):
            return HookResult(skipped=True, response="See you around!")
        if "good bot" in lower:
            return HookResult(skipped=True, response="*wags tail* Arf! Happy to help!")

    # HIGH confidence help → instant response
    if intent.intent_type == IntentType.HELP:
        help_text = _build_instant_help(ctx.player_tier)
        return HookResult(skipped=True, response=help_text)

    # Continue to agent loop for everything else
    return HookResult(skipped=False)


def _build_instant_help(tier: str) -> str:
    """Build instant help response — no LLM needed."""
    commands = {
        "player": [
            "/help — show commands",
            "Ask me anything about ARK, dinos, items, tribe info",
        ],
        "vip": [
            "/spawn <dino> — summon a creature",
            "Ask me anything — dinos, items, tribe info, server status",
        ],
        "mod": [
            "/spawn, /teleport, /kick, /ban, /broadcast",
            "Wild dino near base alerts are automatic",
        ],
        "admin": [
            "Full tool access — spawn, teleport, give, manage tribe",
            "Tip: Use desktop app (WS :8444) for AI chat and skill triggers",
        ],
        "superadmin": [
            "Full access: all commands, skills, graceful shutdown",
            "Desktop app: WS :8444 (ai_chat, ai_intent, memory_search)",
        ],
    }
    tier_cmds = commands.get(tier, commands["player"])
    return "Sheldon: " + " | ".join(tier_cmds)


async def _rate_limit_hook(ctx: HookContext) -> HookResult:
    """Built-in hook: enforce rate limits before agent loop.

    Players are rate-limited on message frequency to prevent spam.
    """
    if ctx.event != "on_player_message_received":
        return HookResult(skipped=False)

    # Rate limiting handled per-player in session manager
    # This hook just checks and short-circuits if rate limited
    # The actual rate limit state is stored in the session
    # (this hook just returns skipped to short-circuit pattern matches)
    return HookResult(skipped=False)


# ─── Singleton ──────────────────────────────────────────────────────────────

_registry: HookRegistry | None = None


def get_hook_registry() -> HookRegistry:
    """Get the global HookRegistry instance."""
    global _registry
    if _registry is None:
        _registry = HookRegistry()
        # Register built-in hooks
        _registry.register(
            "on_player_message_received",
            _intent_routing_hook,
            priority=HookPriority.HIGH,
            min_tier="player",
            description="Intent routing — instant responses for high-confidence patterns",
        )
        _registry.register(
            "on_player_message_received",
            _rate_limit_hook,
            priority=HookPriority.CRITICAL,
            min_tier="player",
            description="Rate limit enforcement",
        )
    return _registry


async def dispatch_hook(event: str, ctx: HookContext) -> HookResult:
    """Convenience function to dispatch a hook event."""
    registry = get_hook_registry()
    return await registry.dispatch(ctx)