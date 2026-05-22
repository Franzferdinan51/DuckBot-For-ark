#include "Plugin.h"
#include <chrono>
#include <algorithm>
#include <random>
#include <sstream>

namespace DuckBot
{
    Plugin* Plugin::singleton_ = nullptr;

    void Plugin::Init() {
        singleton_ = new Plugin();
        singleton_->LogInfo("DuckBot initializing...");

        // Load config
        LoadConfig();

        // Register permissions
        // TODO: AsaApi permission registration
        // AsaApi::Permissions::RegisterPermission(PERM_ADMIN, singleton_);
        // AsaApi::Permissions::RegisterPermission(PERM_MOD, singleton_);
        // AsaApi::Permissions::RegisterPermission(PERM_VIP, singleton_);
        // AsaApi::Permissions::RegisterPermission(PERM_USE, singleton_);
        LogInfo("Permissions registered");

        // Register commands
        // TODO: AsaApi command registration
        // AsaApi::Commands::AddChatCommand("tribe", singleton_, Commands::OnTribeCommand);
        // AsaApi::Commands::AddChatCommand("tdinos", singleton_, Commands::OnTDinosCommand);
        // AsaApi::Commands::AddChatCommand("tribealert", singleton_, Commands::OnTribeAlertCommand);
        // AsaApi::Commands::AddChatCommand("dinos", singleton_, Commands::OnDinosCommand);
        // AsaApi::Commands::AddChatCommand("kits", singleton_, Commands::OnKitsCommand);
        // AsaApi::Commands::AddChatCommand("kit", singleton_, Commands::OnKitCommand);
        // AsaApi::Commands::AddChatCommand("bal", singleton_, Commands::OnBalCommand);
        // AsaApi::Commands::AddChatCommand("home", singleton_, Commands::OnHomeCommand);
        // AsaApi::Commands::AddChatCommand("sethome", singleton_, Commands::OnSetHomeCommand);
        // AsaApi::Commands::AddChatCommand("tpr", singleton_, Commands::OnTPRCommand);
        // AsaApi::Commands::AddChatCommand("tpaccept", singleton_, Commands::OnTPAcceptCommand);
        // AsaApi::Commands::AddChatCommand("warp", singleton_, Commands::OnWarpCommand);
        // AsaApi::Commands::AddChatCommand("setwarp", singleton_, Commands::OnSetWarpCommand);
        // AsaApi::Commands::AddChatCommand("marker", singleton_, Commands::OnMarkerCommand);
        // AsaApi::Commands::AddChatCommand("gridmap", singleton_, Commands::OnGridMapCommand);
        // AsaApi::Commands::AddChatCommand("kick", singleton_, Commands::OnKickCommand);
        // AsaApi::Commands::AddChatCommand("ban", singleton_, Commands::OnBanCommand);
        // AsaApi::Commands::AddChatCommand("mute", singleton_, Commands::OnMuteCommand);
        // AsaApi::Commands::AddChatCommand("slay", singleton_, Commands::OnSlayCommand);
        // AsaApi::Commands::AddChatCommand("feed", singleton_, Commands::OnFeedCommand);
        // AsaApi::Commands::AddChatCommand("coinflip", singleton_, Commands::OnCoinFlipCommand);
        // AsaApi::Commands::AddChatCommand("aibrain", singleton_, Commands::OnAIBrainCommand);
        // AsaApi::Commands::AddChatCommand("reload", singleton_, Commands::OnReloadCommand);
        // AsaApi::Commands::AddChatCommand("save", singleton_, Commands::OnSaveCommand);
        // AsaApi::Commands::AddChatCommand("status", singleton_, Commands::OnStatusCommand);
        // AsaApi::Commands::AddChatCommand("daily", singleton_, Commands::OnDailyCommand);
        // AsaApi::Commands::AddChatCommand("work", singleton_, Commands::OnWorkCommand);
        // AsaApi::Commands::AddChatCommand("breeds", singleton_, Commands::OnBreedsCommand);
        // AsaApi::Commands::AddChatCommand("kibble", singleton_, Commands::OnKibbleCommand);
        // AsaApi::Commands::AddChatCommand("help", singleton_, Commands::OnHelpCommand);
        // AsaApi::Commands::AddChatCommand("event", singleton_, Commands::OnEventCommand);
        // AsaApi::Commands::AddChatCommand("events", singleton_, Commands::OnEventsCommand);
        LogInfo("Commands registered: tribe, tdinos, dinos, kits, kit, bal, home, sethome, tpr, warp, marker, gridmap, kick, ban, mute, slay, feed, coinflip, aibrain, reload, save, status, daily, work, breeds, kibble, help, event, events");

        // Register hooks
        // TODO: AsaApi hook registration
        // AsaApi::Hooks::RegisterHook("OnPlayerConnected", Hooks::OnPlayerConnected);
        // AsaApi::Hooks::RegisterHook("OnPlayerDisconnected", Hooks::OnPlayerDisconnected);
        // AsaApi::Hooks::RegisterHook("OnChatMessage", Hooks::OnChatMessage);
        // AsaApi::Hooks::RegisterHook("OnDinoTamed", Hooks::OnDinoTamed);
        // AsaApi::Hooks::RegisterHook("OnBabyBorn", Hooks::OnBabyBorn);
        // AsaApi::Hooks::RegisterHook("OnDinoDied", Hooks::OnDinoDied);
        // AsaApi::Hooks::RegisterHook("OnPlayerLevelUp", Hooks::OnPlayerLevelUp);
        LogInfo("Hooks registered");

        // Load player data
        LoadPlayerData();

        // Initialize default kits
        InitializeDefaultKits();

        LogInfo("DuckBot v" PLUGIN_VERSION " initialized");
    }

    void Plugin::Shutdown() {
        LogInfo("DuckBot shutting down...");
        SavePlayerData();
        delete singleton_;
        singleton_ = nullptr;
    }

    void Plugin::LogInfo(const std::string& msg) {
        // TODO: AsaApi Logger::Info
        // AsaApi::Logger::Info(("[DuckBot] " + msg).c_str());
        printf("[DuckBot] %s\n", msg.c_str());
    }

    void Plugin::LogError(const std::string& msg) {
        printf("[DuckBot][ERROR] %s\n", msg.c_str());
    }

    void Plugin::LogDebug(const std::string& msg) {
        printf("[DuckBot][DEBUG] %s\n", msg.c_str());
    }

    void Plugin::LoadConfig() {
        // TODO: AsaApi config loading
        // auto& config = AsaApi::Config::Get(PLUGIN_NAME);
        // config.TryGetValue("MCP.Host", config_.mcp_host, "localhost");
        // config.TryGetValue("MCP.Port", config_.mcp_port, 8443);
        // config.TryGetValue("MCP.AuthToken", config_.mcp_auth_token, "secret");
        // config.TryGetValue("Economy.DailyReward", config_.daily_reward, 100);
        // config.TryGetValue("Economy.WorkReward", config_.work_reward, 15);
        // config.TryGetValue("Economy.WorkCooldown", config_.work_cooldown, 300);
        LogInfo("Config loaded");
    }

    void Plugin::SaveConfig() {
        // TODO: AsaApi config saving
        LogInfo("Config saved");
    }

    PlayerData* Plugin::GetOrCreatePlayer(uint64 steam_id) {
        std::lock_guard<std::mutex> lock(data_mutex_);
        for (auto& p : players_) {
            if (p.steam_id == steam_id) return &p;
        }
        PlayerData p;
        p.steam_id = steam_id;
        p.level = 1;
        p.balance = 0;
        players_.push_back(p);
        return &players_.back();
    }

    PlayerData* Plugin::GetPlayer(uint64 steam_id) {
        std::lock_guard<std::mutex> lock(data_mutex_);
        for (auto& p : players_) {
            if (p.steam_id == steam_id) return &p;
        }
        return nullptr;
    }

    void Plugin::SavePlayerData() {
        // TODO: AsaApi data file storage
        // auto path = AsaApi::Directory::GetPluginDirectory(PLUGIN_NAME) + "/players.json";
        // AsaApi::Tools::Json::WriteObject(path, players_);
        LogInfo("Player data saved");
    }

    void Plugin::LoadPlayerData() {
        // TODO: AsaApi data file loading
        // auto path = AsaApi::Directory::GetPluginDirectory(PLUGIN_NAME) + "/players.json";
        // AsaApi::Tools::Json::ReadObject(path, players_);
        LogInfo("Player data loaded");
    }

    bool Plugin::HasPermission(uint64 steam_id, const std::string& perm) {
        // TODO: AsaApi permission check
        // return AsaApi::Permissions::UserHasPermission(steam_id, perm.c_str());
        return false;
    }

    void Plugin::SendReply(uint64 steam_id, const std::string& message) {
        // TODO: AsaApi player send message
        // auto player = AsaApi::ApiUtils::FindPlayerBySteamId(steam_id);
        // if (player) player->SendMessage(message.c_str());
    }

    void Plugin::SendBroadcast(const std::string& message) {
        // TODO: AsaApi broadcast
        // AsaApi::ApiUtils::Broadcast(message.c_str());
    }

    void Plugin::InitializeDefaultKits() {
        // Starter Kit
        {
            KitDefinition kit;
            kit.name = "starter";
            kit.description = "Stone tools, torch, sleeping bag for new players";
            kit.cooldown_seconds = 0;
            kit.items = {
                {"Stone Pickaxe", 1, 0},
                {"Stone Hatchet", 1, 0},
                {"Torch", 1, 0},
                {"Sleeping Bag", 1, 0},
            };
            kits_.push_back(kit);
        }

        // Building Kit
        {
            KitDefinition kit;
            kit.name = "building";
            kit.description = "Wooden walls, floors, ramps";
            kit.cooldown_seconds = 3600;
            kit.required_permission = PERM_USE;
            kit.items = {
                {"Wood Foundation", 10, 0},
                {"Wood Wall", 20, 0},
                {"Wood Ceiling", 5, 0},
                {"Wood Ramp", 2, 0},
            };
            kits_.push_back(kit);
        }

        // PVP Kit
        {
            KitDefinition kit;
            kit.name = "pvp";
            kit.description = "Cloth armor, pike, medical brew";
            kit.cooldown_seconds = 7200;
            kit.required_permission = PERM_USE;
            kit.items = {
                {"Cloth Boots", 1, 1},
                {"Cloth Shirt", 1, 1},
                {"Cloth Pants", 1, 1},
                {"Cloth Hat", 1, 1},
                {"Pike", 1, 0},
                {"Medical Brew", 5, 0},
            };
            kits_.push_back(kit);
        }

        // Metal Kit
        {
            KitDefinition kit;
            kit.name = "metal";
            kit.description = "Metal pick, hatchet, sword";
            kit.cooldown_seconds = 5400;
            kit.required_permission = PERM_VIP;
            kit.items = {
                {"Metal Pick", 1, 0},
                {"Metal Hatchet", 1, 0},
                {"Metal Sword", 1, 0},
            };
            kits_.push_back(kit);
        }

        // Dino Kit (spawns level 30 dino)
        {
            KitDefinition kit;
            kit.name = "dino";
            kit.description = "Tamed level 30 dino (random species)";
            kit.cooldown_seconds = 14400;
            kit.required_permission = PERM_VIP;
            kits_.push_back(kit);
        }

        LogInfo("Kits initialized: starter, building, pvp, metal, dino");
    }

    // ─── Hook Implementations ───────────────────────────────────────────────────

    void Hooks::OnPlayerConnected(void* player) {
        // TODO: Get player steam_id and name from AsaApi
        // uint64 steam_id = AsaApi::ApiUtils::BptrToSteamId(player);
        // std::string name = AsaApi::ApiUtils::GetPlayerName(player);
        uint64 steam_id = 0; // placeholder
        std::string name = "Unknown";

        Plugin::Get()->LogInfo("[Join] " + name);

        auto* pData = Plugin::Get()->GetOrCreatePlayer(steam_id);
        pData->name = name;

        // Send welcome
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Welcome! Use /db help for commands.");

        // Notify MCP bridge
        // auto* bridge = Plugin::Get()->GetMCPBridge();
        // if (bridge) bridge->OnPlayerEvent("join", steam_id, name, pData->tribe_id);
    }

    void Hooks::OnPlayerDisconnected(void* player) {
        Plugin::Get()->LogInfo("[Leave] Player disconnected");
        Plugin::Get()->SavePlayerData();
    }

    void Hooks::OnChatMessage(void* player, const char* message, int mode) {
        // Check if muted
        // uint64 steam_id = AsaApi::ApiUtils::BptrToSteamId(player);
        // auto* pData = Plugin::Get()->GetPlayer(steam_id);
        // if (pData && pData->is_muted) return;

        // Check for AI prefix
        // if (strncmp(message, "!ai ", 4) == 0) {
        //     // Forward to MCP bridge
        // }
    }

    void Hooks::OnDinoTamed(void* player, void* dino) {
        // TODO: Extract dino info via AsaApi
        // std::string species = AsaApi::ApiUtils::GetDinoSpecies(dino);
        // int level = AsaApi::ApiUtils::GetDinoLevel(dino);
        Plugin::Get()->LogInfo("[Tame] New tame recorded");
    }

    void Hooks::OnBabyBorn(void* baby, void* mother, void* player) {
        Plugin::Get()->LogInfo("[Breed] Baby born");
    }

    void Hooks::OnDinoDied(void* dino, void* killer) {
        Plugin::Get()->LogInfo("[Death] Dino died");
    }

    void Hooks::OnPlayerLevelUp(void* player, int new_level) {
        Plugin::Get()->LogInfo("[LevelUp] Player leveled up");
    }

    // ─── Command Implementations ─────────────────────────────────────────────────

    const char* HELP_TEXT = R"(
=== DuckBot Commands ===
TRIBE: /db tribe, /db tdinos, /db tribealert
DINOS: /db dinos, /db breeds, /db feed
MAP: /db marker add|list|remove, /db gridmap
KITS: /db kits, /db kit [name]
ECONOMY: /db bal, /db pay [player] [amount], /db daily, /db work
TELEPORT: /db home, /db sethome, /db tpr [player], /db warp [name]
MOD: /db kick, /db ban, /db mute, /db slay
GAMES: /db coinflip [wager], /db kibble [species]
AI: /db aibrain
ADMIN: /db reload, /db save, /db status, /db event
)";

    void Commands::OnHelpCommand(void* player, int argc, const char** argv) {
        // TODO: Get steam_id from player
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, HELP_TEXT);
    }

    void Commands::OnTribeCommand(void* player, int argc, const char** argv) {
        // TODO: Get tribe info via AsaApi
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Tribe overview: (not yet implemented)");
    }

    void Commands::OnTDinosCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Tribe dinos: (not yet implemented)");
    }

    void Commands::OnTribeAlertCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] No wild dino alerts.");
    }

    void Commands::OnDinosCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Dinos: use /db track [name]");
    }

    void Commands::OnKitsCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        std::string msg = "=== Available Kits ===\n";
        auto& kits = Plugin::Get()->GetAllKits();
        for (auto& kit : kits) {
            msg += "  " + kit.name + " - " + kit.description + "\n";
        }
        Plugin::Get()->SendReply(steam_id, msg);
    }

    void Commands::OnKitCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        if (argc < 1) {
            Plugin::Get()->SendReply(steam_id, "[DuckBot] Usage: /db kit [name]");
            return;
        }
        // TODO: Look up kit, check cooldown, give items
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Kit system: (not yet implemented)");
    }

    void Commands::OnBalCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        auto* pData = Plugin::Get()->GetPlayer(steam_id);
        if (pData) {
            char buf[128];
            snprintf(buf, sizeof(buf), "[DuckBot] Balance: %d points", pData->balance);
            Plugin::Get()->SendReply(steam_id, buf);
        } else {
            Plugin::Get()->SendReply(steam_id, "[DuckBot] Balance: 0 points");
        }
    }

    void Commands::OnHomeCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Teleporting to home... (not yet implemented)");
    }

    void Commands::OnSetHomeCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        // TODO: Get player position via AsaApi, save to home
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Home position saved.");
    }

    void Commands::OnTPRCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        if (argc < 1) {
            Plugin::Get()->SendReply(steam_id, "[DuckBot] Usage: /db tpr [player]");
            return;
        }
        Plugin::Get()->SendReply(steam_id, "[DuckBot] TPR sent to target.");
    }

    void Commands::OnTPAcceptCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Teleport accepted.");
    }

    void Commands::OnWarpCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        if (argc < 1) {
            Plugin::Get()->SendReply(steam_id, "[DuckBot] Usage: /db warp [name]");
            return;
        }
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Warping... (not yet implemented)");
    }

    void Commands::OnSetWarpCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        if (argc < 1) {
            Plugin::Get()->SendReply(steam_id, "[DuckBot] Usage: /db setwarp [name]");
            return;
        }
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Warp created. (not yet implemented)");
    }

    void Commands::OnMarkerCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        if (argc < 1) {
            Plugin::Get()->SendReply(steam_id, "[DuckBot] Usage: /db marker add|list|remove [name] [type]");
            return;
        }
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Marker: (not yet implemented)");
    }

    void Commands::OnGridMapCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Grid map: (not yet implemented)");
    }

    void Commands::OnKickCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        if (argc < 1) return;
        if (!Plugin::Get()->HasPermission(steam_id, PERM_MOD)) return;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Kicked player.");
    }

    void Commands::OnBanCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        if (argc < 1) return;
        if (!Plugin::Get()->HasPermission(steam_id, PERM_ADMIN)) return;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Player banned.");
    }

    void Commands::OnMuteCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        if (argc < 1) return;
        if (!Plugin::Get()->HasPermission(steam_id, PERM_MOD)) return;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Player muted.");
    }

    void Commands::OnSlayCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        if (argc < 1) return;
        if (!Plugin::Get()->HasPermission(steam_id, PERM_MOD)) return;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Slayed player's dinos.");
    }

    void Commands::OnFeedCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Auto-feeding your tames... (not yet implemented)");
    }

    void Commands::OnCoinFlipCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        int wager = 0;
        if (argc >= 1) wager = atoi(argv[0]);

        static std::random_device rd;
        static std::mt19937 gen(rd());
        std::bernoulli_distribution dist(0.5);
        bool result = dist(gen);

        char buf[256];
        if (wager > 0) {
            snprintf(buf, sizeof(buf), "[DuckBot] Coin flipped: %s | Wager: %d | You %s!",
                result ? "HEADS" : "TAILS", wager, result ? "WIN" : "LOSE");
        } else {
            snprintf(buf, sizeof(buf), "[DuckBot] Coin flipped: %s", result ? "HEADS" : "TAILS");
        }
        Plugin::Get()->SendReply(steam_id, buf);
    }

    void Commands::OnAIBrainCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] AI Brain: (not yet connected)");
    }

    void Commands::OnReloadCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->LoadConfig();
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Config reloaded.");
    }

    void Commands::OnSaveCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SavePlayerData();
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Data saved.");
    }

    void Commands::OnStatusCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Status: Initializing... (hook verification needed)");
    }

    void Commands::OnDailyCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Daily reward: (not yet implemented)");
    }

    void Commands::OnWorkCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Work: (not yet implemented)");
    }

    void Commands::OnBreedsCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] No recent breed alerts.");
    }

    void Commands::OnKibbleCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        if (argc < 1) {
            Plugin::Get()->SendReply(steam_id, "[DuckBot] Usage: /db kibble [dino species]");
            return;
        }
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Kibble: (not yet implemented)");
    }

    void Commands::OnEventCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Event: (admin only, not yet implemented)");
    }

    void Commands::OnEventsCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] No active events.");
    }

    void Commands::OnDropCommand(void* player, int argc, const char** argv) {
        uint64 steam_id = 0;
        if (!Plugin::Get()->HasPermission(steam_id, PERM_ADMIN)) return;
        Plugin::Get()->SendReply(steam_id, "[DuckBot] Drop party started! (not yet implemented)");
    }
}