# DuckBot AI for ARK

DuckBot AI for ARK is an AI-assisted control stack for **ARK: Survival Ascended**. It combines a **ServerAPI C++ plugin** with a **Python bridge** that talks to an LLM and can answer ARK questions, enforce tiered permissions, and queue in-game actions.

This repo is a practical fork of the SheldonAI concept. Some Python package names still use `sheldon_bridge`, but the active runtime surfaces here are DuckBot-branded.

## What ships today

- `plugin/`: ServerAPI plugin for ASA, built in Visual Studio.
- `mcp-bridge/`: Python bridge with WebSocket server, tool registry, auth, sessions, metrics, audit logging, and LLM provider support.
- `mod/`: DevKit assets for an in-game UI path and map extension content.
- `data/`: bundled ARK knowledge data used by the bridge.

The bridge and plugin are the primary working path. The `mod/` directory is useful source material, but the repo is not just a Blueprint mod.

## Architecture

```text
ARK Server
  -> DuckBot plugin (C++ / AsaApi / ServerAPI)
  -> WebSocket connection
  -> DuckBot bridge (Python)
  -> LLM provider via LiteLLM
```

The plugin captures chat commands and game events, then forwards structured messages to the bridge. The bridge authenticates the connection, creates a per-player session, exposes only tier-appropriate tools to the model, and returns replies or queued game actions.

## Current feature set

- 39 in-game chat commands in `plugin/src/Plugin.cpp`
- 6 registered gameplay hooks for join, logout, tame, birth, death, and level-up
- permission tiers with code-enforced tool partitioning (`player`, `admin`, `superadmin`)
- knowledge tools for dinos, items, engrams, and server info
- action tools for spawn, teleport, give item, broadcast, time control, and raw console commands
- session persistence, rate limiting, audit logging, and optional semantic cache warmup
- provider support for OpenRouter, Anthropic, OpenAI, Gemini, LM Studio, MiniMax, and Ollama

## Repository layout

```text
plugin/        Visual Studio solution and C++ source
mcp-bridge/    Python package, tests, Dockerfile, config example
mod/           ASA DevKit assets (.uasset, .uplugin)
data/          ARK vanilla data and data build script
docs/          architecture, permissions, and project notes
examples/      sample config and prompt files
```

## Quick start: bridge

```powershell
cd mcp-bridge
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy config.json.example config.json
duckbot-bridge secret
duckbot-bridge run --config config.json
```

Useful commands:

- `duckbot-bridge run --config config.json`: start the WebSocket bridge
- `duckbot-bridge serve --config config.json --port 8080`: lightweight HTTP health and discovery surface
- `pytest`: run the Python test suite
- `ruff check .`
- `mypy sheldon_bridge`

Notes:

- `config.json.example` contains comments, so treat it as a template, not strict JSON.
- API keys can come from `config.json` or a local `.env` file loaded by the CLI.

## Quick start: plugin

1. Install Visual Studio 2022 with C++ desktop development tools.
2. Clone `AsaApi` as a sibling directory to this repo.
3. Open [plugin/DuckBot.sln](plugin/DuckBot.sln).
4. Build `Release x64`.
5. Copy `plugin/Binaries/Release/DuckBot.dll` into `ArkApi/Plugins/DuckBot/` on the server.

See [plugin/README.md](plugin/README.md) and [MOD_BUILD_GUIDE.md](MOD_BUILD_GUIDE.md) for the expected filesystem layout and deployment details.

## Testing

The bridge test suite lives in `mcp-bridge/tests/`.

- `test_permissions.py` covers the core trust boundary: tool visibility, validation, limits, and session isolation.
- `test_integration.py` is a real end-to-end bridge test and requires `ANTHROPIC_API_KEY`.

Run locally:

```powershell
cd mcp-bridge
pytest
pytest -k integration
```

## Configuration and security

- Bridge config template: `mcp-bridge/config.json.example`
- Example game settings: `examples/gameusersettings.example.ini`
- Security policy: [SECURITY.md](SECURITY.md)
- Permission model notes: [docs/PERMISSIONS.md](docs/PERMISSIONS.md)

Do not commit live API keys, auth secrets, server-specific config, or logs.

## Project status

The repo is past the concept stage: the Python bridge, plugin command surface, and bridge-to-game command queue are implemented. The remaining work is mostly iteration and hardening, not initial scaffolding. The codebase still carries some Sheldon-era names in docs and Python modules; that is naming debt, not a separate product.
