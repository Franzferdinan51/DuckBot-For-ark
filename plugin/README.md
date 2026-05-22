# DuckBot Plugin — Building & Reference

## Building

1. Install **Visual Studio 2022** with C++ desktop development workload
2. Clone AsaApi SDK as a **sibling directory** to this repo:
   ```
   cd "C:/Users/franz/OneDrive/Desktop/ARK Mod"
   git clone https://github.com/ArkServerApi/AsaApi.git
   ```
   Expected directory layout:
   ```
   ARK Mod/
   ├── duckbot-ai-for-ark/plugin/     ← your plugin
   │   ├── DuckBot.vcxproj
   │   └── src/
   └── AsaApi/                        ← sibling SDK
       └── AsaApi/Core/Public/API/...
   ```
3. Open `DuckBot.sln` in Visual Studio 2022
4. **Build → Build Solution** (Release x64)
5. Output: `Binaries/Release/DuckBot.dll`
6. Copy `DuckBot.dll` to your server's `ArkApi/Plugins/DuckBot/` directory

## AsaApi Framework

- **NOT Oxide** — Oxide does NOT support ASA. Uses ServerAPI / AsaApi.
- Hook system: `DECLARE_HOOK` macro + `AsaApi::GetHooks().SetHook()`
- Commands: `AsaApi::GetCommands().AddChatCommand()` / `.AddConsoleCommand()` / `.AddRconCommand()`
- Teleport: `pc->SetActorLocation(FVector, ...)` directly on `AShooterPlayerController`
- Cheat commands: `AsaApi::GetCommands().ExecuteCommand(FString)` for dino spawn, item give, unban, feed

## Source Files

| File | Description |
|------|-------------|
| `src/Plugin.cpp` | 39 chat commands, 6 hook implementations, MCP bridge senders |
| `src/Plugin.h` | Structs, command callbacks, DECLARE_HOOK declarations |
| `src/MCPBridge.cpp` | Raw Winsock2 WebSocket client (RFC 6455, auto-reconnect) |
| `src/MCPBridge.h` | Bridge interface and event senders |

## Config

Written to `ArkApi/Data/DuckBot/config.json` at runtime. Default values:

```json
{
  "MCP": {
    "host": "localhost",
    "port": 8443,
    "auth_token": "secret"
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

## MCP Bridge Connection

The plugin connects as a WebSocket CLIENT to the sheldon-mcp-bridge Python server. Events sent:

- `OnPlayerConnected` / `OnPlayerDisconnected`
- `OnDinoTamed` / `OnBabyBorn` / `OnDinoDied`
- `OnPlayerLevelUp`
- `OnWildDinoSpawn` (Giga, Titan near tribe base)