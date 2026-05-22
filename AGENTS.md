# Repository Guidelines

## Project Structure & Module Organization
This repo has three active surfaces:

- `mcp-bridge/`: Python 3.11+ service that hosts the AI bridge, tool registry, auth, sessions, and tests.
- `plugin/`: ARK ServerAPI C++ plugin (`DuckBot.sln`, `src/*.cpp`, `src/*.h`) built with Visual Studio against a sibling `AsaApi/` checkout.
- `mod/`: ASA DevKit assets and `.uasset` content. Treat these as editor-managed binaries, not hand-edited text files.

Supporting material lives in `data/` (game data JSON and build scripts), `docs/` (architecture, permissions), and `examples/` (sample configs).

## Build, Test, and Development Commands
- `cd mcp-bridge; pip install -e ".[dev]"`: install the bridge with test and lint dependencies.
- `cd mcp-bridge; pytest`: run the Python test suite.
- `cd mcp-bridge; ruff check .`: lint Python code.
- `cd mcp-bridge; mypy sheldon_bridge`: run type checks on the bridge package.
- `cd mcp-bridge; duckbot-bridge run`: start the local bridge server.
- Open [`plugin/DuckBot.sln`](/C:/Users/franz/OneDrive/Desktop/ARK%20Mod/duckbot-ai-for-ark/plugin/DuckBot.sln) in Visual Studio 2022 and build `Release x64`: produces `plugin/Binaries/Release/DuckBot.dll`.
- `python data/scripts/build_data.py`: rebuild derived data files when source data changes.

## Coding Style & Naming Conventions
Use 4-space indentation in Python and C++. Python follows PEP 8 with type hints; `ruff` is the enforced style baseline and `pyproject.toml` sets a 100-character line length. Keep Python modules `snake_case`, classes `PascalCase`, and constants `UPPER_SNAKE_CASE`. Match the existing plugin style in `plugin/src/` for command handlers, hooks, and bridge wrappers.

## Testing Guidelines
Python tests live under `mcp-bridge/tests/` and use `pytest` with `pytest-asyncio`. Name test files `test_*.py` and keep new tests close to the behavior they cover, especially auth, permissions, and bridge integration. For plugin changes, include manual verification notes covering command flow, WebSocket connectivity, and server deployment paths.

## Commit & Pull Request Guidelines
Recent history uses short, imperative commit subjects like `Add ARK vanilla data files` and `Enhance desktop admin API with AI-powered commands`. Keep subjects direct and scoped to one change. PRs should explain the affected surface (`mcp-bridge`, `plugin`, or `mod`), list test or build steps run, link the issue when applicable, and include screenshots only for DevKit/UI changes.

## Security & Configuration Tips
Do not commit live API keys, auth secrets, or server-specific configs. Start from `examples/` and `mcp-bridge/config.json.example`, then keep real values in local config files or environment variables. Review [`SECURITY.md`](/C:/Users/franz/OneDrive/Desktop/ARK%20Mod/duckbot-ai-for-ark/SECURITY.md) before reporting permission or auth vulnerabilities.
