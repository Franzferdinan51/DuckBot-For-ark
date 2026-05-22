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

namespace DuckBot
{
    // ─── Forward Declarations ─────────────────────────────────────────────────
    class Plugin;
    class TribeCommandHub;
    class KitSystem;
    class EconomySystem;
    class TeleportSystem;
    class ModerationSystem;
    class DinoTracker;
    class MapMarkerSystem;
    class ChatGamesSystem;
    class EventSystem;
    class MCPBridge;

    // ─── Permissions ────────────────────────────────────────────────────────────
    constexpr const char* PERM_ADMIN = "duckbot.admin";
    constexpr const char* PERM_MOD = "duckbot.mod";
    constexpr const char* PERM_VIP = "duckbot.vip";
    constexpr const char* PERM_USE = "duckbot.use";

    // ─── Helpers ────────────────────────────────────────────────────────────────
    inline std::string to_lower(const std::string& s) {
        std::string r = s;
        std::transform(r.begin(), r.end(), r.begin(), ::tolower);
        return r;
    }

    inline std::vector<std::string> split_args(const std::string& str, int argc, const char* argv[]) {
        std::vector<std::string> args;
        for (int i = 0; i < argc; ++i) if (argv[i]) args.push_back(argv[i]);
        return args;
    }

    // ─── Config ───────────────────────────────────────────────────────────────────
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
        uint64 tribe_id = 0;
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
        uint64 tribe_id = 0;
        std::string name;
        std::vector<DinoSnapshot> dinos;
        std::vector<PlayerData*> members;
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
    };

    // ─── Map Marker ─────────────────────────────────────────────────────────────
    enum class MarkerType { Base, Farming, Metal, Stone, Cave, Beacon, Danger, Boss, Custom };
    struct MapMarker {
        std::string name;
        float x = 0, y = 0, z = 0;
        MarkerType type = MarkerType::Custom;
        std::string color = "#00FF00";
    };

    // ─── Plugin ─────────────────────────────────────────────────────────────────
    class Plugin {
    public:
        static Plugin* Get() { return singleton_; }
        static void Init();
        static void Shutdown();

        // ─── Logging ─────────────────────────────────────────────────────────
        void LogInfo(const std::string& msg);
        void LogError(const std::string& msg);
        void LogDebug(const std::string& msg);

        // ─── Config ─────────────────────────────────────────────────────────
        PluginConfig& GetConfig() { return config_; }
        void LoadConfig();
        void SaveConfig();

        // ─── Player Data ──────────────────────────────────────────────────────
        PlayerData* GetOrCreatePlayer(uint64 steam_id);
        PlayerData* GetPlayer(uint64 steam_id);
        void SavePlayerData();
        void LoadPlayerData();

        // ─── Permissions ──────────────────────────────────────────────────────
        bool HasPermission(uint64 steam_id, const std::string& perm);

        // ─── Chat Reply ──────────────────────────────────────────────────────
        void SendReply(uint64 steam_id, const std::string& message);
        void SendBroadcast(const std::string& message);

        // ─── Data Access ───────────────────────────────────────────────────────
        std::vector<PlayerData>& GetAllPlayers() { return players_; }
        std::vector<TribeData>& GetAllTribes() { return tribes_; }
        std::vector<KitDefinition>& GetAllKits() { return kits_; }
        std::unordered_map<std::string, MapMarker>& GetWarpDatabase() { return warps_; }

        // ─── MCP Bridge ─────────────────────────────────────────────────────
        MCPBridge* GetMCPBridge() { return mcp_bridge_; }

    private:
        static Plugin* singleton_;
        PluginConfig config_;
        std::vector<PlayerData> players_;
        std::vector<TribeData> tribes_;
        std::vector<KitDefinition> kits_;
        std::unordered_map<std::string, MapMarker> warps_;
        std::mutex data_mutex_;

        Plugin() = default;
        ~Plugin() = default;
        Plugin(const Plugin&) = delete;
        Plugin& operator=(const Plugin&) = delete;

        MCPBridge* mcp_bridge_ = nullptr;
    };

    // ─── Command Handlers ──────────────────────────────────────────────────────
    namespace Commands {
        void OnTribeCommand(void* player, int argc, const char** argv);
        void OnTDinosCommand(void* player, int argc, const char** argv);
        void OnTribeAlertCommand(void* player, int argc, const char** argv);
        void OnDinosCommand(void* player, int argc, const char** argv);
        void OnKitCommand(void* player, int argc, const char** argv);
        void OnKitsCommand(void* player, int argc, const char** argv);
        void OnBalCommand(void* player, int argc, const char** argv);
        void OnHomeCommand(void* player, int argc, const char** argv);
        void OnSetHomeCommand(void* player, int argc, const char** argv);
        void OnTPRCommand(void* player, int argc, const char** argv);
        void OnTPAcceptCommand(void* player, int argc, const char** argv);
        void OnWarpCommand(void* player, int argc, const char** argv);
        void OnSetWarpCommand(void* player, int argc, const char** argv);
        void OnMarkerCommand(void* player, int argc, const char** argv);
        void OnGridMapCommand(void* player, int argc, const char** argv);
        void OnKickCommand(void* player, int argc, const char** argv);
        void OnBanCommand(void* player, int argc, const char** argv);
        void OnMuteCommand(void* player, int argc, const char** argv);
        void OnSlayCommand(void* player, int argc, const char** argv);
        void OnFeedCommand(void* player, int argc, const char** argv);
        void OnCoinFlipCommand(void* player, int argc, const char** argv);
        void OnAIBrainCommand(void* player, int argc, const char** argv);
        void OnReloadCommand(void* player, int argc, const char** argv);
        void OnSaveCommand(void* player, int argc, const char** argv);
        void OnStatusCommand(void* player, int argc, const char** argv);
        void OnDailyCommand(void* player, int argc, const char** argv);
        void OnWorkCommand(void* player, int argc, const char** argv);
        void OnBreedsCommand(void* player, int argc, const char** argv);
        void OnKibbleCommand(void* player, int argc, const char** argv);
        void OnHelpCommand(void* player, int argc, const char** argv);
        void OnEventCommand(void* player, int argc, const char** argv);
        void OnEventsCommand(void* player, int argc, const char** argv);
        void OnDropCommand(void* player, int argc, const char** argv);
    }

    // ─── Hook Callbacks ─────────────────────────────────────────────────────────
    namespace Hooks {
        void OnPlayerConnected(void* player);
        void OnPlayerDisconnected(void* player);
        void OnChatMessage(void* player, const char* message, int mode);
        void OnDinoTamed(void* player, void* dino);
        void OnBabyBorn(void* baby, void* mother, void* player);
        void OnDinoDied(void* dino, void* killer);
        void OnPlayerLevelUp(void* player, int new_level);
    }
}