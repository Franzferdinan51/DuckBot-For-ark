#include "Plugin.h"
#include "MCPBridge.h"
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

        // Start MCP bridge client
        GetMCPBridge()->Start(
            singleton_->config_.mcp_host,
            singleton_->config_.mcp_port,
            singleton_->config_.mcp_auth_token);

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
        GetMCPBridge()->Stop();
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

        try {
            json j = json::parse(file);
            config_.mcp_host = j.value("MCP", json::object()).value("host", config_.mcp_host);
            config_.mcp_port = j.value("MCP", json::object()).value("port", config_.mcp_port);
            config_.mcp_auth_token = j.value("MCP", json::object()).value("auth_token", config_.mcp_auth_token);
            config_.daily_reward = j.value("Economy", json::object()).value("daily_reward", config_.daily_reward);
            config_.work_reward = j.value("Economy", json::object()).value("work_reward", config_.work_reward);
            config_.work_cooldown = j.value("Economy", json::object()).value("work_cooldown", config_.work_cooldown);
            config_.teleport_cooldown = j.value("Teleport", json::object()).value("cooldown", config_.teleport_cooldown);
            config_.default_kit_cooldown = j.value("Kits", json::object()).value("default_cooldown", config_.default_kit_cooldown);
            LogInfo("Config loaded from " + config_path);
        } catch (const std::exception& ex) {
            LogError(std::string("Config parse error: ") + ex.what());
        }
        file.close();
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
        auto path = AsaApi::GetDirectory().GetPluginDirectory(PLUGIN_NAME);
        std::string players_path = path + "/players.json";
        std::string warps_path = path + "/warps.json";
        std::string markers_path = path + "/markers.json";

        try {
            // Save players
            {
                json j;
                std::lock_guard<std::mutex> lock(data_mutex_);
                for (const auto& p : players_) {
                    json player_json;
                    player_json["steam_id"] = std::to_string(p.steam_id);
                    player_json["name"] = p.name;
                    player_json["level"] = p.level;
                    player_json["balance"] = p.balance;
                    player_json["tribe_id"] = p.tribe_id;
                    player_json["is_muted"] = p.is_muted;
                    player_json["home_x"] = p.home_x;
                    player_json["home_y"] = p.home_y;
                    player_json["home_z"] = p.home_z;
                    j.push_back(player_json);
                }
                std::ofstream file(players_path);
                file << j.dump(2);
            }

            // Save warps
            {
                json j;
                std::lock_guard<std::mutex> lock(data_mutex_);
                for (const auto& [name, marker] : warps_) {
                    json m;
                    m["name"] = marker.name;
                    m["x"] = marker.x;
                    m["y"] = marker.y;
                    m["z"] = marker.z;
                    j[name] = m;
                }
                std::ofstream file(warps_path);
                file << j.dump(2);
            }

            LogInfo("All data saved");
        } catch (const std::exception& ex) {
            LogError(std::string("SaveAllData error: ") + ex.what());
        }
    }

    void Plugin::LoadAllData() {
        auto path = AsaApi::GetDirectory().GetPluginDirectory(PLUGIN_NAME);
        std::string players_path = path + "/players.json";
        std::string warps_path = path + "/warps.json";

        try {
            // Load players
            std::ifstream pfile(players_path);
            if (pfile.is_open()) {
                std::lock_guard<std::mutex> lock(data_mutex_);
                json j = json::parse(pfile);
                for (const auto& item : j) {
                    PlayerData p;
                    p.steam_id = std::stoull(item.value("steam_id", "0"));
                    p.name = item.value("name", "");
                    p.level = item.value("level", 1);
                    p.balance = item.value("balance", 0);
                    p.tribe_id = item.value("tribe_id", 0);
                    p.is_muted = item.value("is_muted", false);
                    p.home_x = item.value("home_x", 0.0f);
                    p.home_y = item.value("home_y", 0.0f);
                    p.home_z = item.value("home_z", 0.0f);
                    players_.push_back(p);
                }
                pfile.close();
                LogInfo("Loaded " + std::to_string(players_.size()) + " players");
            }

            // Load warps
            std::ifstream wfile(warps_path);
            if (wfile.is_open()) {
                std::lock_guard<std::mutex> lock(data_mutex_);
                json j = json::parse(wfile);
                for (auto& [name, item] : j.items()) {
                    MapMarker m;
                    m.name = item.value("name", name);
                    m.x = item.value("x", 0.0f);
                    m.y = item.value("y", 0.0f);
                    m.z = item.value("z", 0.0f);
                    warps_[name] = m;
                }
                wfile.close();
                LogInfo("Loaded " + std::to_string(warps_.size()) + " warps");
            }
        } catch (const std::exception& ex) {
            LogError(std::string("LoadAllData error: ") + ex.what());
        }
        LogInfo("Data loaded");
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

    // ─── Helpers ─────────────────────────────────────────────────────────────────

    static uint64 GetSteamIdFromPC(AShooterPlayerController* pc) {
        if (!pc) return 0;
        FString eos_id;
        pc->GetUniqueNetIdAsString(&eos_id);
        try {
            return std::stoull(*eos_id);
        } catch (...) {
            return 0;
        }
    }

    static std::string GetPlayerName(AShooterPlayerController* pc) {
        if (!pc) return "Unknown";
        FString name;
        pc->GetPlayerName(&name);
        return std::string(*name);
    }

    static void SendPlayerPositionSnapshot(AShooterPlayerController* pc) {
        if (!pc) return;

        const uint64 steam_id = GetSteamIdFromPC(pc);
        if (steam_id == 0) return;

        const std::string name = GetPlayerName(pc);
        const int tribe_id = Plugin::Get()->GetPlayerTribeId(pc);
        const FVector location = pc->GetActorLocation();
        const FRotator rotation = pc->GetControlRotation();

        GetMCPBridge()->SendPositionUpdate(
            steam_id,
            name,
            tribe_id,
            location.X,
            location.Y,
            location.Z,
            rotation.Yaw
        );
    }

    static std::string WideToUtf8(const std::wstring& wstr) {
        if (wstr.empty()) return "";
        int size = WideCharToMultiByte(CP_UTF8, 0, wstr.data(), static_cast<int>(wstr.size()), nullptr, 0, nullptr, nullptr);
        std::string result(size, '\0');
        WideCharToMultiByte(CP_UTF8, 0, wstr.data(), static_cast<int>(wstr.size()), result.data(), size, nullptr, nullptr);
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
                uint64 steam_id = GetSteamIdFromPC(new_player);
                std::string name = GetPlayerName(new_player);
                Plugin::Get()->GetOrCreatePlayer(steam_id);
                Plugin::Get()->LogInfo("[Join] " + name + " (" + std::to_string(steam_id) + ")");

                // Send player_connected event to MCP bridge
                GetMCPBridge()->SendPlayerConnected(steam_id, name);
                SendPlayerPositionSnapshot(new_player);
            }

            return result;
        }

        bool Hook_AShooterGameMode_HandlePlayerLogout(
            AShooterGameMode* _this,
            AShooterPlayerController* player)
        {
            auto result = AShooterGameMode_HandlePlayerLogout_original(_this, player);

            if (player) {
                uint64 steam_id = GetSteamIdFromPC(player);
                std::string name = GetPlayerName(player);
                Plugin::Get()->LogInfo("[Leave] " + name + " (" + std::to_string(steam_id) + ")");
                GetMCPBridge()->SendPlayerDisconnected(steam_id, name);

                // Update tribe dinos
                auto* pData = Plugin::Get()->GetPlayerBySteamId(steam_id);
                if (pData && pData->tribe_id > 0) {
                    // Mark tribe dinos as offline (owned by this player)
                }
                Plugin::Get()->SaveAllData();
            }
            return result;
        }

        bool Hook_AShooterGameMode_OnDinoTamed(
            AShooterGameMode* _this,
            AShooterPlayerController* tamer,
            AShooterCharacter* dino,
            FString* species_name)
        {
            auto result = AShooterGameMode_OnDinoTamed_original(_this, tamer, dino, species_name);

            if (tamer && dino && species_name) {
                uint64 steam_id = GetSteamIdFromPC(tamer);
                std::string species = std::string(*species_name);
                // Get dino level from its XP or status values
                int level = 1;
                Plugin::Get()->LogInfo("[Tame] " + GetPlayerName(tamer) + " tamed " + species + " Lv" + std::to_string(level));
                GetMCPBridge()->SendDinoTamed(steam_id, species, level);
            }
            return result;
        }

        bool Hook_AShooterGameMode_OnBabyBorn(
            AShooterGameMode* _this,
            AShooterCharacter* baby,
            AShooterCharacter* mother,
            bool is_from_breeding)
        {
            auto result = AShooterGameMode_OnBabyBorn_original(_this, baby, mother, is_from_breeding);

            if (baby) {
                FString species_fstr;
                baby->GetClass()->GetName(&species_fstr);
                std::string species = std::string(*species_fstr);

                uint64 mother_steam = 0;
                std::string mother_name = "unknown";
                std::string father_name = "unknown";
                if (mother) {
                    mother_steam = GetSteamIdFromPC(reinterpret_cast<AShooterPlayerController*>(mother->OwnerField().Get()));
                    mother_name = GetPlayerName(reinterpret_cast<AShooterPlayerController*>(mother->OwnerField().Get()));
                }

                int level = 1;
                Plugin::Get()->LogInfo("[Born] " + species + " Lv" + std::to_string(level) + " from " + mother_name);
                GetMCPBridge()->SendBabyBorn(mother_steam, species, level, mother_name, father_name);
            }
            return result;
        }

        bool Hook_AShooterGameMode_OnDinoDied(
            AShooterGameMode* _this,
            AShooterCharacter* dino,
            float damage_amount,
            AActor* damage_source)
        {
            auto result = AShooterGameMode_OnDinoDied_original(_this, dino, damage_amount, damage_source);

            if (dino) {
                FString species_fstr;
                dino->GetClass()->GetName(&species_fstr);
                std::string species = std::string(*species_fstr);
                int level = 1;

                uint64 owner_steam = 0;
                if (dino->OwnerField().Get()) {
                    if (auto* pc = reinterpret_cast<AShooterPlayerController*>(dino->OwnerField().Get())) {
                        owner_steam = GetSteamIdFromPC(pc);
                    }
                }

                Plugin::Get()->LogInfo("[Died] " + species + " Lv" + std::to_string(level) + " (owner: " + std::to_string(owner_steam) + ")");
                GetMCPBridge()->SendDinoDied(owner_steam, species, level);
            }
            return result;
        }

        bool Hook_AShooterPlayerController_HandlePlayerLevelUp(
            AShooterPlayerController* _this,
            int new_level)
        {
            auto result = AShooterPlayerController_HandlePlayerLevelUp_original(_this, new_level);

            if (_this) {
                uint64 steam_id = GetSteamIdFromPC(_this);
                auto* pData = Plugin::Get()->GetOrCreatePlayer(steam_id);
                if (pData) pData->level = new_level;
                Plugin::Get()->LogInfo("[LevelUp] " + GetPlayerName(_this) + " reached level " + std::to_string(new_level));
                GetMCPBridge()->SendPlayerLevelUp(steam_id, new_level);
                SendPlayerPositionSnapshot(_this);
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
            AsaApi::GetHooks().SetHook(
                "AShooterGameMode.HandlePlayerLogout_Implementation(AShooterPlayerController*)",
                &Hook_AShooterGameMode_HandlePlayerLogout,
                &AShooterGameMode_HandlePlayerLogout_original);
            AsaApi::GetHooks().SetHook(
                "AShooterGameMode.OnDinoTamed_Implementation(AShooterPlayerController*,AShooterCharacter*,FString*)",
                &Hook_AShooterGameMode_OnDinoTamed,
                &AShooterGameMode_OnDinoTamed_original);
            AsaApi::GetHooks().SetHook(
                "AShooterGameMode.OnBabyBorn_Implementation(AShooterCharacter*,AShooterCharacter*,bool)",
                &Hook_AShooterGameMode_OnBabyBorn,
                &AShooterGameMode_OnBabyBorn_original);
            AsaApi::GetHooks().SetHook(
                "AShooterGameMode.OnDinoDied_Implementation(AShooterCharacter*,float,AActor*)",
                &Hook_AShooterGameMode_OnDinoDied,
                &AShooterGameMode_OnDinoDied_original);
            AsaApi::GetHooks().SetHook(
                "AShooterPlayerController.HandlePlayerLevelUp_Implementation(int)",
                &Hook_AShooterPlayerController_HandlePlayerLevelUp,
                &AShooterPlayerController_HandlePlayerLevelUp_original);
            Log::GetLog()->info("DuckBot hooks registered (6 hooks)");
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
            uint64 steam_id = GetSteamIdFromPC(pc);
            auto* pData = Plugin::Get()->GetPlayerBySteamId(steam_id);
            int tribe_id = Plugin::Get()->GetPlayerTribeId(pc);
            if (tribe_id == 0) {
                Plugin::Get()->SendReply(pc, "[DuckBot] You are not in a tribe.");
                return;
            }
            std::ostringstream oss;
            oss << "[DuckBot] Tribe ID: " << tribe_id;
            if (pData) oss << " | Level: " << pData->level << " | Balance: " << pData->balance;
            oss << " | Dinos tracked: " << Plugin::Get()->GetAllTribes().size();
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnTDinos(AShooterPlayerController* pc, FString* cmd, bool) {
            int tribe_id = Plugin::Get()->GetPlayerTribeId(pc);
            if (tribe_id == 0) {
                Plugin::Get()->SendReply(pc, "[DuckBot] You are not in a tribe.");
                return;
            }
            auto& tribes = Plugin::Get()->GetAllTribes();
            std::ostringstream oss;
            oss << "[DuckBot] Tribe dinos (" << tribe_id << "): ";
            int count = 0;
            for (auto& t : tribes) {
                if (t.tribe_id == tribe_id) {
                    for (auto& d : t.dinos) {
                        if (count++ < 10) oss << d.species << " Lv" << d.level << ", ";
                    }
                    break;
                }
            }
            if (count == 0) oss << "(no dinos tracked yet)";
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnTribeAlert(AShooterPlayerController* pc, FString* cmd, bool) {
            int tribe_id = Plugin::Get()->GetPlayerTribeId(pc);
            if (tribe_id == 0) {
                Plugin::Get()->SendReply(pc, "[DuckBot] You are not in a tribe.");
                return;
            }
            auto& tribes = Plugin::Get()->GetAllTribes();
            int alerts = 0;
            for (auto& t : tribes) {
                if (t.tribe_id == tribe_id) {
                    alerts = t.active_alerts;
                    break;
                }
            }
            if (alerts == 0) {
                Plugin::Get()->SendReply(pc, "[DuckBot] No wild dino alerts near your tribe base.");
            } else {
                std::ostringstream oss;
                oss << "[DuckBot] ALERT: " << alerts << " dangerous wild dinos near your tribe!";
                Plugin::Get()->SendReply(pc, oss.str());
            }
        }

        void OnDinos(AShooterPlayerController* pc, FString* cmd, bool) {
            uint64 steam_id = GetSteamIdFromPC(pc);
            auto& tribes = Plugin::Get()->GetAllTribes();
            std::ostringstream oss;
            oss << "[DuckBot] Your tracked dinos: ";
            int count = 0;
            for (auto& t : tribes) {
                for (auto& d : t.dinos) {
                    if (count++ < 10) oss << d.species << " Lv" << d.level << ", ";
                }
            }
            if (count == 0) oss << "(none tracked yet)";
            Plugin::Get()->SendReply(pc, oss.str());
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

            std::string kit_name = std::string(*parsed[1]);
            auto& kits = Plugin::Get()->GetAllKits();
            KitDefinition* found_kit = nullptr;
            for (auto& k : kits) {
                if (k.name == kit_name) { found_kit = &k; break; }
            }

            if (!found_kit) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Kit not found. Use /kits to see available kits.");
                return;
            }

            // Check permission
            if (!found_kit->required_permission.empty() &&
                !Plugin::Get()->HasPermission(pc, found_kit->required_permission)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] You don't have permission to use this kit.");
                return;
            }

            uint64 steam_id = GetSteamIdFromPC(pc);
            auto now = std::chrono::steady_clock::now();

            // Check cooldown
            auto& cooldowns = Plugin::Get()->GetKitCooldowns();
            auto it = cooldowns.find(steam_id);
            if (it != cooldowns.end()) {
                auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - it->second).count();
                if (elapsed < found_kit->cooldown_seconds) {
                    int remaining = found_kit->cooldown_seconds - elapsed;
                    std::ostringstream oss;
                    oss << "[DuckBot] Kit cooldown active. Wait " << remaining << "s";
                    Plugin::Get()->SendReply(pc, oss.str());
                    return;
                }
            }

            // Grant kit
            if (!found_kit->dino_species.empty()) {
                // Use cheat SpawnDino command to spawn the dino at player's location
                FVector pos = pc->GetActorLocation();
                std::ostringstream oss;
                oss << "cheat SpawnDino \"" << found_kit->dino_species << "\" " << found_kit->dino_level << " " << static_cast<int>(pos.X) << " " << static_cast<int>(pos.Y) << " " << static_cast<int>(pos.Z);
                FString cheat_cmd(oss.str().c_str());
                AsaApi::GetCommands().ExecuteCommand(cheat_cmd);
                oss.str("");
                oss << "[DuckBot] " << found_kit->name << " kit granted! " << found_kit->dino_species << " (Lv" << found_kit->dino_level << ") spawned near you.";
                Plugin::Get()->SendReply(pc, oss.str());
            } else {
                // Use cheat GiveItem command to give kit items
                for (auto& item : found_kit->items) {
                    std::ostringstream oss;
                    oss << "cheat GiveItem \"" << item.item_name << "\" " << item.quantity << " " << item.quality;
                    FString cheat_cmd(oss.str().c_str());
                    AsaApi::GetCommands().ExecuteCommand(cheat_cmd);
                }
                std::ostringstream oss;
                oss << "[DuckBot] " << found_kit->name << " kit granted! (" << found_kit->items.size() << " items)";
                Plugin::Get()->SendReply(pc, oss.str());
            }

            cooldowns[steam_id] = now;
        }

        void OnBal(AShooterPlayerController* pc, FString* cmd, bool) {
            uint64 steam_id = GetSteamIdFromPC(pc);
            auto* pData = Plugin::Get()->GetPlayerBySteamId(steam_id);
            int bal = pData ? pData->balance : 0;
            std::ostringstream oss;
            oss << "[DuckBot] Balance: " << bal << " points";
            Plugin::Get()->SendReply(pc, oss.str());
        }

        // ─── TPR Pending Requests ─────────────────────────────────────────────────────
    static std::unordered_map<uint64, uint64> pending_tpr_; // requester_steamid → target_steamid
    static std::mutex tpr_mutex_;

    void OnHome(AShooterPlayerController* pc, FString* cmd, bool) {
            uint64 steam_id = GetSteamIdFromPC(pc);
            auto* pData = Plugin::Get()->GetPlayerBySteamId(steam_id);
            if (!pData) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Player data not found.");
                return;
            }
            if (pData->home_x == 0 && pData->home_y == 0 && pData->home_z == 0) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Home not set. Use /sethome first.");
                return;
            }

            FVector home_pos(pData->home_x, pData->home_y, pData->home_z);
            pc->SetActorLocation(home_pos, false, nullptr, false);
            std::ostringstream oss;
            oss << "[DuckBot] Teleported to home (" << static_cast<int>(pData->home_x) << ", " << static_cast<int>(pData->home_y) << ", " << static_cast<int>(pData->home_z) << ")";
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnSetHome(AShooterPlayerController* pc, FString* cmd, bool) {
            uint64 steam_id = GetSteamIdFromPC(pc);
            auto* pData = Plugin::Get()->GetOrCreatePlayer(steam_id);

            FVector loc = pc->DefaultPlayerCameraManagerComponent ? pc->GetActorLocation() : FVector{0,0,0};
            // Fallback: try GetActorLocation directly
            FVector pos = pc->GetActorLocation();

            pData->home_x = pos.X;
            pData->home_y = pos.Y;
            pData->home_z = pos.Z;

            std::ostringstream oss;
            oss << "[DuckBot] Home set at (" << static_cast<int>(pos.X) << ", " << static_cast<int>(pos.Y) << ", " << static_cast<int>(pos.Z) << ")";
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnTPR(AShooterPlayerController* pc, FString* cmd, bool) {
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /tpr [player]");
                return;
            }

            uint64 requester = GetSteamIdFromPC(pc);
            std::string target_name = std::string(*parsed[1]);

            // Find target player by name (need to iterate connected players via ApiUtils)
            // For now store pending request
            {
                std::lock_guard<std::mutex> lock(tpr_mutex_);
                pending_tpr_[requester] = 0; // placeholder - needs target steamid resolved
            }
            // Note: target player resolution requires iterating all connected
            // players via ApiUtils — simplified for now
            Plugin::Get()->SendReply(pc, "[DuckBot] Teleport request sent to " + target_name + ". They have 60s to /tpaccept");
        }

        void OnTPAccept(AShooterPlayerController* pc, FString* cmd, bool) {
            uint64 target_steam = GetSteamIdFromPC(pc);

            // Find requester who sent TPR to this player
            uint64 requester = 0;
            {
                std::lock_guard<std::mutex> lock(tpr_mutex_);
                for (auto& [req, tgt] : pending_tpr_) {
                    if (tgt == target_steam) { requester = req; break; }
                }
            }

            if (requester == 0) {
                Plugin::Get()->SendReply(pc, "[DuckBot] No pending teleport request.");
                return;
            }

            {
                std::lock_guard<std::mutex> lock(tpr_mutex_);
                pending_tpr_.erase(requester);
            }

            // Find requester's player controller via ApiUtils
            auto* requester_pc = AsaApi::GetApiUtils().FindPlayerBySteamId(requester);
            if (!requester_pc) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Could not find requester player.");
                return;
            }

            FVector requester_pos = requester_pc->GetActorLocation();
            pc->SetActorLocation(requester_pos, false, nullptr, false);
            Plugin::Get()->SendReply(pc, "[DuckBot] Teleport accepted! You have been teleported to the requester.");
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
            auto it = warps.find(warp_name);
            if (it == warps.end()) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Warp not found.");
                return;
            }

            FVector warp_pos(it->second.x, it->second.y, it->second.z);
            pc->SetActorLocation(warp_pos, false, nullptr, false);
            std::ostringstream oss;
            oss << "[DuckBot] Warped to " << warp_name << " (" << static_cast<int>(it->second.x) << ", " << static_cast<int>(it->second.y) << ", " << static_cast<int>(it->second.z) << ")";
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnSetWarp(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_MOD)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] No permission.");
                return;
            }
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /setwarp [name]");
                return;
            }

            std::string warp_name = std::string(*parsed[1]);
            FVector pos = pc->GetActorLocation();

            MapMarker marker;
            marker.name = warp_name;
            marker.x = pos.X;
            marker.y = pos.Y;
            marker.z = pos.Z;
            marker.created_by = GetSteamIdFromPC(pc);

            Plugin::Get()->GetWarpDB()[warp_name] = marker;

            std::ostringstream oss;
            oss << "[DuckBot] Warp '" << warp_name << "' created at (" << static_cast<int>(pos.X) << ", " << static_cast<int>(pos.Y) << ", " << static_cast<int>(pos.Z) << ")";
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnMarker(AShooterPlayerController* pc, FString* cmd, bool) {
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /marker add|list|remove [name] [type]");
                return;
            }

            std::string action = std::string(*parsed[1]);

            if (action == "list") {
                auto& markers = Plugin::Get()->GetMarkerDB();
                int tribe_id = Plugin::Get()->GetPlayerTribeId(pc);
                if (markers.empty()) {
                    Plugin::Get()->SendReply(pc, "[DuckBot] No markers set.");
                    return;
                }
                std::ostringstream oss;
                oss << "[DuckBot] Markers for tribe " << tribe_id << ": ";
                int count = 0;
                for (auto& [key, m] : markers) {
                    if (count++ < 10) oss << m.name << "(" << static_cast<int>(m.x) << "," << static_cast<int>(m.z) << ") ";
                }
                Plugin::Get()->SendReply(pc, oss.str());
                return;
            }

            if (action == "add") {
                if (!parsed.IsValidIndex(2)) {
                    Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /marker add [name] [type]");
                    return;
                }
                std::string name = std::string(*parsed[2]);
                FVector pos = pc->GetActorLocation();
                MapMarker m;
                m.name = name;
                m.x = pos.X; m.y = pos.Y; m.z = pos.Z;
                m.created_by = GetSteamIdFromPC(pc);
                int tribe_id = Plugin::Get()->GetPlayerTribeId(pc);
                std::string key = std::to_string(tribe_id) + ":" + name;
                Plugin::Get()->GetMarkerDB()[key] = m;
                Plugin::Get()->SendReply(pc, "[DuckBot] Marker '" + name + "' added.");
                return;
            }

            if (action == "remove") {
                if (!parsed.IsValidIndex(2)) {
                    Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /marker remove [name]");
                    return;
                }
                std::string name = std::string(*parsed[2]);
                int tribe_id = Plugin::Get()->GetPlayerTribeId(pc);
                std::string key = std::to_string(tribe_id) + ":" + name;
                auto& markers = Plugin::Get()->GetMarkerDB();
                if (markers.erase(key)) {
                    Plugin::Get()->SendReply(pc, "[DuckBot] Marker '" + name + "' removed.");
                } else {
                    Plugin::Get()->SendReply(pc, "[DuckBot] Marker not found.");
                }
                return;
            }

            Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /marker add|list|remove [name] [type]");
        }

        void OnGridMap(AShooterPlayerController* pc, FString* cmd, bool) {
            // Show all warps and markers as a text-based grid reference
            auto& warps = Plugin::Get()->GetWarpDB();
            auto& markers = Plugin::Get()->GetMarkerDB();
            std::ostringstream oss;
            oss << "[DuckBot] Warps (" << warps.size() << "): ";
            for (auto& [name, w] : warps) {
                oss << name << ", ";
            }
            oss << " | Markers (" << markers.size() << "): ";
            for (auto& [key, m] : markers) {
                oss << m.name << ", ";
            }
            if (warps.empty() && markers.empty()) {
                oss << "(none defined — use /setwarp or /marker add)";
            }
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnKick(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_MOD)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] No permission.");
                return;
            }
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) return;

            std::string target_name = std::string(*parsed[1]);
            // Find target via ApiUtils
            auto* target = AsaApi::GetApiUtils().FindPlayerByName(target_name.c_str());
            if (!target) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Player not found.");
                return;
            }

            FString reason = parsed.IsValidIndex(2) ? parsed[2] : FString(L"Kicked by admin");
            AsaApi::GetCommands().KickPlayer(target, reason);
            Plugin::Get()->SendBroadcast("[DuckBot] " + target_name + " was kicked.");
        }

        void OnBan(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_ADMIN)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] No permission.");
                return;
            }
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) return;

            std::string target_name = std::string(*parsed[1]);
            auto* target = AsaApi::GetApiUtils().FindPlayerByName(target_name.c_str());
            if (!target) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Player not found.");
                return;
            }

            FString reason = parsed.IsValidIndex(2) ? parsed[2] : FString(L"Banned by admin");
            AsaApi::GetCommands().BanPlayer(target, reason);
            Plugin::Get()->SendBroadcast("[DuckBot] " + target_name + " was banned.");
        }

        void OnUnban(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_ADMIN)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] No permission.");
                return;
            }
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) return;

            std::string target_name = std::string(*parsed[1]);
            // Use server console command to remove ban
            FString full_cmd = FString(L"UnbanPlayer ") + FString(target_name.c_str());
            AsaApi::GetCommands().ExecuteCommand(full_cmd);
            Plugin::Get()->SendReply(pc, "[DuckBot] " + target_name + " unbanned.");
        }

        void OnMute(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_MOD)) return;
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) return;

            std::string target_name = std::string(*parsed[1]);
            auto* target = AsaApi::GetApiUtils().FindPlayerByName(target_name.c_str());
            if (!target) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Player not found.");
                return;
            }

            uint64 steam_id = GetSteamIdFromPC(target);
            auto* pData = Plugin::Get()->GetOrCreatePlayer(steam_id);
            pData->is_muted = true;
            Plugin::Get()->SendReply(pc, "[DuckBot] " + target_name + " muted.");
        }

        void OnUnmute(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_MOD)) return;
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) return;

            std::string target_name = std::string(*parsed[1]);
            // Find player in saved data and unmute
            auto& players = Plugin::Get()->GetAllPlayers();
            for (auto& p : players) {
                if (p.name == target_name) {
                    p.is_muted = false;
                    Plugin::Get()->SendReply(pc, "[DuckBot] " + target_name + " unmuted.");
                    return;
                }
            }
            Plugin::Get()->SendReply(pc, "[DuckBot] Player not found.");
        }

        void OnSlay(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_MOD)) return;
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) return;

            std::string target_name = std::string(*parsed[1]);
            auto* target = AsaApi::GetApiUtils().FindPlayerByName(target_name.c_str());
            if (!target) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Player not found.");
                return;
            }

            // Kill the player's character using DestroyActor
            if (target->MyCharacterField().Get()) {
                target->MyCharacterField().Get()->DestroyActor(false, false);
            }
            Plugin::Get()->SendReply(pc, "[DuckBot] " + target_name + " killed.");
        }

        void OnSlayPlayer(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_MOD)) return;
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) return;

            std::string target_name = std::string(*parsed[1]);
            auto* target = AsaApi::GetApiUtils().FindPlayerByName(target_name.c_str());
            if (!target) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Player not found.");
                return;
            }

            // Kill the player character using DestroyActor
            if (target->MyCharacterField().Get()) {
                target->MyCharacterField().Get()->DestroyActor(false, false);
            }
            Plugin::Get()->SendReply(pc, "[DuckBot] " + target_name + " slain.");
        }

        void OnTPHere(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_MOD)) return;
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) return;

            std::string target_name = std::string(*parsed[1]);
            auto* target = AsaApi::GetApiUtils().FindPlayerByName(target_name.c_str());
            if (!target) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Player not found.");
                return;
            }

            FVector pos = pc->GetActorLocation();
            target->SetActorLocation(pos, false, nullptr, false);
            Plugin::Get()->SendReply(pc, "[DuckBot] " + target_name + " teleported to you.");
        }

        void OnFeed(AShooterPlayerController* pc, FString* cmd, bool) {
            uint64 steam_id = GetSteamIdFromPC(pc);
            auto* pData = Plugin::Get()->GetOrCreatePlayer(steam_id);
            int tribe_id = pData ? pData->tribe_id : Plugin::Get()->GetPlayerTribeId(pc);
            if (tribe_id == 0) {
                Plugin::Get()->SendReply(pc, "[DuckBot] You are not in a tribe.");
                return;
            }
            // Use cheat command to force feed all tribe dinos owned by this player
            FString cheat_cmd = FString(L"cheat FeedTribe ") + FString(std::to_string(steam_id).c_str());
            AsaApi::GetCommands().ExecuteCommand(cheat_cmd);

            Plugin::Get()->SendReply(pc, "[DuckBot] Auto-feeding tribe dinos...");
        }

        void OnKibble(AShooterPlayerController* pc, FString* cmd, bool) {
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /kibble [dino species]");
                return;
            }
            std::string species = parsed.IsValidIndex(1) ? std::string(*parsed[1]) : "";
            std::string species_lower = species;
            std::transform(species_lower.begin(), species_lower.end(), species_lower.begin(), ::tolower);

            // Static kibble recipes — species → base ingredient mapping
            // Key = lowercase species match
            static std::unordered_map<std::string, std::string> kibble_recipes = {
                {"archaeopteryx", "1x Simple Bug Meat, 1x Medium Egg, 1x Fiber, 1x Sparkcloud"},
                {"argy",         "1x Prime Meat, 1x Large Egg, 1x Fiber, 1x Rare Mushroom"},
                {"baryonyx",     "1x Raw Prime Meat, 1x Piranha, 1x Fiber, 1x Rare Flower"},
                {"bronto",       "1xVegetables, 2x Fiber, 1x Mega Seed, 1x Sparkcloud"},
                {"camelsaurus",  "1x Cactus Sap, 2x Fiber, 1x Mejooffer, 1x Rare Flower"},
                {"carbonemys",   "1x Superior Kibble, 1x Turtle Shell, 1x Fiber, 1x Rare Mushroom"},
                {"castingraft",  "1x Raw Meat, 1x Fiber, 1x Rock Element, 1x Sparkcloud"},
                {"dilophosaur",  "1x Raw Meat, 2x Fiber, 1x Mejooffer, 1x Rare Flower"},
                {"dimetrodon",   "1x Prime Meat, 1x Fiber, 1x Sparkcloud, 1x Rare Mushroom"},
                {"dimorph",      "1x Raw Meat, 1x Medium Egg, 1x Fiber, 1x Rare Flower"},
                {"giganoto",     "1x Raw Prime Meat, 2x Prime, 1x Exceptional Kibble, 1x Sparkcloud"},
                {"ichthy",       "1x Raw Fish Meat, 1x Piranha, 1x Fiber, 1x Sparkcloud"},
                {"iguanodon",    "1x Citronella, 2x Fiber, 1x Mejooffer, 1x Rare Flower"},
                {"kairuku",      "1x Raw Prime Fish Meat, 1x Pinzon, 1x Fiber, 1x Rare Mushroom"},
                {"kaprosuchus",  "1x Raw Prime Meat, 1x Piranha, 1x Fiber, 1x Rare Flower"},
                {"kentrosaurus", "1x Vegetarians Egg, 2x Fiber, 1x Mejooffer, 1x Rare Mushroom"},
                {"lickatooth",   "1x Raw Prime Meat, 1x Mejooffer, 1x Fiber, 1x Rare Mushroom"},
                {"megalodon",    "1x Raw Prime Meat, 2x Piranha, 1x Exceptional Kibble, 1x Sparkcloud"},
                {"mosasaurus",   "1x Raw Prime Fish Meat, 2x Piranha, 1x Exceptional Kibble, 1x Megacave"},
                {"onyx",         "1x Raw Prime Meat, 2x Prime, 1x Exceptional Kibble, 1x Sparkcloud"},
                {"pachy",        "1x Veggies, 2x Fiber, 1x Mejooffer, 1x Rare Flower"},
                {"paracer",      "1x Veggies, 2x Fiber, 1x Mega Seed, 1x Rare Mushroom"},
                {"pegomastax",   "1x Simple Bug Meat, 1x Fiber, 1x Mejooffer, 1x Rare Flower"},
                {"pelagornis",   "1x Raw Prime Fish Meat, 1x Piranha, 1x Fiber, 1x Rare Flower"},
                {"ptera",        "1x Raw Meat, 1x Small Egg, 1x Fiber, 1x Rare Flower"},
                {"quetzal",      "1x Superior Kibble, 1x Mejooffer, 1x Fiber, 1x Rare Mushroom"},
                {"raptor",       "1x Raw Meat, 1x Medium Egg, 1x Fiber, 1x Rare Flower"},
                {"rex",          "1x Raw Prime Meat, 2x Prime, 1x Exceptional Kibble, 1x Sparkcloud"},
                {"snow owl",     "1x Raw Prime Meat, 1x Large Egg, 1x Fiber, 1x Rare Mushroom"},
                {"spino",        "1x Raw Prime Fish Meat, 1x Piranha, 1x Exceptional Kibble, 1x Sparkcloud"},
                {"stego",        "1x Vegetables, 2x Fiber, 1x Mejooffer, 1x Rare Flower"},
                {"tapejara",     "1x Raw Prime Meat, 1x Large Egg, 1x Fiber, 1x Sparkcloud"},
                {"terror bird", "1x Raw Meat, 1x Medium Egg, 1x Fiber, 1x Rare Flower"},
                {"thorny dragon","1x Veggies, 2x Fiber, 1x Mejooffer, 1x Rare Mushroom"},
                {"triceratops",  "1x Vegetables, 2x Fiber, 1x Mejooffer, 1x Rare Flower"},
                {"troodon",      "1x Raw Prime Meat, 1x Medium Egg, 1x Fiber, 1x Rare Mushroom"},
                {"velonasaur",   "1x Raw Meat, 2x Fiber, 1x Exceptional Kibble, 1x Sparkcloud"},
                {"wyvern",       "1x Raw Prime Meat, 1x Large Egg, 1x Fiber, 1x Exceptional Kibble"},
            };

            auto it = kibble_recipes.find(species_lower);
            std::string recipe;
            if (it != kibble_recipes.end()) {
                recipe = "[DuckBot] Kibble for " + species + ": " + it->second;
            } else {
                recipe = "[DuckBot] Kibble for " + species + ": (unknown species — try: rex, raptor, trike, stego, ptera, wyvern)";
            }
            Plugin::Get()->SendReply(pc, recipe);
        }
        }

        void OnAIBrain(AShooterPlayerController* pc, FString* cmd, bool) {
            bool connected = GetMCPBridge()->IsConnected();
            std::ostringstream oss;
            oss << "[DuckBot] AI Bridge: " << (connected ? "CONNECTED" : "DISCONNECTED");
            oss << " | Host: " << Plugin::Get()->GetConfig().mcp_host << ":" << Plugin::Get()->GetConfig().mcp_port;
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnAIReset(AShooterPlayerController* pc, FString* cmd, bool) {
            Plugin::Get()->SendReply(pc, "[DuckBot] AI context reset for your session.");
        }

        void OnCoinFlip(AShooterPlayerController* pc, FString* cmd, bool) {
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            int wager = parsed.IsValidIndex(1) ? std::stoi(std::string(*parsed[1])) : 0;

            static std::random_device rd;
            static std::mt19937 gen(rd());
            bool result = std::bernoulli_distribution(0.5)(gen);

            std::ostringstream oss;
            if (wager > 0) {
                uint64 steam_id = GetSteamIdFromPC(pc);
                auto* pData = Plugin::Get()->GetOrCreatePlayer(steam_id);
                if (pData->balance < wager) {
                    Plugin::Get()->SendReply(pc, "[DuckBot] Insufficient balance.");
                    return;
                }
                if (result) {
                    pData->balance += wager;
                    oss << "[DuckBot] Coin: HEADS | Wager: " << wager << " | YOU WIN!";
                } else {
                    pData->balance -= wager;
                    oss << "[DuckBot] Coin: TAILS | Wager: " << wager << " | YOU LOSE!";
                }
            } else {
                oss << "[DuckBot] Coin: " << (result ? "HEADS" : "TAILS");
            }
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnDaily(AShooterPlayerController* pc, FString* cmd, bool) {
            uint64 steam_id = GetSteamIdFromPC(pc);
            auto* pData = Plugin::Get()->GetOrCreatePlayer(steam_id);

            auto now = std::chrono::steady_clock::now();
            auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - pData->last_daily).count();

            if (elapsed < 86400) { // 24 hours
                int remaining = 86400 - elapsed;
                std::ostringstream oss;
                oss << "[DuckBot] Daily reward available in " << (remaining / 3600) << "h "
                    << ((remaining % 3600) / 60) << "m";
                Plugin::Get()->SendReply(pc, oss.str());
                return;
            }

            pData->balance += Plugin::Get()->GetConfig().daily_reward;
            pData->last_daily = now;

            std::ostringstream oss;
            oss << "[DuckBot] Daily reward claimed! +" << Plugin::Get()->GetConfig().daily_reward << " points";
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnWork(AShooterPlayerController* pc, FString* cmd, bool) {
            uint64 steam_id = GetSteamIdFromPC(pc);
            auto* pData = Plugin::Get()->GetOrCreatePlayer(steam_id);
            auto now = std::chrono::steady_clock::now();

            int cooldown = Plugin::Get()->GetConfig().work_cooldown;
            auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - pData->last_work).count();

            if (elapsed < cooldown) {
                std::ostringstream oss;
                oss << "[DuckBot] Work cooldown active. Wait " << (cooldown - elapsed) << "s";
                Plugin::Get()->SendReply(pc, oss.str());
                return;
            }

            pData->balance += Plugin::Get()->GetConfig().work_reward;
            pData->last_work = now;

            std::ostringstream oss;
            oss << "[DuckBot] Work done! +" << Plugin::Get()->GetConfig().work_reward << " points";
            Plugin::Get()->SendReply(pc, oss.str());
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
            oss << "MCP Bridge: " << (GetMCPBridge()->IsConnected() ? "CONNECTED" : "DISCONNECTED") << "\n";
            oss << "Version: " << PLUGIN_VERSION;
            Plugin::Get()->SendReply(pc, oss.str());
        }

        void OnEvent(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_ADMIN)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Admin only.");
                return;
            }
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(1)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /event start|stop|list [name]");
                return;
            }

            std::string action = std::string(*parsed[1]);

            if (action == "list") {
                auto& events = Plugin::Get()->GetEventDB();
                if (events.empty()) {
                    Plugin::Get()->SendReply(pc, "[DuckBot] No events defined.");
                    return;
                }
                std::ostringstream oss;
                oss << "[DuckBot] Events: ";
                for (auto& [name, e] : events) {
                    oss << name << "(" << (e.active ? "ACTIVE" : "INACTIVE") << "), ";
                }
                Plugin::Get()->SendReply(pc, oss.str());
                return;
            }

            if (action == "start") {
                if (!parsed.IsValidIndex(2)) {
                    Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /event start [name]");
                    return;
                }
                std::string event_name = std::string(*parsed[2]);
                uint64 steam_id = GetSteamIdFromPC(pc);

                EventDefinition evt;
                evt.name = event_name;
                evt.active = true;
                evt.admin_steam_id = steam_id;
                evt.started_at = std::chrono::steady_clock::now();

                Plugin::Get()->GetEventDB()[event_name] = evt;
                Plugin::Get()->SendBroadcast("[DuckBot] Event '" + event_name + "' has started!");
                return;
            }

            if (action == "stop") {
                if (!parsed.IsValidIndex(2)) {
                    Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /event stop [name]");
                    return;
                }
                std::string event_name = std::string(*parsed[2]);
                auto& events = Plugin::Get()->GetEventDB();
                auto it = events.find(event_name);
                if (it == events.end()) {
                    Plugin::Get()->SendReply(pc, "[DuckBot] Event not found.");
                    return;
                }
                it->second.active = false;
                Plugin::Get()->SendBroadcast("[DuckBot] Event '" + event_name + "' has ended!");
                return;
            }

            Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /event start|stop|list [name]");
        }

        void OnEvents(AShooterPlayerController* pc, FString* cmd, bool) {
            auto& events = Plugin::Get()->GetEventDB();
            int active_count = 0;
            for (auto& [name, e] : events) {
                if (e.active) active_count++;
            }
            if (active_count == 0) {
                Plugin::Get()->SendReply(pc, "[DuckBot] No active events.");
            } else {
                std::ostringstream oss;
                oss << "[DuckBot] " << active_count << " active event(s): ";
                for (auto& [name, e] : events) {
                    if (e.active) oss << name << ", ";
                }
                Plugin::Get()->SendReply(pc, oss.str());
            }
        }

        void OnDrop(AShooterPlayerController* pc, FString* cmd, bool) {
            if (!Plugin::Get()->HasPermission(pc, PERM_ADMIN)) return;

            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            int item_count = parsed.IsValidIndex(1) ? std::stoi(std::string(*parsed[1])) : 10;
            int radius = parsed.IsValidIndex(2) ? std::stoi(std::string(*parsed[2])) : 2000;

            // Use server broadcast and spawn items at random locations near all online players
            std::ostringstream oss;
            oss << "[DuckBot] DROP PARTY! " << item_count << " items raining within " << radius << " units!";
            Plugin::Get()->SendBroadcast(oss.str());

            FString cheat_cmd = FString(L"cheat SpawnResourceDropSpawner ");
            AsaApi::GetCommands().ExecuteCommand(cheat_cmd);

            Plugin::Get()->SendReply(pc, "[DuckBot] Drop party spawned " + std::to_string(item_count) + " items!");
        }

        void OnPay(AShooterPlayerController* pc, FString* cmd, bool) {
            TArray<FString> parsed;
            cmd->ParseIntoArray(parsed, L" ", true);
            if (!parsed.IsValidIndex(2)) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Usage: /pay [player] [amount]");
                return;
            }

            uint64 sender_steam = GetSteamIdFromPC(pc);
            auto* sender = Plugin::Get()->GetPlayerBySteamId(sender_steam);
            if (!sender) sender = Plugin::Get()->GetOrCreatePlayer(sender_steam);

            std::string target_name = std::string(*parsed[1]);
            int amount = std::atoi(std::string(*parsed[2]).c_str());

            if (amount <= 0) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Invalid amount.");
                return;
            }

            if (sender->balance < amount) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Insufficient balance.");
                return;
            }

            // Find target player by name
            auto& all_players = Plugin::Get()->GetAllPlayers();
            PlayerData* target = nullptr;
            for (auto& p : all_players) {
                if (p.name == target_name) {
                    target = &p;
                    break;
                }
            }

            if (!target) {
                Plugin::Get()->SendReply(pc, "[DuckBot] Player not found.");
                return;
            }

            sender->balance -= amount;
            target->balance += amount;

            std::ostringstream oss;
            oss << "[DuckBot] Paid " << amount << " points to " << target_name;
            Plugin::Get()->SendReply(pc, oss.str());
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
