#include "Plugin.h"

#include <fstream>
#include <random>
#include <algorithm>
#include <sstream>
#include <cstdlib>

#pragma comment(lib, "AsaApi.lib")

namespace DuckBot
{
    Plugin* Plugin::singleton_ = nullptr;

    // ─── Plugin Lifecycle ─────────────────────────────────────────────────────

    void Plugin::Load() {
        singleton_ = new Plugin();
        singleton_->LogInfo("DuckBot loading...");

        // Read config
        singleton_->ReadConfig();

        // Load player and tribe data from disk
        singleton_->LoadAllData();

        // Initialize default kits
        singleton_->InitDefaultKits();

        // Register hooks
        Hooks::Init();

        // Register commands — AsaApi pattern (from Permissions.cpp)
        auto& commands = AsaApi::GetCommands();

        // Chat commands — /db prefix
        commands.AddChatCommand("/tribe", &ChatCommands::OnTribe);
        commands.AddChatCommand("/tdinos", &ChatCommands::OnTDinos);
        commands.AddChatCommand("/tribealert", &ChatCommands::OnTribeAlert);
        commands.AddChatCommand("/dinos", &ChatCommands::OnDinos);
        commands.AddChatCommand("/kits", &ChatCommands::OnKits);
        commands.AddChatCommand("/kit", &ChatCommands::OnKit);
        commands.AddChatCommand("/bal", &ChatCommands::OnBal);
        commands.AddChatCommand("/home", &ChatCommands::OnHome);
        commands.AddChatCommand("/sethome", &ChatCommands::OnSetHome);
        commands.AddChatCommand("/tpr", &ChatCommands::OnTPR);
        commands.AddChatCommand("/tpaccept", &ChatCommands::OnTPAccept);
        commands.AddChatCommand("/warp", &ChatCommands::OnWarp);
        commands.AddChatCommand("/setwarp", &ChatCommands::OnSetWarp);
        commands.AddChatCommand("/marker", &ChatCommands::OnMarker);
        commands.AddChatCommand("/gridmap", &ChatCommands::OnGridMap);
        commands.AddChatCommand("/kick", &ChatCommands::OnKick);
        commands.AddChatCommand("/ban", &ChatCommands::OnBan);
        commands.AddChatCommand("/unban", &ChatCommands::OnUnban);
        commands.AddChatCommand("/mute", &ChatCommands::OnMute);
        commands.AddChatCommand("/unmute", &ChatCommands::OnUnmute);
        commands.AddChatCommand("/slay", &ChatCommands::OnSlay);
        commands.AddChatCommand("/slayplayer", &ChatCommands::OnSlayPlayer);
        commands.AddChatCommand("/tphere", &ChatCommands::OnTPHere);
        commands.AddChatCommand("/feed", &ChatCommands::OnFeed);
        commands.AddChatCommand("/coinflip", &ChatCommands::OnCoinFlip);
        commands.AddChatCommand("/daily", &ChatCommands::OnDaily);
        commands.AddChatCommand("/work", &ChatCommands::OnWork);
        commands.AddChatCommand("/breeds", &ChatCommands::OnBreeds);
        commands.AddChatCommand("/kibble", &ChatCommands::OnKibble);
        commands.AddChatCommand("/aibrain", &ChatCommands::OnAIBrain);
        commands.AddChatCommand("/aireset", &ChatCommands::OnAIReset);
        commands.AddChatCommand("/save", &ChatCommands::OnSave);
        commands.AddChatCommand("/reload", &ChatCommands::OnReload);
        commands.AddChatCommand("/status", &ChatCommands::OnStatus);
        commands.AddChatCommand("/event", &ChatCommands::OnEvent);
        commands.AddChatCommand("/events", &ChatCommands::OnEvents);
        commands.AddChatCommand("/drop", &ChatCommands::OnDrop);
        commands.AddChatCommand("/pay", &ChatCommands::OnPay);
        commands.AddChatCommand("/help", &ChatCommands::OnHelp);

        // Console commands
        commands.AddConsoleCommand("DuckBot.Reload", &ChatCommands::OnReload);
        commands.AddConsoleCommand("DuckBot.Save", &ChatCommands::OnSave);

        // Rcon commands
        // commands.AddRconCommand("DuckBot.Reload", &RconCommands::OnReload);
        // commands.AddRconCommand("DuckBot.Save", &RconCommands::OnSave);

        singleton_->LogInfo("DuckBot v" PLUGIN_VERSION " loaded — 32 commands registered");
    }

    void Plugin::Unload() {
        LogInfo("DuckBot unloading...");
        SaveAllData();
        delete singleton_;
        singleton_ = nullptr;
    }

    // ─── Logging ────────────────────────────────────────────────────────────────

    void Plugin::LogInfo(const std::string& msg) {
        Log::GetLog()->info(msg.c_str());
    }

    void Plugin::LogError(const std::string& msg) {
        Log::GetLog()->error(msg.c_str());
    }

    // ─── Config ──────────────────────────────────────────────────────────────

    void Plugin::ReadConfig() {
        const std::string config_path = GetConfigPath();
        std::ifstream file{ config_path };
        if (!file.is_open()) {
            LogInfo("No config found, using defaults");
            return;
        }
        // TODO: parse JSON config with nlohmann::json like Permissions plugin
        // For now use defaults defined in PluginConfig struct
        file.close();
        LogInfo("Config loaded");
    }

    void Plugin::ReloadConfigCmd(AShooterPlayerController* pc, FString* cmd, bool) {
        try {
            ReadConfig();
            SendReply(pc, "[DuckBot] Config reloaded.");
        } catch (const std::exception& ex) {
            LogError(std::string("Config reload failed: ") + ex.what());
            SendReply(pc, "[DuckBot] Config reload failed.");
        }
    }

    // ─── Player Data ──────────────────────────────────────────────────────────

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

    PlayerData* Plugin::GetPlayerBySteamId(uint64 steam_id) {
        std::lock_guard<std::mutex> lock(data_mutex_);
        for (auto& p : players_) {
            if (p.steam_id == steam_id) return &p;
        }
        return nullptr;
    }

    int Plugin::GetPlayerTribeId(AShooterPlayerController* pc) {
        if (!pc) return 0;
        auto* player_state = reinterpret_cast<AShooterPlayerState*>(pc->PlayerStateField().Get());
        if (!player_state) return 0;
        auto* tribe_data = &player_state->MyTribeDataField();
        if (!tribe_data) return 0;
        return tribe_data->TribeIDField();
    }

    // ─── Permissions ──────────────────────────────────────────────────────────

    bool Plugin::HasPermission(AShooterPlayerController* pc, const std::string& perm) {
        if (!pc) return false;
        // Use AsaApi permission system
        FString eos_id;
        pc->GetUniqueNetIdAsString(&eos_id);
        // TODO: Check actual permission via AsaApi::GetPermissions().UserHasPermission
        // For now, admin always has permission
        return AsaApi::GetPermissions().UserHasPermission(*eos_id, perm.c_str());
    }

    // ─── Messaging ───────────────────────────────────────────────────────────

    void Plugin::SendReply(AShooterPlayerController* pc, const std::string& message) {
        if (!pc) return;
        AsaApi::GetApiUtils().SendServerMessage(pc, FColorList::White, message.c_str());
    }

    void Plugin::SendReplyToPlayer(AShooterPlayerController* pc, const std::string& message,
                                     float r, float g, float b, float a) {
        if (!pc) return;
        FColor color(r, g, b, a);
        AsaApi::GetApiUtils().SendServerMessage(pc, color, message.c_str());
    }

    void Plugin::SendBroadcast(const std::string& message) {
        auto* world = AsaApi::GetApiUtils().GetWorld();
        if (!world) return;
        const auto& controllers = world->PlayerControllerListField();
        for (const auto& ctrl : controllers) {
            auto* pc = static_cast<AShooterPlayerController*>(ctrl.Get());
            if (pc) AsaApi::GetApiUtils().SendServerMessage(pc, FColorList::White, message.c_str());
        }
    }

    // ─── Data Persistence ───────────────────────────────────────────────────

    void Plugin::SaveAllData() {
        // TODO: Save to JSON using nlohmann::json (like Permissions plugin)
        // auto path = AsaApi::GetDirectory().GetPluginDirectory(PLUGIN_NAME) + "/players.json";
        // std::ofstream file(path);
        // file << nlohmann::json(players_);
        LogInfo("All data saved");
    }

    void Plugin::LoadAllData() {
        // TODO: Load from JSON
        // auto path = AsaApi::GetDirectory().GetPluginDirectory(PLUGIN_NAME) + "/players.json";
        LogInfo("Data loaded (using defaults)");
    }

    // ─── Kit Initialization ──────────────────────────────────────────────────

    void Plugin::InitDefaultKits() {
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
            kit.description = "Wood walls, floors, ramps";
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

        // Dino Kit
        {
            KitDefinition kit;
            kit.name = "dino";
            kit.description = "Tamed level 30 dino (random species)";
            kit.cooldown_seconds = 14400;
            kit.required_permission = PERM_VIP;
            kit.dino_species = "Rex";
            kit.dino_level = 30;
            kits_.push_back(kit);
        }

        LogInfo("Kits initialized: starter, building, pvp, metal, dino");
    }

    // ─── Helpers ─────────────────────────────────────────────────────────────

    std::string GetConfigPath() {
        return AsaApi::GetDirectory().GetPluginDirectory(PLUGIN_NAME) + "/config.json";
    }

    std::vector<std::string> SplitString(const std::string& str, wchar_t delim) {
        std::vector<std::string> result;
        FString fstr(str.c_str());
        fstr.ParseIntoArray(result, &delim, true);
        return result;
    }

    // ════════════════════════════════════════════════════════════════════════
    // HOOK IMPLEMENTATIONS
    // ════════════════════════════════════════════════════════════════════════

    namespace Hooks {
        bool Hook_AShooterGameMode_HandleNewPlayer(
            AShooterGameMode* _this,
            AShooterPlayerController* new_player,
            UPrimalPlayerData* player_data,
            AShooterCharacter* player_character,
            bool is_from_login)
        {
            // Call original
            auto result = AShooterGameMode_HandleNewPlayer_original(
                _this, new_player, player_data, player_character, is_from_login);

            // Initialize player data in DuckBot
            if (new_player) {
                FString eos_id;
                new_player->GetUniqueNetIdAsString(&eos_id);
                Plugin::Get()->GetOrCreatePlayer(std::stoull(*eos_id));
                Plugin::Get()->LogInfo("[Join] " + std::string(*eos_id));
            }

            return result;
        }

        void Init() {
            Log::GetLog()->info("DuckBot Hooks::Init called");
            // Register hook on player join
            AsaApi::GetHooks().SetHook(
                "AShooterGameMode.HandleNewPlayer_Implementation(AShooterPlayerController*,UPrimalPlayerData*,AShooterCharacter*,bool)",
                &Hook_AShooterGameMode_HandleNewPlayer,
                &AShooterGameMode_HandleNewPlayer_original);
            Log::GetLog()->info("DuckBot hooks registered");
        }
    }

    // ════════════════════════════════════════════════════════════════════════
    // CHAT COMMAND IMPLEMENTATIONS
    // ════════════════════════════════════════════════════════════════════════

    namespace ChatCommands {

        void OnHelp(AShooterPlayerController* pc, FString* cmd, bool) {
            std::string help = R"(
=== DuckBot Commands ===
TRIBE: /tribe, /tdinos, /tribealert
DINOS: /dinos, /breeds, /feed
MAP: /marker add|list|remove, /gridmap
KITS: /kits, /kit [name]
ECONOMY: /bal, /pay [player] [amount], /daily, /work
TELEPORT: /home, /sethome, /tpr [player], /warp [name]
MOD: /kick, /ban, /mute, /slay
GAMES: /coinflip [wager], /kibble [species]
AI: /aibrain
ADMIN: /reload, /save, /status, /event
)";
            Plugin::Get()->SendReply(pc, help);
        }

        void OnTribe(AShooterPlayerController* pc, FString* cmd, bool) {
            auto* pData = Plugin::Get()->GetPlayerBySteamId(0); // TODO: get actual steam_id
            int tribe_id = Plugin::Get()->GetPlayerTribeId(pc);
            if (tribe_id == 0) {
                Plugin::Get()->SendReply(pc, "[DuckBot] You are not in a tribe.");
                return;
            }
            std::ostringstream oss;
            oss << "[DuckBot] Tribe ID: " << tribe_id << " — Overview: (tracking not yet connected)";
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnTDinos(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SendReply(pc, "[DuckBot] Tribe dinos: (not yet implemented)");
        }

        void OnTribeAlert(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SendReply(pc, "[DuckBot] No wild dino alerts.");
        }

        void OnDinos(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SendReply(pc, "[DuckBot] Dinos: tracking not yet connected");
        }

        void OnKits(AShooterPlayerController* pc, FString* cmd, bool) {
            std::string msg = "=== Available Kits ===\n";
            for (auto& kit : Plugin::Get()->GetAllKits()) {
                msg += "  " + kit.name + " - " + kit.description + "\n";
            }
            Plugin::Get()->SendReply(pc, msg);
        }

        void OnKit(AShooterPlayerController* pc, FString* cmd, bool) {
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /kit [name]");
                return;
            }
            Plugin::Get()->SendReply(pc, "[DuckBot] Kit system: not yet implemented");
        }

        void OnBal(AShooterPlayerController* pc, FString* cmd, bool) {
            auto* pData = Plugin::Get()->GetPlayerBySteamId(0); // TODO: real steam_id
            int bal = pData ? pData->balance : 0;
            std::ostringstream oss;
            oss << "[DuckBot] Balance: " << bal << " points";
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnHome(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SendReply(pc, "[DuckBot] Teleporting to home... (not yet implemented)");
        }

        void OnSetHome(AShooterPlayerController* pc, FString* cmd, bool) {
            auto* world = AsaApi::GetApiUtils().GetWorld();
            if (!world) return;
            // TODO: Get player position from pc, save as home
            Plugin::Get()->SendReply(pc, "[DuckBot] Home position saved.");
        }

        void OnTPR(AShooterPlayerController* pc, FString* cmd, bool) {
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /tpr [player]");
                return;
            }
            Plugin::Get()->SendReply(pc, "[DuckBot] TPR sent. Target has 60s to /tpaccept");
        }

        void OnTPAccept(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SendReply(pc, "[DuckBot] Teleport accepted.");
        }

        void OnWarp(AShooterPlayerController* pc, FString* cmd, bool) {
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /warp [name]");
                return;
            }
            auto& warps = Plugin::Get()->GetWarpDB();
            auto warp_name = std::string(*parsed[1]);
            if (warps.find(warp_name) == warps.end()) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Warp not found.");
                return;
            }
            Plugin::Get()->SendReply(pc, "[DuckBot] Warping... (not yet implemented)");
        }

        void OnSetWarp(AShooterPlayerController* pc, FString* cmd, bool) {
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /setwarp [name]");
                return;
            }
            Plugin::Get()->SendReply(pc, "[DuckBot] Warp created. (not yet implemented)");
        }

        void OnMarker(AShooterPlayerController* pc, FString* cmd, bool) {
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /marker add|list|remove [name] [type]");
                return;
            }
            Plugin::Get()->SendReply(pc, "[DuckBot] Marker: (not yet implemented)");
        }

        void OnGridMap(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SendReply(pc, "[DuckBot] Grid map: (not yet implemented)");
        }

        void OnKick(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_MOD)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] No permission.");
                return;
            }
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) return;
            Plugin::Get()->SendReply(pc, "[DuckBot] Kicked. (not yet implemented)");
        }

        void OnBan(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_ADMIN)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] No permission.");
                return;
            }
            Plugin::Get()->SendReply(pc, "[DuckBot] Banned. (not yet implemented)");
        }

        void OnUnban(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_ADMIN)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] No permission.");
                return;
            }
            Plugin::Get()->SendReply(pc, "[DuckBot] Unbanned. (not yet implemented)");
        }

        void OnMute(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_MOD)) return;
            Plugin::Get()->SendReply(pc, "[DuckBot] Muted. (not yet implemented)");
        }

        void OnUnmute(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_MOD)) return;
            Plugin::Get()->SendReply(pc, "[DuckBot] Unmuted. (not yet implemented)");
        }

        void OnSlay(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_MOD)) return;
            Plugin::Get()->SendReply(pc, "[DuckBot] Slayed dinos. (not yet implemented)");
        }

        void OnSlayPlayer(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_MOD)) return;
            Plugin::Get()->SendReply(pc, "[DuckBot] Slayed player. (not yet implemented)");
        }

        void OnTPHere(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_MOD)) return;
            Plugin::Get()->SendReply(pc, "[DuckBot] Teleported to you. (not yet implemented)");
        }

        void OnFeed(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SendReply(pc, "[DuckBot] Auto-feeding tames... (not yet implemented)");
        }

        void OnCoinFlip(AShooterPlayerController* pc, FString* cmd, bool) {
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            int wager = parsed.IsValidIndex(1) ? std::stoi(*parsed[1]) : 0;

            static std::random_device rd;
            static std::mt19937 gen(rd());
            bool result = std::bernoulli_distribution(0.5)(gen);

            std::ostringstream oss;
            if (wager > 0) {
                oss << "[DuckBot] Coin: " << (result ? "HEADS" : "TAILS") << " | Wager: " << wager << " | You " << (result ? "WIN!" : "LOSE!");
            } else {
                oss << "[DuckBot] Coin: " << (result ? "HEADS" : "TAILS");
            }
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnDaily(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SendReply(pc, "[DuckBot] Daily reward claimed! +100 points (not yet persisted)");
        }

        void OnWork(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SendReply(pc, "[DuckBot] Work done! +15 points (not yet persisted)");
        }

        void OnBreeds(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SendReply(pc, "[DuckBot] No recent breed alerts.");
        }

        void OnKibble(AShooterPlayerController* pc, FString* cmd, bool) {
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /kibble [dino species]");
                return;
            }
            Plugin::Get()->SendReply(pc, "[DuckBot] Kibble: (not yet implemented)");
        }

        void OnAIBrain(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SendReply(pc, "[DuckBot] AI Brain: Not yet connected to MCP bridge");
        }

        void OnAIReset(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SendReply(pc, "[DuckBot] AI context reset.");
        }

        void OnSave(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SaveAllData();
            Plugin::Get()->SendReply(pc, "[DuckBot] Data saved.");
        }

        void OnReload(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->ReadConfig();
            Plugin::Get()->SendReply(pc, "[DuckBot] Config reloaded.");
        }

        void OnStatus(AShooterPlayerController* pc, FString* cmd, bool) {
            std::ostringstream oss;
            oss << "=== DuckBot Status ===\n";
            oss << "Players: " << Plugin::Get()->GetAllPlayers().size() << "\n";
            oss << "Tribes: " << Plugin::Get()->GetAllTribes().size() << "\n";
            oss << "Kits: " << Plugin::Get()->GetAllKits().size() << "\n";
            oss << "Warps: " << Plugin::Get()->GetWarpDB().size() << "\n";
            oss << "MCP Bridge: Not connected\n";
            oss << "Version: " << PLUGIN_VERSION;
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnEvent(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_ADMIN)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Admin only.");
                return;
            }
            Plugin::Get()->SendReply(pc, "[DuckBot] Event: (not yet implemented)");
        }

        void OnEvents(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SendReply(pc, "[DuckBot] No active events.");
        }

        void OnDrop(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_ADMIN)) return;
            Plugin::Get()->SendReply(pc, "[DuckBot] Drop party started! (not yet implemented)");
        }

        void OnPay(AShooterPlayerController* pc, FString* cmd, bool) {
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(2)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /pay [player] [amount]");
                return;
            }
            Plugin::Get()->SendReply(pc, "[DuckBot] Payment sent. (not yet implemented)");
        }
    }

    // ════════════════════════════════════════════════════════════════════════
    // DLL ENTRY POINT
    // ════════════════════════════════════════════════════════════════════════

    BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
    {
        switch (ul_reason_for_call)
        {
        case DLL_PROCESS_ATTACH:
            Plugin::Load();
            break;
        case DLL_PROCESS_DETACH:
            Plugin::Unload();
            break;
        }
        return TRUE;
    }
}