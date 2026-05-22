"""SQLite-backed session persistence for DuckBot.

Sessions are saved to SQLite on disconnect and restored on bridge startup,
so players don't lose their conversation context after bridge restarts.

Schema:
    sessions       — player_id PK, PlayerContext, conversation, game events, tribe data
    sessions_fts   — FTS5 virtual table for session search

Usage:
    from sheldon_bridge.session_persistence import SessionStore

    store = SessionStore("data/sessions.db")
    await store.save(session)
    restored = await store.restore(player_id)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from sheldon_bridge.auth import PlayerContext
from sheldon_bridge.session import Session
from sheldon_bridge.duckbot_session import DuckBotSession, GameEvent

logger = logging.getLogger(__name__)

DB_PATH = Path("data/sessions.db")


class SessionStore:
    """SQLite session persistence layer."""

    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self._lock = asyncio.Lock()
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        async with self._get_db() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    player_id          TEXT PRIMARY KEY,
                    player_json        TEXT NOT NULL,
                    conversation_json  TEXT NOT NULL,
                    system_prompt      TEXT NOT NULL DEFAULT '',
                    total_input_tokens INTEGER NOT NULL DEFAULT 0,
                    total_output_tokens INTEGER NOT NULL DEFAULT 0,
                    total_cost         REAL NOT NULL DEFAULT 0.0,
                    created_at         REAL NOT NULL,
                    last_active        REAL NOT NULL,
                    events_json        TEXT NOT NULL DEFAULT '[]',
                    tribe_data_json    TEXT NOT NULL DEFAULT '{}',
                    updated_at         REAL NOT NULL
                )
            """)
            # FTS5 for session search — search across player name + conversation
            await db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
                    player_id,
                    display_name,
                    tribe_id,
                    conversation_text,
                    tokenize='porter unicode61'
                )
            """)
            await db.commit()
        logger.info(f"Session store initialized: {self.db_path}")

    @contextmanager
    async def _get_db(self):
        """Get a DB connection. Handles lazy init + concurrency."""
        if self._db is None:
            self._db = await aiosqlite.connect(str(self.db_path))
            self._db.row_factory = aiosqlite.Row
        yield self._db

    async def save(self, session: Session) -> None:
        """Persist a session to SQLite.

        If it's a DuckBotSession, saves game events + tribe data too.
        """
        async with self._lock:
            async with self._get_db() as db:
                player_json = json.dumps(self._player_to_dict(session.player))

                conversation = session.conversation
                conversation_json = json.dumps(conversation)

                # DuckBotSession fields if applicable
                events_json = "[]"
                tribe_data_json = "{}"
                if isinstance(session, DuckBotSession):
                    events_json = json.dumps([e.to_dict() for e in session._events])
                    tribe_data_json = json.dumps(getattr(session, "_tribe_data", {}))

                now = time.time()
                await db.execute("""
                    INSERT OR REPLACE INTO sessions (
                        player_id, player_json, conversation_json, system_prompt,
                        total_input_tokens, total_output_tokens, total_cost,
                        created_at, last_active, events_json, tribe_data_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session.player.player_id,
                    player_json,
                    conversation_json,
                    session.system_prompt,
                    session.total_input_tokens,
                    session.total_output_tokens,
                    session.total_cost,
                    session.created_at,
                    session.last_active,
                    events_json,
                    tribe_data_json,
                    now,
                ))

                # Update FTS index
                display_name = session.player.display_name
                tribe_id = session.player.tribe_id or ""
                conv_text = self._conversation_preview(conversation)

                await db.execute("""
                    INSERT OR REPLACE INTO sessions_fts (player_id, display_name, tribe_id, conversation_text)
                    VALUES (?, ?, ?, ?)
                """, (session.player.player_id, display_name, tribe_id, conv_text))

                await db.commit()

        logger.debug(f"Session saved: {session.player.player_id[:8]}...")

    def _player_to_dict(self, player: PlayerContext) -> dict[str, Any]:
        return {
            "player_id": player.player_id,
            "display_name": player.display_name,
            "tier": player.tier,
            "tribe_id": player.tribe_id,
            "position": player.position,
            "facing_yaw": player.facing_yaw,
        }

    def _conversation_preview(self, conversation: list[dict]) -> str:
        """Extract searchable text from conversation for FTS indexing."""
        parts = []
        for msg in conversation[-20:]:  # last 20 messages for preview
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 2:
                parts.append(content[:200])
        return " | ".join(parts)

    async def restore(self, player_id: str) -> Session | None:
        """Restore a session from SQLite. Returns base Session or DuckBotSession."""
        async with self._lock:
            async with self._get_db() as db:
                row = await db.execute_fetchone(
                    "SELECT * FROM sessions WHERE player_id = ?", (player_id,)
                )
                if not row:
                    return None

        return self._row_to_session(dict(row))

    def _row_to_session(self, row: dict) -> Session:
        """Convert a DB row back to a Session or DuckBotSession."""
        player_dict = json.loads(row["player_json"])
        player = PlayerContext(
            player_id=player_dict["player_id"],
            display_name=player_dict["display_name"],
            tier=player_dict["tier"],
            tribe_id=player_dict.get("tribe_id", ""),
            position=player_dict.get("position", {}),
            facing_yaw=player_dict.get("facing_yaw", 0.0),
        )

        conversation = json.loads(row["conversation_json"])

        # Determine if this was a DuckBotSession by presence of events
        events_json = row.get("events_json", "[]")
        events_list = json.loads(events_json) if events_json else []

        if events_list:
            from sheldon_bridge.duckbot_session import DuckBotSession

            base = Session(player=player)
            base.conversation = conversation
            base.system_prompt = row.get("system_prompt", "")
            base.total_input_tokens = row.get("total_input_tokens", 0)
            base.total_output_tokens = row.get("total_output_tokens", 0)
            base.total_cost = row.get("total_cost", 0.0)
            base.created_at = row.get("created_at", time.time())
            base.last_active = row.get("last_active", time.time())

            duckbot = DuckBotSession(
                base_session=base,
                max_events=50,
                tribe_data=json.loads(row.get("tribe_data_json", "{}")),
            )
            # Restore game events
            for evt_dict in events_list:
                evt = GameEvent(
                    event_type=evt_dict["event_type"],
                    data=evt_dict.get("data", {}),
                    timestamp=evt_dict.get("timestamp", time.time()),
                )
                duckbot._events.append(evt)
            return duckbot
        else:
            session = Session(player=player)
            session.conversation = conversation
            session.system_prompt = row.get("system_prompt", "")
            session.total_input_tokens = row.get("total_input_tokens", 0)
            session.total_output_tokens = row.get("total_output_tokens", 0)
            session.total_cost = row.get("total_cost", 0.0)
            session.created_at = row.get("created_at", time.time())
            session.last_active = row.get("last_active", time.time())
            return session

    async def restore_all(self) -> dict[str, Session]:
        """Restore all sessions from SQLite on bridge startup."""
        sessions = {}
        async with self._lock:
            async with self._get_db() as db:
                async for row in db.execute_fetchall("SELECT * FROM sessions"):
                    row_d = dict(row)
                    session = self._row_to_session(row_d)
                    sessions[session.player.player_id] = session
        logger.info(f"Restored {len(sessions)} sessions from SQLite")
        return sessions

    async def search(
        self,
        player_id: str,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Full-text search a player's session history.

        Returns matching message excerpts from their conversation.
        """
        async with self._lock:
            async with self._get_db() as db:
                # FTS search within player's conversation
                row = await db.execute_fetchone(
                    "SELECT conversation_json FROM sessions WHERE player_id = ?",
                    (player_id,)
                )
                if not row:
                    return []

                conversation = json.loads(row["conversation_json"])
                query_lower = query.lower()
                results = []

                for msg in conversation:
                    content = msg.get("content", "")
                    if isinstance(content, str) and query_lower in content.lower():
                        results.append({
                            "role": msg.get("role", "unknown"),
                            "content": content[:300],
                        })
                        if len(results) >= limit:
                            break

                return results

    async def delete(self, player_id: str) -> None:
        """Delete a session from the store."""
        async with self._lock:
            async with self._get_db() as db:
                await db.execute("DELETE FROM sessions WHERE player_id = ?", (player_id,))
                await db.execute("DELETE FROM sessions_fts WHERE player_id = ?", (player_id,))
                await db.commit()
        logger.debug(f"Session deleted: {player_id[:8]}...")

    async def close(self) -> None:
        """Close the DB connection."""
        if self._db:
            await self._db.close()
            self._db = None


# Global session store
_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    return _store


async def init_session_store(db_path: str | Path = DB_PATH) -> SessionStore:
    """Initialize the global session store."""
    global _store
    _store = SessionStore(db_path)
    await _store.initialize()
    return _store