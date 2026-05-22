#pragma once

#include "Plugin.h"

#include <string>
#include <vector>
#include <functional>
#include <mutex>
#include <atomic>

namespace DuckBot
{
    // ─── WebSocket Message ───────────────────────────────────────────────────
    struct WSMessage {
        std::string type;      // "event" for game events, "player_message" for chat
        std::string sub_type;  // e.g. "player_connected", "dino_tamed" — the actual event type
        std::string data;      // JSON payload
        int request_id = 0;
    };

    // ─── MCP Bridge Client ─────────────────────────────────────────────────────
    // Connects to the sheldon Python MCP bridge via WebSocket.
    // Sends game events (tame, born, death, levelup) and receives commands.

    class MCPBridgeClient {
    public:
        using MessageHandler = std::function<void(const WSMessage&)>;
        using ConnectionHandler = std::function<void(bool connected)>;

        MCPBridgeClient();
        ~MCPBridgeClient();

        // Start/stop the connection
        void Start(const std::string& host, int port, const std::string& auth_token);
        void Stop();

        // Send a message to the bridge (async, queued)
        void Send(const WSMessage& msg);

        // Register callbacks
        void OnMessage(MessageHandler handler) { message_handler_ = handler; }
        void OnConnectionChange(ConnectionHandler handler) { conn_handler_ = handler; }

        // Connection state
        bool IsConnected() const { return connected_.load(); }

        // Event senders — call these from hook callbacks
        void SendPlayerConnected(uint64 steam_id, const std::string& name);
        void SendPlayerDisconnected(uint64 steam_id, const std::string& name);
        void SendDinoTamed(uint64 steam_id, const std::string& species, int level);
        void SendBabyBorn(uint64 steam_id, const std::string& species, int level,
                          const std::string& mother, const std::string& father);
        void SendDinoDied(uint64 steam_id, const std::string& species, int level);
        void SendPlayerLevelUp(uint64 steam_id, int new_level);
        void SendPositionUpdate(
            uint64 steam_id,
            const std::string& name,
            int tribe_id,
            float x,
            float y,
            float z,
            float facing_yaw
        );

    private:
        void ConnectLoop();       // background thread: connect + recv loop
        void SendThread();        // background thread: send queue drain
        void ProcessMessage(const std::string& json);

        std::string host_;
        int port_;
        std::string auth_token_;
        std::atomic<bool> running_{false};
        std::atomic<bool> connected_{false};

        // Winsock
        SOCKET socket_ = INVALID_SOCKET;
        std::thread connect_thread_;
        std::thread send_thread_;

        // Queues
        std::vector<WSMessage> send_queue_;
        std::mutex send_mutex_;
        std::condition_variable send_cv_;

        // Callbacks
        MessageHandler message_handler_;
        ConnectionHandler conn_handler_;
    };

    // ─── Singleton accessor ───────────────────────────────────────────────────
    MCPBridgeClient* GetMCPBridge();
}
