#pragma once

#define PLUGIN_NAME "DuckBot"
#define PLUGIN_VERSION "1.0.0"

#include "../AsaApi/Core/Public/API/Base.h"
#include "../AsaApi/Core/Public/API/Hooks.h"
#include "../AsaApi/Core/Public/API/Commands.h"
#include "../AsaApi/Core/Public/API/Tools/Logger.h"
#include "../AsaApi/Core/Public/API/Tools/Config.h"
#include "../AsaApi/Core/Public/API/Tools/Directory.h"

#include <string>
#include <vector>
#include <unordered_map>
#include <mutex>
#include <optional>
#include <chrono>

namespace DuckBot
{
    // ─── Forward Declarations ─────────────────────────────────────────────────
    class Plugin;

    // ─── Permissions ────────────────────────────────────────────────────────────
    constexpr const char* PERM_ADMIN = "duckbot.admin";
    constexpr const char* PERM_MOD = "duckbot.mod";
    constexpr const char* PERM_VIP = "duckbot.vip";
    constexpr const char* PERM_USE = "duckbot.use";

    // ─── Config ─────────────────────────────────────────────────────────────────
    struct PluginConfig {
        std::string mcp_host = "localhost";
        int mcp_port = 8443;
        std::string mcp_auth_token = "secret";
        int daily_reward = 100;
        int work_reward = 15;
        int work_cooldown = 300;
        int teleport_cooldown = 30;
        int default_kit_cooldown = 3600;
    };

    // ─── Player Data ─────────────────────────────────────────────────────────────
    struct PlayerData {
        uint64 steam_id = 0;
        std::string name;
        int level = 1;
        int balance = 0;
        int tribe_id = 0;
        bool is_muted = false;
        float home_x = 0, home_y = 0, home_z = 0;
        std::chrono::steady_clock::time_point last_work;
        std::chrono::steady_clock::time_point last_daily;
    };

    // ─── Dino Snapshot ────────────────────────────────────────────────────────────
    struct DinoSnapshot {
        uint64 dino_id = 0;
        std::string species;
        int level = 0;
        float health = 1.0f;
        float hunger = 1.0f;
        float pos_x = 0, pos_y = 0, pos_z = 0;
        std::string nickname;
    };

    // ─── Tribe Data ─────────────────────────────────────────────────────────────
    struct TribeData {
        int tribe_id = 0;
        std::string name;
        std::vector<DinoSnapshot> dinos;
        int active_alerts = 0;
    };

    // ─── Kit Definition ─────────────────────────────────────────────────────────
    struct KitItem {
        std::string item_name;
        int quantity = 1;
        int quality = 0;
    };

    struct KitDefinition {
        std::string name;
        std::string description;
        std::vector<KitItem> items;
        int cooldown_seconds = 3600;
        std::string required_permission;
        std::string dino_species;   // if non-empty, spawn a dino instead of giving items
        int dino_level = 30;
    };

    // ─── Map Marker ─────────────────────────────────────────────────────────────
    enum class MarkerType { Base, Farming, Metal, Stone, Cave, Beacon, Danger, Boss, Custom };
    struct MapMarker {
        std::string name;
        float x = 0, y = 0, z = 0;
        MarkerType type = MarkerType::Custom;
        std::string color = "#00FF00";
        int created_by = 0;
    };

    // ─── Plugin Singleton ───────────────────────────────────────────────────────
    class Plugin {
    public:
        static Plugin* Get() { return singleton_; }

        // ─── Lifecycle ─────────────────────────────────────────────────────────
        static void Load();
        static void Unload();

        // ─── Logging ─────────────────────────────────────────────────────────
        void LogInfo(const std::string& msg);
        void LogError(const std::string& msg);

        // ─── Config ─────────────────────────────────────────────────────────
        PluginConfig& GetConfig() { return config_; }
        void ReadConfig();
        void ReloadConfigCmd(AShooterPlayerController* pc, FString* cmd, bool);

        // ─── Player Data ──────────────────────────────────────────────────────
        PlayerData* GetOrCreatePlayer(uint64 steam_id);
        PlayerData* GetPlayerBySteamId(uint64 steam_id);
        int GetPlayerTribeId(AShooterPlayerController* pc);
        void SaveAllData();
        void LoadAllData();

        // ─── Permissions (AsaApi pattern) ───────────────────────────────────────
        bool HasPermission(AShooterPlayerController* pc, const std::string& perm);

        // ─── Messaging (AsaApi pattern) ────────────────────────────────────────
        void SendReply(AShooterPlayerController* pc, const std::string& message);
        void SendReplyToPlayer(AShooterPlayerController* pc, const std::string& message, float r = 1.0f, float g = 1.0f, float b = 1.0f, float a = 1.0f);
        void SendBroadcast(const std::string& message);

        // ─── Data Access ───────────────────────────────────────────────────────
        std::vector<PlayerData>& GetAllPlayers() { return players_; }
        std::vector<TribeData>& GetAllTribes() { return tribes_; }
        std::vector<KitDefinition>& GetAllKits() { return kits_; }
        std::unordered_map<std::string, MapMarker>& GetWarpDB() { return warps_; }
        std::unordered_map<std::string, MapMarker>& GetMarkerDB() { return markers_; }
        std::unordered_map<uint64, std::chrono::steady_clock::time_point>& GetKitCooldowns() { return kit_cooldowns_; }

    private:
        static Plugin* singleton_;
        PluginConfig config_;
        std::vector<PlayerData> players_;
        std::vector<TribeData> tribes_;
        std::vector<KitDefinition> kits_;
        std::unordered_map<std::string, MapMarker> warps_;
        std::unordered_map<std::string, MapMarker> markers_;  // tribe markers keyed by "tribeId:name"
        std::unordered_map<uint64, std::chrono::steady_clock::time_point> kit_cooldowns_;
        std::mutex data_mutex_;

        Plugin() = default;
        ~Plugin() = default;
        Plugin(const Plugin&) = delete;
        Plugin& operator=(const Plugin&) = delete;
    };

    // ─── Chat Command Callbacks (AsaApi signature) ────────────────────────────
    // AsaApi chat command callback signature:
    // void Cmd(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command)
    namespace ChatCommands {
        void OnHelp(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnTribe(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnTDinos(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnTribeAlert(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnDinos(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnKits(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnKit(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnBal(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnHome(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnSetHome(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnTPR(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnTPAccept(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnWarp(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnSetWarp(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnMarker(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnGridMap(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnKick(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnBan(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnUnban(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnMute(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnUnmute(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnSlay(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnSlayPlayer(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnTPHere(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnFeed(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnCoinFlip(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnDaily(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnWork(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnBreeds(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnKibble(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnAIBrain(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnAIReset(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnSave(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnReload(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnStatus(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnEvent(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnEvents(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnDrop(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
        void OnPay(AShooterPlayerController* pc, FString* cmd, bool is_from_logged_command);
    }

    // ─── Rcon Command Callbacks ─────────────────────────────────────────────────
    namespace RconCommands {
        // Rcon callback signature same as chat: (RCONClientConnection*, RCONPacket*, UWorld*)
    }

    // ─── Console Command Callbacks ─────────────────────────────────────────────
    namespace ConsoleCommands {
        void OnReloadConsole(AShooterPlayerController* pc, FString* cmd, bool);
    }

    // ─── Hooks ─────────────────────────────────────────────────────────────────
    namespace Hooks {
        // DECLARE_HOOK callbacks (following AsaApi pattern from Permissions plugin)
        DECLARE_HOOK(AShooterGameMode_HandleNewPlayer, bool, AShooterGameMode*, AShooterPlayerController*, UPrimalPlayerData*, AShooterCharacter*, bool);

        void Init();
    }
}