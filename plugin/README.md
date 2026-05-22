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

---

## Commands

All commands prefixed with `/` (ServerAPI chat command system):

| Command | Description | Permission |
|---------|-------------|------------|
| `/tribe` | Tribe overview: members, tames, alerts | use |
| `/tdinos` | List tribe's active tames | use |
| `/tribealert` | Wild dino alerts near tribe | use |
| `/dinos` | Show tracked dinos | use |
| `/kits` | Show available kits | use |
| `/kit [name]` | Claim a kit | use |
| `/bal` | Show your balance | use |
| `/pay [player] [amount]` | Pay another player | use |
| `/daily` | Claim daily reward (24h) | use |
| `/work` | Claim work reward (5min) | use |
| `/home` | Teleport to home | use |
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
| `/feed` | Auto-feed your tames | use |
| `/coinflip [wager]` | Flip a coin | use |
| `/breeds` | Recent breed alerts and mutations | use |
| `/kibble [species]` | Kibble recipe guide | use |
| `/aibrain` | AI brain status | use |
| `/aireset` | Reset AI context | use |
| `/event start\|stop\|list` | Manage events | admin |
| `/events` | Show active events | use |
| `/drop` | Host drop party | admin |
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
    ├── Sends events to MCP bridge (tame, born, level up, etc.)
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

The plugin uses `DECLARE_HOOK` macros to intercept game events and `AsaApi::GetCommands().AddChatCommand()` to register all 32+ commands. Events are sent to the sheldon MCP bridge via WebSocket for AI processing.

---

## Hooks Used

| Hook | Purpose |
|------|---------|
| `AShooterGameMode.HandleNewPlayer_Implementation` | Player join — initialize player data |

Additional hooks to add:
- `AShooterGameMode.HandlePlayerLogout` — player leave
- `OnDinoTamed` — dino taming event
- `OnBabyBorn` — breeding event
- `OnDinoDied` — dino death
- `OnPlayerLevelUp` — XP level up
- `OnChatMessage` — chat for AI prefix detection

---

## Building

1. Install Visual Studio 2022 with C++ desktop development
2. Install ARK ServerAPI SDK (AsaApi) — put in `AsaApi/` sibling directory
3. Open `plugin/DuckBot.vcxproj` in Visual Studio
4. Build → Build Solution
5. Output: `Binaries/DuckBot.dll` — copy to server's `ArkApi/Plugins/` directory

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
  }
}
```

---

## TODO

- [x] Plugin scaffold with 32 commands (stub implementations)
- [x] AsaApi hook pattern (DECLARE_HOOK from Permissions plugin)
- [x] Command registration pattern (AddChatCommand from Permissions plugin)
- [x] Kit system with 5 default kits
- [ ] Verify hook signatures against live ASA server
- [ ] Implement all command bodies (currently stub)
- [ ] Implement player data persistence (JSON save/load)
- [ ] Implement warp and home teleport functionality
- [ ] Implement tribe data tracking
- [ ] Connect MCP bridge WebSocket client
- [ ] Add remaining hooks: OnDinoTamed, OnBabyBorn, OnDinoDied, OnPlayerLevelUp
- [ ] Implement moderation commands (kick, ban, slay, mute)
- [ ] Implement kit giving system
- [ ] Implement economy (daily, work, pay)
- [ ] Add `/db` alias as prefix command router

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
- `OnWildDinoSpawn` (Giga, Titan, etc. near tribe base)