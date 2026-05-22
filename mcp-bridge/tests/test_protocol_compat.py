import asyncio
import json
from types import SimpleNamespace

import pytest

from sheldon_bridge.admin_api import AdminServer, AdminSession


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, payload: str):
        self.sent.append(json.loads(payload))


def make_admin():
    return AdminServer(
        config=SimpleNamespace(
            shared_secret="test-secret-that-is-long-enough",
            admin_port=8444,
            ark={},
        ),
        game_server_ref=None,
    )


def test_admin_auth_success_payload_includes_legacy_player_shape():
    admin = make_admin()
    payload = admin._build_auth_success_payload(
        session_id="desktop_client",
        server_info={"status": "ok"},
        legacy_player={"id": "desktop_client", "name": "ArkDuckBot", "tier": "admin"},
    )
    assert payload["type"] == "auth_success"
    assert payload["player"]["id"] == "desktop_client"
    assert payload["player"]["name"] == "ArkDuckBot"
    assert payload["tier"] == "admin"


@pytest.mark.parametrize("message,expected", [
    ({"request_id": 7}, 7),
    ({"id": 11}, 11),
    ({}, None),
])
def test_admin_server_extract_request_id_supports_legacy_id(message, expected):
    admin = make_admin()
    assert admin._extract_request_id(message) == expected


def test_admin_server_with_request_id_sets_both_fields():
    admin = make_admin()
    payload = admin._with_request_id({"type": "reply"}, 42)
    assert payload["request_id"] == 42
    assert payload["id"] == 42


@pytest.mark.asyncio
async def test_admin_server_routes_legacy_player_message(monkeypatch):
    admin = make_admin()
    session = AdminSession(id="desktop_client", websocket=FakeWebSocket(), authorized=True)
    called = {}

    async def fake_legacy_player_chat(session_arg, query, request_id):
        called["query"] = query
        called["request_id"] = request_id

    monkeypatch.setattr(admin, "_legacy_player_chat", fake_legacy_player_chat)

    await admin._handle_message(
        {"type": "player_message", "message": "hello", "id": 5},
        session,
    )

    assert called == {"query": "hello", "request_id": 5}


@pytest.mark.asyncio
async def test_admin_server_legacy_ping_gets_pong():
    admin = make_admin()
    session = AdminSession(id="desktop_client", websocket=FakeWebSocket(), authorized=True)

    await admin._handle_message({"type": "ping"}, session)

    assert session.websocket.sent
    assert session.websocket.sent[0]["type"] == "pong"
