# Sheldon AI for ARK — with DuckBot ServerAPI Plugin

**Fork of [sheldon-ai-for-ark](https://github.com/Franzferdinan51/sheldon-ai-for-ark) with DuckBot C++ plugin.**

An open-source, in-game AI assistant for **ARK: Survival Ascended** with two complementary components:

1. **DuckBot Plugin** — ServerAPI C++ plugin with 39 chat commands, tribe management, economy, and moderation (this repo)
2. **sheldon-ai-for-ark Blueprint Mod** — Natural language AI assistant via the same MCP bridge

> **"Hey Sheldon, where do Rexes spawn on Ragnarok?"**
> **"Spawn a level 200 female Yutyrannus 40 feet in front of me."**
> **"What kibble do I need for an Argentavis?"**

![Status](https://img.shields.io/badge/status-in%20development-orange)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## Two Ways to Use This Project

### Option A — DuckBot Plugin (ServerAPI/C++)

For server operators who want a **command-driven** admin bot with no AI overhead:

- 39 slash commands (`/tribe`, `/kits`, `/kit`, `/bal`, `/daily`, `/work`, `/home`, `/warp`, `/kibble`, etc.)
- Tribe management, dino tracking, breeding alerts
- Economy: daily rewards, work rewards, balance, pay, coinflip
- Teleport system: home, warp, tpr, tpaccept, tphere
- Moderation: kick, ban, unban, mute, unmute, slay, slayplayer
- Kit system with cooldowns and permission gates
- Event system and drop party hosting
- AI brain status (`/aibrain`, `/aireset`)
- MCP WebSocket bridge to sheldon-mcp-bridge for AI events
- Built with **ServerAPI / AsaApi** (NOT Oxide)

**See [plugin/README.md](plugin/README.md) for full DuckBot plugin docs.**

---

### Option B — sheldon-ai-for-ark Blueprint Mod (DevKit/UE5)

For server operators who want a **natural language** AI assistant:

- Press **F8** in-game, type any question or command in plain English
- ARK encyclopedia, dino stats, spawn locations, taming strategies
- Breeding calculators, crafting recipes, map navigation
- Server info, rates, rules, online players
- Dino spawning, item giving, teleportation — all from plain English
- Multi-LLM support: Anthropic, OpenAI, Google Gemini, OpenRouter
- Permission system enforced in deterministic code (LLM cannot bypass)

---

## How They Work Together

```
DuckBot Plugin (C++/ServerAPI)              sheldon-ai-for-ark Blueprint Mod
        │                                            │
        │         ┌──────────────────┐              │
        │         │sheldon-mcp-bridge│◄─────────────┘
        └────────►│  (Python server) │
        WebSocket │                  │         WebSocket
                   │  Permission     │
                   │  enforcement    │
                   │  Tool registry  │──────────► LLM Provider
                   │  Agentic loop   │         (Anthropic/OpenAI/Gemini)
                   └──────────────────┘
```

- Both DuckBot plugin and sheldon Blueprint Mod connect to the **same sheldon-mcp-bridge**
- DuckBot sends game events (tame, born, death, level up) to the bridge via WebSocket
- sheldon Blueprint handles natural language queries via the same bridge
- Tribe data from DuckBot feeds the AI brain via MCP events

---

## Quick Start

### 1. Install the Bridge

```bash
pip install sheldon-bridge
```

Or with Docker:

```bash
docker pull ghcr.io/arkascendedai/sheldon-ai-for-ark:latest
```

### 2. Configure

```bash
sheldon-bridge init
```

```json
{
  "llm": {
    "provider": "openrouter",
    "api_key": "your-api-key-here"
  },
  "auth": {
    "shared_secret": "auto-generated-during-init"
  }
}
```

See `examples/config.advanced.json` for all available options.

### 3. Install the Mod

Subscribe to **SheldonAI** on CurseForge and add it to your server's mod list.

Add to your `GameUserSettings.ini`:

```ini
[SheldonAI]
WebSocketURL=wss://your-server:8443/sheldon
AuthSecret=your-generated-secret
```

### 4. Run

```bash
sheldon-bridge run
```

---

## DuckBot Plugin Commands (39 total)

All commands prefixed with `/` (ServerAPI chat command system):

| Command | Description | Permission |
|---------|-------------|------------|
| `/tribe` | Tribe overview: members, tames, alerts | use |
| `/tdinos` | List tribe's active tames | use |
| `/tribealert` | Wild dino alerts near tribe | use |
| `/dinos` | Show tracked dinos | use |
| `/kits` | Show available kits | use |
| `/kit [name]` | Claim a kit (with cooldown) | use |
| `/bal` | Show your balance | use |
| `/pay [player] [amount]` | Pay another player | use |
| `/daily` | Claim daily reward (24h) | use |
| `/work` | Claim work reward (5min cooldown) | use |
| `/home` | Teleport to saved home position | use |
| `/sethome` | Save home position | use |
| `/tpr [player]` | Send teleport request | use |
| `/tpaccept` | Accept teleport request | use |
| `/warp [name]` | Teleport to warp | use |
| `/setwarp [name]` | Create warp | mod |
| `/marker add\|list\|remove` | Manage tribe markers | use |
| `/gridmap` | Show grid map with all waypoints | use |
| `/kick [player]` | Kick player | mod |
| `/ban [player]` | Ban player | admin |
| `/unban [player]` | Unban player | admin |
| `/mute [player]` | Mute player | mod |
| `/unmute [player]` | Unmute player | mod |
| `/slay [player]` | Slay player's dinos | mod |
| `/slayplayer [player]` | Slay player | mod |
| `/tphere [player]` | Teleport player to you | mod |
| `/feed` | Auto-feed your tribe dinos | use |
| `/coinflip [wager]` | Flip a coin (wager from balance) | use |
| `/breeds` | Recent breed alerts and mutations | use |
| `/kibble [species]` | Kibble recipe guide (40+ species) | use |
| `/aibrain` | AI brain status and MCP bridge state | use |
| `/aireset` | Reset AI context | use |
| `/event start\|stop\|list` | Manage events | admin |
| `/events` | Show active events | use |
| `/drop [count] [radius]` | Host drop party | admin |
| `/save` | Save all data | admin |
| `/reload` | Reload config | admin |
| `/status` | Plugin status and stats | admin |
| `/help` | Show all commands | use |

**See [plugin/README.md](plugin/README.md) for full building instructions.**

---

## Features

### For Players (No Admin Required)
- **ARK Encyclopedia** — dino stats, spawn locations, taming strategies, breeding info
- **Taming & Breeding Calculators** — "How much mutton for a level 150 Rex?"
- **Crafting Recipes** — ingredients, workstations, engram requirements
- **Map Navigation** — "Where's the nearest metal-rich area?"
- **Personal Tame Tracking** — "Where's my Argentavis?"
- **Server Info** — rates, rules, mods, online players

### For Admins (Tier-Based Permissions)
- **Natural Language Server Control** — "Make it morning", "Spawn me a Rex"
- **World Queries** — "How many wild Rexes on the map?"
- **Player Management** — teleport, give items, kick, ban
- **Dino Spawning** — species, level, gender, position — all from plain English
- **Broadcasts** — "Tell everyone the server restarts in 15 minutes"

### Architecture Highlights
- **Multi-LLM Support** — Anthropic, OpenAI, Google Gemini, or any model via OpenRouter
- **Inviolable Permission System** — enforced in deterministic code, not by the LLM ([details](docs/PERMISSIONS.md))
- **Cross-Platform** — PC, Xbox, PS5 via CurseForge cloud cooking
- **Custom UI** — dedicated in-game chat panel (F8), no admin required

---

## Components

| Component | Description | Technology |
|-----------|-------------|------------|
| **[DuckBot Plugin](plugin/)** | ServerAPI C++ mod with 39 commands, hooks, MCP bridge client | C++ / AsaApi / ServerAPI |
| **[Sheldon Bridge](mcp-bridge/)** | Standalone AI agent server. Permission enforcement, agentic loop, multi-provider LLM support. | Python 3.12+ |
| **[SheldonAI Mod](mod/)** | In-game Blueprint mod. Custom UI, WebSocket client, game queries, command execution. | ASA DevKit (UE5) |
| **[Data](data/)** | ARK knowledge base — dinos, items, recipes, maps. Queryable by the LLM via tools. | JSON |

---

## Permission System

Sheldon uses a **three-layer permission model** where the LLM is treated as an untrusted component. Permissions are enforced in deterministic code — no amount of prompt injection or social engineering can bypass them.

| Layer | Role | Trust Level |
|-------|------|-------------|
| **Mod** | Identity attestation (HMAC-signed player context) | Trusted |
| **Bridge** | Permission enforcement (tool partitioning, validation, rate limiting) | Trusted |
| **LLM** | Natural language understanding and UX | Untrusted |

The LLM never sees tools above the player's permission tier. Admin tools don't exist in a regular player's session — there's nothing to exploit.

**[Full Permission Architecture →](docs/PERMISSIONS.md)**

---

## Supported LLM Providers

| Provider | Configuration | Notes |
|----------|--------------|-------|
| **OpenRouter** | `"provider": "openrouter"` | 200+ models, pay-per-token, recommended for flexibility |
| **Anthropic** | `"provider": "anthropic"` | Anthropic models directly |
| **OpenAI** | `"provider": "openai"` | GPT-4o, GPT-4 Turbo |
| **Google** | `"provider": "gemini"` | Gemini 2.0 Flash/Pro |

Swap providers by changing two fields in your config. All providers use native tool/function calling — no prompt-based hacks.

---

## Customization

### Personality

Create a `personality.md` file with your assistant's character:

```markdown
You are a helpful, knowledgeable ARK assistant. You speak with
enthusiasm about dinosaurs and prehistoric survival.
```

### Server Context

Drop markdown files into your `server-context/` directory to give the AI knowledge about your specific server — mods, rules, custom configurations, lore. The bridge loads these at startup.

### Custom Data

Add JSON files to `data/custom/` for mod-specific dinos, items, or locations. The lookup tools automatically search custom data alongside vanilla.

---

## Documentation

| Document | Description |
|----------|-------------|
| [DuckBot Plugin README](plugin/README.md) | Full DuckBot ServerAPI plugin docs (39 commands, hooks, building) |
| [Architecture](docs/ARCHITECTURE.md) | System design, communication protocol, component overview |
| [Permissions](docs/PERMISSIONS.md) | Security model, tier enforcement, attack vector analysis |
| [Open Source](docs/OPEN-SOURCE.md) | Repository structure, distribution, extensibility |

---

## License

[MIT](LICENSE) — use it however you want.