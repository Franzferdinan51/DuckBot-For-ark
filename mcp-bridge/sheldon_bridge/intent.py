"""AI intent classifier — routes player messages to the right handler.

Inspired by DuckBotAiService in the Ark-DuckBot-Desktop client. This provides:
- Fast rule-based classification for common ARK commands
- LLM-powered classification for ambiguous cases
- Entity extraction (dino names, player names, levels, quantities)

Intent types:
  QUERY   — "what's my balance", "show me dino stats"
  COMMAND — "/spawn", "teleport to X", "kick player"
  ACTION  — "spawn me a rex", "give me kibble"
  HELP    — "help", "what can you do"
  CHAT    — casual conversation

Usage:
    classifier = IntentClassifier(llm)
    result = classifier.classify("spawn me a level 200 rex")
    # result.type = IntentType.ACTION, result.entities = {dino: "Rex", level: "200"}
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class IntentType(Enum):
    QUERY = "query"      # Info requests — what, how, show, tell me
    COMMAND = "command"  # Admin actions — spawn, teleport, kick, ban
    ACTION = "action"    # Direct spawn/give requests
    HELP = "help"        # Help requests
    CHAT = "chat"        # Casual conversation


# ─── Entity extractors ────────────────────────────────────────────────────────

DINO_ALIASES = {
    # Common aliases
    "rex": "Rex", "t-rex": "Rex", "trex": "Rex",
    "giga": "Giganotosaurus", "giganoto": "Giganotosaurus",
    "mega": "Megalodon", "megalodon": "Megalodon",
    "argy": "Argentavis", "argentavis": "Argentavis",
    "yuty": "Yutyrannus", "yutyrannus": "Yutyrannus",
    "therizino": "Therizinosaurus", "theriz": "Therizinosaurus",
    "ptera": "Pteranodon", "pteranodon": "Pteranodon",
    "raptor": "Raptor", "velo": "Velonasaur",
    "spino": "Spinosaurus", "spinosaur": "Spinosaurus",
    "bronto": "Brontosaurus", "brontosaurus": "Brontosaurus",
    "stego": "Stegosaurus", "stegosaurus": "Stegosaurus",
    "trike": "Triceratops", "triceratops": "Triceratops",
    "anky": "Ankylosaurus", "ankylosaurus": "Ankylosaurus",
}

COMMAND_WORDS = {
    "spawn", "create", "summon", "give", "teleport", "warp", "go",
    "set", "enable", "disable", "kick", "ban", "unban", "mute",
    "unmute", "slay", "warn", "broadcast", "announce",
}

QUERY_WORDS = {"what", "how", "show", "tell", "list", "find", "search", "where", "who", "which"}


@dataclass
class IntentResult:
    """Result of intent classification."""
    intent_type: IntentType
    confidence: float  # 0.0–1.0
    raw_input: str
    entities: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""

    # Parsed components (populated after classification)
    command: str = ""
    arguments: str = ""


class IntentClassifier:
    """Lightweight intent classifier for ARK player messages.

    Uses a two-phase approach:
    1. Fast rule-based check for common patterns (handles ~80% of messages)
    2. LLM classification for edge cases (ambiguous or complex queries)

    Entity extraction happens in parallel with classification.
    """

    def __init__(self, llm_provider=None):
        self._llm = llm_provider
        self._rule_cache: dict[str, IntentResult] = {}

    def classify(self, text: str) -> IntentResult:
        """Classify a player message and extract entities.

        Fast path: rule-based classification
        Slow path: LLM classification (when rule-based is uncertain)
        """
        text = text.strip()
        if not text:
            return IntentResult(IntentType.CHAT, 0.0, text, reasoning="empty input")

        # Check cache
        cache_key = text.lower()
        if cache_key in self._rule_cache:
            cached = self._rule_cache[cache_key]
            return IntentResult(
                intent_type=cached.intent_type,
                confidence=cached.confidence,
                raw_input=text,
                entities=dict(cached.entities),
                reasoning=f"[cached] {cached.reasoning}",
            )

        # Phase 1: Fast rule-based classification
        result = self._rule_based_classify(text)

        # If confidence is high enough from rules, return early
        if result.confidence >= 0.85:
            self._rule_cache[cache_key] = result
            return result

        # Phase 2: LLM classification for ambiguous cases
        if result.confidence < 0.7 and self._llm is not None:
            llm_result = self._llm_classify(text, result)
            if llm_result.confidence > result.confidence:
                return llm_result

        return result

    def _rule_based_classify(self, text: str) -> IntentResult:
        """Fast rule-based intent classification."""
        lower = text.lower()

        # Check for explicit slash commands
        if lower.startswith("/"):
            return self._classify_slash_command(text, lower)

        # Check for direct command words
        for cmd in COMMAND_WORDS:
            if lower.startswith(cmd):
                return self._classify_command(text, lower, cmd)

        # Check for query patterns
        for qword in QUERY_WORDS:
            if lower.startswith(qword) or lower.startswith(f"{qword} "):
                return self._classify_query(text, lower)

        # Check for spawn patterns
        if any(kw in lower for kw in ("spawn", "create", "summon")):
            return self._classify_action(text, lower)

        # Check for give patterns
        if "give me" in lower or "give" in lower.split()[:3]:
            return self._classify_action(text, lower)

        # Check for help
        if lower.startswith("help") or "what can you do" in lower:
            return IntentResult(IntentType.HELP, 0.95, text, reasoning="help pattern detected")

        # Check for casual chat patterns
        casual_patterns = [
            r"\b(hi|hello|hey|howdy|yo)\b",
            r"\b(thanks?|thank you|thx)\b",
            r"\b(are you|how are you|what's up)\b",
            r"\b(bye|goodbye|see ya)\b",
        ]
        for pattern in casual_patterns:
            if re.search(pattern, lower):
                return IntentResult(IntentType.CHAT, 0.85, text, reasoning="casual pattern")

        # Default: treat as chat (low confidence)
        return IntentResult(IntentType.CHAT, 0.5, text, reasoning="default to chat")

    def _classify_slash_command(self, text: str, lower: str) -> IntentResult:
        """Classify an explicit slash command like /spawn, /help."""
        parts = text.split(maxsplit=1)
        cmd = parts[0].lstrip("/").lower()
        args = parts[1] if len(parts) > 1 else ""

        # Map common slash commands
        slash_commands = {
            "spawn": IntentType.ACTION,
            "give": IntentType.ACTION,
            "spawnitem": IntentType.ACTION,
            "teleport": IntentType.COMMAND,
            "tp": IntentType.COMMAND,
            "warp": IntentType.COMMAND,
            "home": IntentType.COMMAND,
            "sethome": IntentType.COMMAND,
            "kick": IntentType.COMMAND,
            "ban": IntentType.COMMAND,
            "unban": IntentType.COMMAND,
            "mute": IntentType.COMMAND,
            "unmute": IntentType.COMMAND,
            "warn": IntentType.COMMAND,
            "broadcast": IntentType.COMMAND,
            "announce": IntentType.COMMAND,
            "help": IntentType.HELP,
            "h": IntentType.HELP,
            "stats": IntentType.QUERY,
            "balance": IntentType.QUERY,
            "info": IntentType.QUERY,
            "who": IntentType.QUERY,
        }

        intent = slash_commands.get(cmd, IntentType.COMMAND)

        # Extract entities from args
        entities = self._extract_entities(args if args else text)

        return IntentResult(
            intent_type=intent,
            confidence=0.95,
            raw_input=text,
            entities=entities,
            reasoning=f"slash command: /{cmd}",
            command=cmd,
            arguments=args,
        )

    def _classify_command(self, text: str, lower: str, cmd: str) -> IntentResult:
        """Classify a command that starts with a known command word."""
        # Extract arguments (everything after the command word)
        cmd_idx = lower.find(cmd)
        args = text[cmd_idx + len(cmd):].strip()

        entities = self._extract_entities(args if args else lower)

        # Determine specific sub-type based on context
        sub_intent = self._refine_command_intent(lower, cmd, entities)

        return IntentResult(
            intent_type=sub_intent,
            confidence=0.9,
            raw_input=text,
            entities=entities,
            reasoning=f"command word: {cmd}",
            command=cmd,
            arguments=args,
        )

    def _classify_query(self, text: str, lower: str) -> IntentResult:
        """Classify a query pattern (what, how, show, etc.)."""
        entities = self._extract_entities(text)

        # Sub-classify query types
        if any(w in lower for w in ("balance", "money", "coins", "points")):
            return IntentResult(IntentType.QUERY, 0.95, text, entities, reasoning="balance query")
        if any(w in lower for w in ("dino", "creature", "rex", "giga", "spino", "dinosaur")):
            return IntentResult(IntentType.QUERY, 0.9, text, entities, reasoning="dino query")
        if any(w in lower for w in ("player", "who is", "steam")):
            return IntentResult(IntentType.QUERY, 0.9, text, entities, reasoning="player query")
        if any(w in lower for w in ("tribe", "tribe members", "my tribe")):
            return IntentResult(IntentType.QUERY, 0.9, text, entities, reasoning="tribe query")
        if any(w in lower for w in ("server", "status", "uptime", "players online")):
            return IntentResult(IntentType.QUERY, 0.95, text, entities, reasoning="server status query")
        if any(w in lower for w in ("event", "active", "running")):
            return IntentResult(IntentType.QUERY, 0.85, text, entities, reasoning="event query")

        return IntentResult(IntentType.QUERY, 0.75, text, entities, reasoning="general query")

    def _classify_action(self, text: str, lower: str) -> IntentResult:
        """Classify an action pattern (spawn, create, give)."""
        entities = self._extract_entities(text)

        # Is it a dino spawn?
        has_level = "level" in lower or any(c.isdigit() for c in lower)
        has_spawn = any(w in lower for w in ("spawn", "create", "summon"))

        if has_spawn and (any(d in lower for d in DINO_ALIASES) or has_level):
            return IntentResult(IntentType.ACTION, 0.95, text, entities, reasoning="dino spawn action")

        # Is it an item spawn?
        if "give" in lower or "item" in lower:
            return IntentResult(IntentType.ACTION, 0.9, text, entities, reasoning="item spawn action")

        return IntentResult(IntentType.ACTION, 0.8, text, entities, reasoning="general action")

    def _refine_command_intent(self, lower: str, cmd: str, entities: dict) -> IntentType:
        """Refine a command into a more specific intent."""
        if cmd in ("spawn", "create", "summon"):
            return IntentType.ACTION
        if cmd in ("give",):
            return IntentType.ACTION
        if cmd in ("teleport", "tp", "warp", "home"):
            return IntentType.COMMAND
        if cmd in ("kick", "ban", "unban", "mute", "unmute", "slay", "warn"):
            return IntentType.COMMAND
        if cmd in ("broadcast", "announce"):
            return IntentType.COMMAND
        return IntentType.COMMAND

    def _extract_entities(self, text: str) -> dict[str, Any]:
        """Extract structured entities from natural language text."""
        entities: dict[str, Any] = {}
        lower = text.lower()
        words = text.split()

        # Extract level
        level_matches = re.findall(r'\blevel\s*(\d+)\b', lower)
        if not level_matches:
            level_matches = re.findall(r'\blvl\s*(\d+)\b', lower)
        if not level_matches:
            # Check for standalone numbers that might be levels
            for w in words:
                cleaned = w.lower().replace("lvl", "").replace("level", "")
                if cleaned.isdigit() and 1 <= int(cleaned) <= 500:
                    level_matches.append(cleaned)
                    break
        if level_matches:
            entities["level"] = max(int(l) for l in level_matches)

        # Extract quantity
        qty_matches = re.findall(r'\b(\d+)\s*(?:x|qty|quantity)?\b', lower)
        if qty_matches:
            entities["quantity"] = int(qty_matches[0])

        # Extract dino name
        for alias, full_name in DINO_ALIASES.items():
            if alias in lower:
                entities["dino"] = full_name
                break

        # Extract player name (capitalized words that aren't common commands)
        player_parts = []
        skip_next = False
        for i, w in enumerate(words):
            if skip_next:
                skip_next = False
                continue
            if w and w[0].isupper() and len(w) > 2:
                # Check it's not a common command
                if w.lower() not in COMMAND_WORDS and w.lower() not in QUERY_WORDS:
                    player_parts.append(w)
                    if i + 1 < len(words) and words[i + 1][0].isupper():
                        skip_next = True
                        continue
                    break
        if player_parts:
            entities["player"] = " ".join(player_parts)

        # Extract target player (for teleport commands)
        target_patterns = [
            r'(?:to|towards?|warp to|go to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'(?:tp|teleport)\s+(?:to\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        ]
        for pattern in target_patterns:
            match = re.search(pattern, text)
            if match:
                entities["target"] = match.group(1).strip()

        # Extract message (for broadcast/announce)
        if any(w in lower for w in ("broadcast", "announce", "tell everyone")):
            msg_match = re.search(r'(?:broadcast|announce|tell everyone)[:\s]+(.*)', lower)
            if msg_match:
                entities["message"] = msg_match.group(1).strip()

        # Extract item name
        item_patterns = [
            r'(?:give|spawn)\s+(?:me\s+)?(?:a\s+)?(?:item\s+)?(.+)',
            r'(?:want|need)\s+(\w+)',
        ]
        for pattern in item_patterns:
            match = re.search(pattern, lower)
            if match:
                item = match.group(1).strip().rstrip(" please").rstrip(" thanks")
                if item and item not in ("me", "something", "it"):
                    entities["item"] = item
                    break

        return entities

    def _llm_classify(self, text: str, rule_result: IntentResult) -> IntentResult:
        """Use LLM to classify ambiguous messages."""
        try:
            import litellm

            prompt = f"""Classify this ARK player message. Respond with JSON only:
{{"intent": "query|command|action|help|chat", "confidence": 0.0-1.0, "reasoning": "brief"}}

Message: {text}

Rule-based got: {rule_result.intent_type.value} (confidence {rule_result.confidence})
Reasoning: {rule_result.reasoning}"""

            response = litellm.completion(
                model="openrouter/anthropic/claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=100,
            )

            content = response.choices[0].message.content.strip()
            # Try to parse JSON
            if "{" in content:
                json_str = content[content.find("{"):content.rfind("}") + 1]
                import json
                data = json.loads(json_str)
                return IntentResult(
                    intent_type=IntentType(data.get("intent", rule_result.intent_type.value)),
                    confidence=float(data.get("confidence", rule_result.confidence)),
                    raw_input=text,
                    entities=rule_result.entities,
                    reasoning=f"[LLM] {data.get('reasoning', rule_result.reasoning)}",
                )
        except Exception as e:
            logger.debug(f"LLM classification failed, using rule result: {e}")

        return rule_result


# ─── Singleton ──────────────────────────────────────────────────────────────

_classifier: IntentClassifier | None = None


def get_intent_classifier() -> IntentClassifier:
    """Get the global IntentClassifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier