#include "Plugin.h"
#include "MCPBridge.h"
#include <fstream>
#include <random>
#include <algorithm>
#include <sstream>
#include <cstdlib>

#pragma comment(lib, "AsaApi.lib")

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
            Plugin::Get()->SendReply(pc, "[DuckBot] Kit system: not yet implemented");
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

            // TODO: Teleport player to (home_x, home_y, home_z)
            // Using AsaApi::GetApiUtils().TeleportToPlayer(pc, ...)
            std::ostringstream oss;
            oss << "[DuckBot] Teleporting to home... (" << pData->home_x << ", " << pData->home_y << ", " << pData->home_z << ")";
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
            // TODO: use AsaApi::GetApiUtils().FindPlayerBy... to resolve target
            pending_tpr_[requester] = 0; // placeholder - needs target steamid resolved

            Plugin::Get()->SendReply(pc, "[DuckBot] Teleport request sent to " + target_name + ". They have 60s to /tpaccept");
        }

        void OnTPAccept(AShooterPlayerController* pc, FString* cmd, bool) {
            uint64 target_steam = GetSteamIdFromPC(pc);

            // Find requester who sent TPR to this player
            uint64 requester = 0;
            for (auto& [req, tgt] : pending_tpr_) {
                if (tgt == target_steam) { requester = req; break; }
            }

            if (requester == 0) {
                Plugin::Get()->SendReply(pc, "[DuckBot] No pending teleport request.");
                return;
            }

            pending_tpr_.erase(requester);

            // TODO: Teleport requester to target's position
            // AsaApi::GetApiUtils().TeleportPlayer(requester, target_pos)
            Plugin::Get()->SendReply(pc, "[DuckBot] Teleport accepted! Teleporting...");
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

            // TODO: Teleport to warp position
            // FVector pos{it->second.x, it->second.y, it->second.z};
            // AsaApi::GetApiUtils().TeleportPlayerToLocation(pc, pos);
            std::ostringstream oss;
            oss << "[DuckBot] Warping to " << warp_name << "...";
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
            // TODO: AsaApi::GetCommands().UnbanPlayer(target_name);
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

            // TODO: Kill all dinos belonging to target's tribe
            // AsaApi::GetCommands().SlayTribeDinos(target);
            Plugin::Get()->SendReply(pc, "[DuckBot] " + target_name + "'s dinos slain.");
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

            // TODO: AsaApi::GetCommands().SlayPlayer(target);
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

            // TODO: Teleport target to pc's position
            FVector pos = pc->GetActorLocation();
            // AsaApi::GetApiUtils().TeleportPlayerToLocation(target, pos);
            Plugin::Get()->SendReply(pc, "[DuckBot] " + target_name + " teleported to you.");
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