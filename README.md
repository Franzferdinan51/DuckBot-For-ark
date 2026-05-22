# DuckBot AI for ARK

**Fork of [sheldon-ai-for-ark](https://github.com/ArkAscendedAI/sheldon-ai-for-ark) — converted to ServerAPI C++ for ARK Survival Ascended.**

An AI-powered in-game assistant for **ARK: Survival Ascended** where a large language model controls tribe management, dino operations, economy, moderation, and server events through natural language.

> **"DuckBot, enable wild dino alerts for my tribe"**
> **"What's the status of my tribe's dinos?"**
> **"Claim the VIP kit"**

![Status](https://img.shields.io/badge/status-converting-orange)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## Architecture

```
DuckBot Plugin (C++/ServerAPI)
    │
    ├── Hooks into AShooterGameMode + AShooterPlayerController
    ├── 39 chat commands → parse user intent
    ├── Sends game events to MCP bridge (tame, born, death, level up, chat)
    │
    ▼
DuckBot MCP Bridge (Python) ← based on sheldon-mcp-bridge
    │
    ├── WebSocket server (plugin connects as client)
    ├── Permission enforcement (role tiers: user/vip/mod/admin)
    ├── Tool registry (spawn, teleport, kit, economy, tribe ops)
    ├── Agentic loop → LLM provider
    │
    ▼
LLM Provider (Anthropic / OpenAI / Gemini / OpenRouter)
```

The **LLM is the brain** — DuckBot plugin sends structured events, the MCP bridge runs an agent loop that decides what to do and executes via tools. Players interact via `/` commands or natural language through the bridge.

---

## How It Works

1. **DuckBot plugin** intercepts game events via ServerAPI hooks and sends them to the bridge via WebSocket
2. **MCP bridge** maintains player state, enforces permissions, and runs an agent loop
3. **LLM** processes player requests and decides which tools to call
4. **Tools** execute game actions (spawn, teleport, give items, etc.) on behalf of players within their permission tier

This is a direct port/re-creation of the [ArkAscendedAI/sheldon-ai-for-ark](https://github.com/ArkAscendedAI/sheldon-ai-for-ark) concept from Blueprint/UE5 to **ServerAPI C++**, keeping the same AI bridge pattern but using AsaApi instead of DevKit.

---

## Components

| Component | Description | Technology |
|-----------|-------------|------------|
| **[DuckBot Plugin](plugin/)** | ServerAPI C++ mod. Hooks, 39 commands, MCP WebSocket client, game event emission. | C++ / AsaApi / ServerAPI |
| **[MCP Bridge](mcp-bridge/)** | Python AI agent server. Permission enforcement, tool registry, LLM integration. | Python 3.12+ |
| **[Blueprint Mod](mod/)** | (Future) In-game F8 UI for natural language input | ASA DevKit (UE5) |

---

## Building

1. Install Visual Studio 2022 with C++ desktop development workload
2. Clone ARK ServerAPI SDK as a **sibling directory**:
   ```
   cd "C:/Users/franz/OneDrive/Desktop/ARK Mod"
   git clone https://github.com/ArkServerApi/AsaApi.git
   ```
   Expected structure:
   ```
   ARK Mod/
   ├── duckbot-ai-for-ark/plugin/      ← your plugin
   │   └── DuckBot.vcxproj
   └── AsaApi/                         ← sibling SDK
       └── AsaApi/Core/Public/API/...
   ```
3. Open `plugin/DuckBot.sln` in Visual Studio 2022
4. Build → Build Solution (Release x64)
5. Output: `plugin/Binaries/Release/DuckBot.dll`
6. Copy `DuckBot.dll` to server's `ArkApi/Plugins/DuckBot/` directory

---

## MCP Bridge (Python)

The MCP bridge is based on [sheldon-mcp-bridge](https://github.com/ArkAscendedAI/sheldon-ai-for-ark/tree/main/mcp-bridge):

```bash
cd mcp-bridge
pip install -e .
sheldon-bridge run
```

### Configuration

```json
{
  "llm": {
    "provider": "openrouter",
    "api_key": "your-api-key"
  },
  "auth": {
    "shared_secret": "your-secret"
  },
  "server": {
    "host": "0.0.0.0",
    "port": 8443
  }
}
```

### LLM Providers

| Provider | Notes |
|----------|-------|
| **OpenRouter** | 200+ models, pay-per-token |
| **Anthropic** | claude-3-5-sonnet, claude-3-haiku |
| **OpenAI** | GPT-4o, GPT-4 Turbo |
| **Google** | Gemini 2.0 Flash/Pro |

### Permission Tiers

| Tier | Access |
|------|--------|
| `user` | Chat, tribe info, dino status, kits, economy |
| `vip` | Extended kits, marker management |
| `mod` | Kick, mute, slay, warp management |
| `admin` | Ban, unban, drop party, event management, AI brain control |

---

## Commands (39 total)

All commands prefixed with `/`:

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

---

## Hooks Used (6 registered)

| Hook | Purpose |
|------|---------|
| `AShooterGameMode.HandleNewPlayer_Implementation` | Player join → init player data + MCP event |
| `AShooterGameMode.HandlePlayerLogout_Implementation` | Player leave → save data + MCP event |
| `AShooterGameMode.OnDinoTamed_Implementation` | Dino tame → MCP event |
| `AShooterGameMode.OnBabyBorn_Implementation` | Breeding → MCP event |
| `AShooterGameMode.OnDinoDied_Implementation` | Dino death → MCP event |
| `AShooterPlayerController.HandlePlayerLevelUp_Implementation` | Level up → update + MCP event |

---

## Configuration

Config file: `ArkApi/Data/DuckBot/config.json`

```json
{
  "MCP": {
    "host": "localhost",
    "port": 8443,
    "auth_token": "your-secret"
  },
  "Economy": {
    "daily_reward": 100,
    "work_reward": 15,
    "work_cooldown": 300
  },
  "Teleport": {
    "cooldown": 30
  },
  "Kits": {
    "default_cooldown": 3600
  }
}
```

---

## Status

**Conversion in progress — ServerAPI C++ plugin structure complete, MCP bridge adapting from sheldon-mcp-bridge.**

- [x] 39 chat commands implemented
- [x] 6 game hooks registered
- [x] MCP WebSocket bridge client (raw Winsock2, auto-reconnect)
- [x] Economy: daily, work, balance, pay, coinflip
- [x] Teleport: home, warp, tpr, tpaccept, tphere
- [x] Moderation: kick, ban, unban, mute, unmute, slay, slayplayer
- [x] Kit system: 5 default kits with cooldown
- [x] Kibble recipes: 40+ species
- [x] Event system: start/stop/list events, drop party
- [x] JSON persistence (players, warps, markers, events)
- [ ] MCP bridge Python server (based on sheldon-mcp-bridge, in progress)
- [ ] Blueprint mod / natural language UI (future work)

---

## Reference Sources

- **[ArkAscendedAI/sheldon-ai-for-ark](https://github.com/ArkAscendedAI/sheldon-ai-for-ark)** — original Blueprint/UE5 implementation
- **[Franzferdinan51/sheldon-ai-for-ark](https://github.com/Franzferdinan51/sheldon-ai-for-ark)** — fork with MCP bridge Python code
- **[Franzferdinan51/rust-duckbot-mod](https://github.com/Franzferdinan51/rust-duckbot-mod)** — Rust/Oxide reference for RustDuckBot AI pattern
- **[ArkServerApi/AsaApi](https://github.com/ArkServerApi/AsaApi)** — ServerAPI SDK for ARK Survival Ascended

---

## License

[MIT](LICENSE)