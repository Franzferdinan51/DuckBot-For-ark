# DuckBot AI Plugin for ARK

**ServerAPI C++ plugin for ARK Survival Ascended — fork of [sheldon-ai-for-ark](https://github.com/Franzferdinan51/sheldon-ai-for-ark).**

This is a ServerAPI (AsaApi) C++ plugin that adds full command-driven tribe management, economy, and AI agent integration to ARK, running alongside the existing sheldon-ai-for-ark Blueprint mod.

---

## Framework

- **ServerAPI / AsaApi** — The C++ mod loader for ARK Survival Ascended
- **NOT** Oxide — Oxide does NOT support ASA
- Plugin class: `AShooterPlayerController`, `AShooterGameMode`
- Hook system: `DECLARE_HOOK` macro + `AsaApi::GetHooks().SetHook()`
- Commands: `AsaApi::GetCommands().AddChatCommand()` (chat) / `.AddConsoleCommand()` / `.AddRconCommand()`
- Permissions: `AsaApi::GetPermissions().UserHasPermission()`
- Player API: `AsaApi::GetApiUtils()` — `SendServerMessage`, `SendNotification`, `GetWorld`, `FindPlayerBySteamId`, etc.
- Teleport: `pc->SetActorLocation(FVector, ...)` directly on `AShooterPlayerController`
- Cheat commands: `AsaApi::GetCommands().ExecuteCommand(FString)` for dino spawn, item give

---

## Commands (39 total)

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

---

## Architecture

```
DuckBot Plugin (C++/ServerAPI)
    │
    ├── Tracks tribe members, dinos, breeding events via hooks
    ├── Handles all command parsing and execution
    ├── Sends events to MCP bridge (tame, born, death, level up, etc.)
    │
    ▼
sheldon-mcp-bridge (Python)
    │
    ├── Permission enforcement
    ├── Tool registry (game commands, spawn, teleport)
    ├── LLM integration (Anthropic/OpenAI/Gemini/OpenRouter)
    │
    ▼
sheldon-ai-for-ark Blueprint Mod
```

The plugin uses `DECLARE_HOOK` macros to intercept game events and `AsaApi::GetCommands().AddChatCommand()` to register all 39 commands. Events are sent to the sheldon MCP bridge via WebSocket for AI processing.

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

**All TODO items completed — plugin is fully implemented.**

- [x] 39 chat commands with complete implementations
- [x] 6 game hooks registered (join, leave, tame, born, died, levelup)
- [x] MCP bridge WebSocket client (raw Winsock2, auto-reconnect, RFC 6455)
- [x] Economy: daily (24h), work (5min), balance, pay, coinflip
- [x] Teleport: home, warp, sethome, setwarp, tpr, tpaccept, tphere
- [x] Moderation: kick, ban, unban, mute, unmute, slay, slayplayer
- [x] Kit system: 5 default kits with cooldown + permission gates
- [x] Kibble recipes for 40+ species
- [x] Event system: start/stop/list events
- [x] Drop party command
- [x] JSON persistence (players, warps, markers, kit cooldowns, events)
- [x] Permission checks via AsaApi
- [x] MCP event senders for all 6 hooks

---

## Integration with sheldon-ai-for-ark

This plugin **extends** the sheldon-ai-for-ark Blueprint mod:
- Both use the same MCP bridge (sheldon-mcp-bridge)
- DuckBot plugin registers ServerAPI commands for structured access
- sheldon Blueprint handles natural language AI queries via the same bridge
- Tribe data from DuckBot plugin feeds the AI brain via MCP events

The plugin sends events to the bridge:
- `OnPlayerConnected` / `OnPlayerDisconnected`
- `OnDinoTamed` / `OnBabyBorn` / `OnDinoDied`
- `OnPlayerLevelUp`
- `OnWildDinoSpawn` (Giga, Titan, etc. near tribe base — from tribe alert system)