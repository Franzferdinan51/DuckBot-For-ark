"""Generate a reproducible spec for the ARK DevKit in-game DuckBot UI.

This repository stores compiled `.uasset` files, which are not diff-friendly.
The manifest generated here is the repo-local source of truth for rebuilding the
same UI in the ASA DevKit or feeding a future DevKit Bridge automation layer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_manifest() -> dict:
    return {
        "mod_name": "SheldonAI",
        "ui_contract_version": 1,
        "assets": [
            {
                "name": "BP_SheldonWebSocket",
                "type": "ActorComponent",
                "parent": "ActorComponent",
                "interfaces": ["BPSecureNetworkingInterface"],
                "variables": [
                    ["SocketID", "Integer", -1],
                    ["IsConnected", "Boolean", False],
                    ["BridgeURL", "String", ""],
                    ["AuthSecret", "String", ""],
                    ["PlayerID", "String", ""],
                    ["PlayerName", "String", ""],
                    ["PlayerTier", "String", "player"],
                    ["IsAuthenticated", "Boolean", False],
                    ["PendingReplyText", "String", ""],
                ],
                "events": [
                    "On WebSocket Connected -> SendAuthMessage",
                    "On Websocket Connection Error -> retry after 5s",
                    "On WebSocket Closed -> clear auth and reply buffer",
                    "On WebSocket Message Recieved -> route auth_success/reply/stream_token/thinking/error",
                ],
            },
            {
                "name": "WBP_SheldonChat",
                "type": "WidgetBlueprint",
                "parent": "PrimalUI",
                "layout": {
                    "panel": "500x600 dark root canvas",
                    "header": ["title", "close_button"],
                    "history": ["ScrollBox", "ChatHistory VerticalBox"],
                    "input": ["EditableTextBox", "SendButton"],
                },
                "functions": [
                    "DisplayPlayerMessage(text)",
                    "ShowThinkingIndicator()",
                    "AppendStreamToken(token)",
                    "FinalizeReply(text)",
                    "DisplayError(text)",
                    "ToggleVisibilityAndInputMode()",
                ],
                "behavior": [
                    "Enter key and Send button share one send path",
                    "stream_token appends into the active assistant bubble",
                    "reply finalizes the assistant bubble and clears the typing state",
                    "error renders as a visible system row in chat history",
                ],
            },
            {
                "name": "BP_SheldonMapExtension",
                "type": "MapExtension",
                "startup": [
                    "Authority -> connect BP_SheldonWebSocket to bridge",
                    "Remote -> create WBP_SheldonChat and bind F8",
                ],
                "netexec": [
                    "Client sends chat text to server over NetExec",
                    "Server forwards bridge replies back to owning client",
                ],
            },
        ],
        "bridge_protocol": {
            "auth": {
                "type": "auth",
                "token": "SECRET",
                "player": {
                    "player_id": "EOS_ID",
                    "display_name": "NAME",
                    "tier": "player",
                    "tribe_id": "",
                    "position": {"x": 0, "y": 0, "z": 0},
                    "facing_yaw": 0.0,
                },
            },
            "player_message": {
                "type": "player_message",
                "message": "text",
                "position": {"x": 0, "y": 0, "z": 0},
                "facing_yaw": 0.0,
            },
            "responses": [
                "auth_success",
                "thinking",
                "stream_token",
                "reply",
                "error",
            ],
        },
        "notes": [
            "Desktop companion on :8444 is not a replacement for the PrimalUI widget.",
            "The in-game UI must remain PrimalUI-based and server-authoritative.",
            "Console targets require wss:// in GameUserSettings.ini.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the DuckBot in-game UI build manifest.")
    parser.add_argument(
        "--output",
        default="mod/generated/sheldon_mod_build_manifest.json",
        help="Output path for the generated manifest",
    )
    args = parser.parse_args()

    manifest = build_manifest()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
