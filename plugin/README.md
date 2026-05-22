# DuckBot AI for ARK

**ARK Survival Ascended tribe management and AI bot — fork of [sheldon-ai-for-ark](https://github.com/Franzferdinan51/sheldon-ai-for-ark).**

This is a ServerAPI C++ plugin that adds full command-driven tribe management, economy, and AI agent integration to ARK, running alongside the existing sheldon-ai-for-ark Blueprint mod.

---

## What This Adds

This plugin layer sits **below** the sheldon-ai-for-ark Blueprint mod. It provides:

| Feature | Description |
|---------|-------------|
| **Tribe Command Hub** | Track all tribe tames with health/hunger, wild dino spawn alerts, breeding/mutation alerts |
| **Kit System** | ARK-native kits (stone tools, metal, kibble, dino spawns) — not scrap |
| **Economy** | Points-based: daily/work rewards, pay other players, event rewards |
| **Teleport** | Home positions, warp locations, TPR requests |
| **Moderation** | Kick, ban, mute, slay player dinos, auto-feed |
| **Map Markers** | Tribe waypoints (base, farming, metal, cave, beacon, danger) |
| **Chat Games** | Coinflip, scavenger hunt, race, kibble guide |
| **AI Bridge** | MCP bridge connecting to sheldon's Python server for AI queries |

Commands are registered via `/db` (or via sheldon's natural language AI).

---

## Architecture

```
DuckBot Plugin (C++/ServerAPI)
    │
    ├── Tracks tribe members, dinos, breeding events
    ├── Handles all /db command parsing and execution
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
ARK ServerAPI / Blueprint Mod
```

The plugin registers commands with ServerAPI, tracks game events (tame, breed, death, join/leave), and sends them to the sheldon mcp-bridge via WebSocket. The bridge runs the agentic loop and executes tools via the plugin's command interface.

---

## Commands

All commands prefixed with `/db`:

### Tribe
| Command | Description |
|---------|-------------|
| `/db tribe` | Tribe overview: members, tames, alerts |
| `/db tdinos` | List tribe's active tames |
| `/db tribealert` | Wild dino alerts near tribe |

### Dino Tracking
| Command | Description |
|---------|-------------|
| `/db dinos` | Show tracked dinos |
| `/db dinoinfo` | Get info on a specific dino |
| `/db breeds` | Recent breed alerts and mutations |
| `/db feed` | Auto-feed your tames |

### Map Markers
| Command | Description |
|---------|-------------|
| `/db marker add [name] [type]` | Add a waypoint |
| `/db marker remove [name]` | Remove a waypoint |
| `/db markers` | List all tribe markers |
| `/db gridmap` | Grid map with all waypoints |

### Kits
| Command | Description |
|---------|-------------|
| `/db kits` | Show available kits |
| `/db kit [name]` | Claim a kit |

### Economy
| Command | Description |
|---------|-------------|
| `/db bal` | Show your balance |
| `/db pay [player] [amount]` | Pay another player |
| `/db daily` | Claim daily reward |
| `/db work` | Claim work reward |

### Teleport
| Command | Description |
|---------|-------------|
| `/db home` | Teleport to home |
| `/db sethome` | Save home position |
| `/db tpr [player]` | Send teleport request |
| `/db tpaccept` | Accept teleport request |
| `/db warp [name]` | Teleport to warp |
| `/db setwarp [name]` | Create warp |

### Moderation
| Command | Description |
|---------|-------------|
| `/db kick [player]` | Kick player |
| `/db ban [player]` | Ban player |
| `/db mute [player]` | Mute player |
| `/db slay [player]` | Slay player's dinos |
| `/db slayplayer [player]` | Slay the player |

### AI / Bridge
| Command | Description |
|---------|-------------|
| `/db aibrain` | AI brain status |
| `/db aireset` | Reset AI context |
| `!ai [query]` | Send direct AI query |

### Admin
| Command | Description |
|---------|-------------|
| `/db reload` | Reload config |
| `/db save` | Save data |
| `/db status` | Plugin status |

---

## Building

Requires:
- Visual Studio 2022
- ARK ServerAPI SDK (AsaApi)
- ASAMD-Server compiled headers

```bash
# Clone with submodules
git clone --recursive https://github.com/Franzferdinan51/duckbot-ai-for-ark

# Open solution in Visual Studio
# Build → Build Solution
# Output: Binaries/*.v墩
```

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

---

## Permission Tiers

| Tier | Access |
|------|--------|
| `duckbot.admin` | Full access: all commands, slay, ban, event management |
| `duckbot.mod` | Kick, mute, slay dinos, feed, setwarp |
| `duckbot.vip` | Extra kits, faster cooldowns |
| `duckbot.use` | Basic access: tribe, kits, economy, teleport |

---

## Status

**Active development** — this is a fork of sheldon-ai-for-ark being adapted for full DuckBot functionality.

- [x] Architecture designed
- [x] Plugin scaffold written
- [ ] AsaApi hook verification against live server
- [ ] Full command implementation
- [ ] MCP bridge integration testing