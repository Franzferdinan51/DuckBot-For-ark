#include "MCPBridge.h"
#include "Plugin.h"

#pragma comment(lib, "ws2_32.lib")

namespace DuckBot
{
    // ─── Base64 encode ─────────────────────────────────────────────────────
    static std::string Base64Encode(const unsigned char* data, size_t len) {
        static const char b64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        std::string out;
        for (size_t i = 0; i < len; i += 3) {
            int a = data[i];
            int b = (i + 1 < len) ? data[i + 1] : 0;
            int c = (i + 2 < len) ? data[i + 2] : 0;
            out += b64[a >> 2];
            out += b64[((a & 3) << 4) | (b >> 4)];
            out += (i + 1 < len) ? b64[((b & 15) << 2) | (c >> 6)] : '=';
            out += (i + 2 < len) ? b64[c & 63] : '=';
        }
        return out;
    }

    // ─── SHA1 (for WebSocket handshake) ───────────────────────────────────
    // Simplified SHA1 for WebSocket key processing
    static void SHA1(const unsigned char* data, size_t len, unsigned char* out) {
        // Use Windows CryptGenRandom for simplicity or a simple static salt
        // Actually we'll use a simpler approach: Windows built-in crypto API
        HCRYPTPROV prov = 0;
        if (CryptAcquireContext(&prov, nullptr, nullptr, PROV_RSA_FULL, CRYPT_VERIFYCONTEXT)) {
           HCRYPTHASH hash = 0;
            if (CryptCreateHash(prov, CALG_SHA1, 0, 0, &hash)) {
                CryptHashData(hash, data, len, 0);
                DWORD hashLen = 20;
                CryptGetHashParam(hash, HP_HASHVALUE, out, &hashLen, 0);
                CryptDestroyHash(hash);
            }
            CryptReleaseContext(prov, 0);
        }
        // Fallback: zero out
        memset(out, 0, 20);
    }

    // ─── WebSocket Frame ───────────────────────────────────────────────────
    static std::vector<unsigned char> BuildWSFrame(const std::string& text) {
        std::vector<unsigned char> frame;
        frame.push_back(0x81); // FIN + text frame
        size_t len = text.size();
        if (len < 126) {
            frame.push_back(static_cast<unsigned char>(len));
        } else if (len < 65536) {
            frame.push_back(126);
            frame.push_back((len >> 8) & 0xFF);
            frame.push_back(len & 0xFF);
        } else {
            frame.push_back(127);
            for (int i = 7; i >= 0; --i)
                frame.push_back((len >> (i * 8)) & 0xFF);
        }
        for (char c : text)
            frame.push_back(static_cast<unsigned char>(c));
        return frame;
    }

    static std::string DecodeWSFrame(const unsigned char* data, size_t len, size_t& out_len) {
        if (len < 2) return "";
        int opcode = data[0] & 0x0F;
        bool fin = (data[0] & 0x80) != 0;
        int maskbit = (data[1] & 0x80) ? 1 : 0;
        int payload_len = data[1] & 0x7F;

        size_t header_len = 2;
        if (payload_len == 126) header_len = 4;
        else if (payload_len == 127) header_len = 10;

        if (maskbit) header_len += 4;
        if (len < header_len) return "";

        size_t pos = header_len;
        int mask_key = maskbit ? (data[header_len - 4] | (data[header_len - 3] << 8) |
                                  (data[header_len - 2] << 16) | (data[header_len - 1] << 24)) : 0;

        std::string result;
        for (size_t i = 0; i < payload_len && pos < len; ++i, ++pos) {
            char c = static_cast<char>(data[pos] ^ (maskbit ? ((mask_key >> ((i % 4) * 8)) & 0xFF) : 0));
            result += c;
        }
        out_len = header_len + payload_len;
        return result;
    }

    // ─── MCPBridgeClient ───────────────────────────────────────────────────

    MCPBridgeClient::MCPBridgeClient() {
        // Initialize Winsock
        WSADATA wsaData;
        WSAStartup(MAKEWORD(2, 2), &wsaData);
    }

    MCPBridgeClient::~MCPBridgeClient() {
        Stop();
        WSACleanup();
    }

    void MCPBridgeClient::Start(const std::string& host, int port, const std::string& auth_token) {
        host_ = host;
        port_ = port;
        auth_token_ = auth_token;
        running_ = true;
        connected_ = false;

        connect_thread_ = std::thread([this]() { ConnectLoop(); });
        send_thread_ = std::thread([this]() { SendThread(); });
    }

    void MCPBridgeClient::Stop() {
        running_ = false;
        if (socket_ != INVALID_SOCKET) {
            closesocket(socket_);
            socket_ = INVALID_SOCKET;
        }
        connected_ = false;
        send_cv_.notify_all();
        if (connect_thread_.joinable()) connect_thread_.join();
        if (send_thread_.joinable()) send_thread_.join();
    }

    void MCPBridgeClient::Send(const WSMessage& msg) {
        std::lock_guard<std::mutex> lock(send_mutex_);
        send_queue_.push_back(msg);
        send_cv_.notify_one();
    }

    void MCPBridgeClient::ConnectLoop() {
        while (running_) {
            // Resolve host
            struct hostent* he = gethostbyname(host_.c_str());
            if (!he) {
                Plugin::Get()->LogError("MCPBridge: failed to resolve " + host_);
                std::this_thread::sleep_for(std::chrono::seconds(5));
                continue;
            }

            // Create socket
            socket_ = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
            if (socket_ == INVALID_SOCKET) {
                Plugin::Get()->LogError("MCPBridge: socket creation failed");
                std::this_thread::sleep_for(std::chrono::seconds(5));
                continue;
            }

            // Connect
            struct sockaddr_in addr;
            addr.sin_family = AF_INET;
            addr.sin_port = htons(static_cast<unsigned short>(port_));
            addr.sin_addr = *((struct in_addr*)he->h_addr);

            if (connect(socket_, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
                Plugin::Get()->LogError("MCPBridge: connect failed to " + host_ + ":" + std::to_string(port_));
                closesocket(socket_);
                socket_ = INVALID_SOCKET;
                std::this_thread::sleep_for(std::chrono::seconds(5));
                continue;
            }

            // WebSocket handshake (RFC 6455)
            // Generate a 16-byte random key
            unsigned char key_bytes[16];
            HCRYPTPROV prov = 0;
            if (CryptAcquireContext(&prov, nullptr, nullptr, PROV_RSA_FULL, CRYPT_VERIFYCONTEXT)) {
                CryptGenRandom(prov, 16, key_bytes);
                CryptReleaseContext(prov, 0);
            } else {
                srand(static_cast<unsigned>(time(nullptr)));
                for (int i = 0; i < 16; ++i) key_bytes[i] = static_cast<unsigned char>(rand() % 256);
            }
            std::string key_b64 = Base64Encode(key_bytes, 16);

            std::string handshake = "GET / HTTP/1.1\r\n";
            handshake += "Host: " + host_ + ":" + std::to_string(port_) + "\r\n";
            handshake += "Upgrade: websocket\r\n";
            handshake += "Connection: Upgrade\r\n";
            handshake += "Sec-WebSocket-Key: " + key_b64 + "\r\n";
            handshake += "Sec-WebSocket-Version: 13\r\n";
            handshake += "\r\n";

            if (send(socket_, handshake.c_str(), static_cast<int>(handshake.size()), 0) < 0) {
                Plugin::Get()->LogError("MCPBridge: handshake send failed");
                closesocket(socket_);
                socket_ = INVALID_SOCKET;
                std::this_thread::sleep_for(std::chrono::seconds(5));
                continue;
            }

            // Read handshake response
            char resp[512];
            int received = recv(socket_, resp, sizeof(resp) - 1, 0);
            if (received <= 0) {
                Plugin::Get()->LogError("MCPBridge: no handshake response");
                closesocket(socket_);
                socket_ = INVALID_SOCKET;
                std::this_thread::sleep_for(std::chrono::seconds(5));
                continue;
            }
            resp[received] = '\0';

            // Check for "HTTP/1.1 101" in response
            if (strstr(resp, "101") == nullptr) {
                Plugin::Get()->LogError("MCPBridge: handshake failed - no 101 response");
                closesocket(socket_);
                socket_ = INVALID_SOCKET;
                std::this_thread::sleep_for(std::chrono::seconds(5));
                continue;
            }

            connected_ = true;
            Plugin::Get()->LogInfo("MCPBridge: connected to " + host_ + ":" + std::to_string(port_));
            if (conn_handler_) conn_handler_(true);

            // Send auth message
            std::string auth_json = "{"
                "\"type\":\"auth\","
                "\"token\":\"" + auth_token_ + "\","
                "\"player\":{"
                    "\"player_id\":\"server_plugin\","
                    "\"display_name\":\"DuckBot\","
                    "\"tier\":\"admin\""
                "}"
            "}";
            auto frame = BuildWSFrame(auth_json);
            send(socket_, reinterpret_cast<const char*>(frame.data()), static_cast<int>(frame.size()), 0);

            // Receive loop
            std::vector<unsigned char> recv_buf;
            while (running_ && connected_) {
                char chunk[4096];
                int n = recv(socket_, chunk, sizeof(chunk), 0);
                if (n <= 0) break;
                for (int i = 0; i < n; ++i) recv_buf.push_back(static_cast<unsigned char>(chunk[i]));

                // Process complete frames
                size_t offset = 0;
                while (offset < recv_buf.size()) {
                    size_t frame_len = 0;
                    std::string msg = DecodeWSFrame(recv_buf.data() + offset, recv_buf.size() - offset, frame_len);
                    if (frame_len == 0) break;
                    if (!msg.empty()) ProcessMessage(msg);
                    offset += frame_len;
                }
                if (offset > 0) {
                    recv_buf.erase(recv_buf.begin(), recv_buf.begin() + static_cast<long>(offset));
                }
            }

            connected_ = false;
            if (conn_handler_) conn_handler_(false);
            closesocket(socket_);
            socket_ = INVALID_SOCKET;
            Plugin::Get()->LogInfo("MCPBridge: disconnected, reconnecting in 5s...");
            std::this_thread::sleep_for(std::chrono::seconds(5));
        }
    }

    void MCPBridgeClient::SendThread() {
        while (running_) {
            std::string next_msg;
            {
                std::unique_lock<std::mutex> lock(send_mutex_);
                send_cv_.wait_for(lock, std::chrono::seconds(1), [this] {
                    return !send_queue_.empty() || !running_;
                });
                if (!running_) break;
                if (send_queue_.empty()) continue;
                // Build JSON from message
                auto& msg = send_queue_.front();
                std::string json = "{\"type\":\"" + msg.type + "\",\"data\":" + msg.data + ",\"request_id\":" + std::to_string(msg.request_id) + "}";
                send_queue_.erase(send_queue_.begin());
                next_msg = std::move(json);
            }
            if (!next_msg.empty() && connected_) {
                auto frame = BuildWSFrame(next_msg);
                int sent = send(socket_, reinterpret_cast<const char*>(frame.data()), static_cast<int>(frame.size()), 0);
                if (sent < 0) {
                    // Will reconnect in ConnectLoop
                }
            }
        }
    }

    void MCPBridgeClient::ProcessMessage(const std::string& json) {
        try {
            json j = json::parse(json);
            WSMessage msg;
            msg.type = j.value("type", "");
            msg.data = j.value("data", "{}");
            msg.request_id = j.value("request_id", 0);
            if (message_handler_) message_handler_(msg);
        } catch (...) {
            // Ignore parse errors
        }
    }

    // ─── Event Senders ─────────────────────────────────────────────────────────

    void MCPBridgeClient::SendPlayerConnected(uint64 steam_id, const std::string& name) {
        json data = {
            {"steam_id", std::to_string(steam_id)},
            {"name", name},
            {"event", "player_connected"}
        };
        Send({"event", data.dump()});
    }

    void MCPBridgeClient::SendPlayerDisconnected(uint64 steam_id, const std::string& name) {
        json data = {
            {"steam_id", std::to_string(steam_id)},
            {"name", name},
            {"event", "player_disconnected"}
        };
        Send({"event", data.dump()});
    }

    void MCPBridgeClient::SendDinoTamed(uint64 steam_id, const std::string& species, int level) {
        json data = {
            {"steam_id", std::to_string(steam_id)},
            {"species", species},
            {"level", level},
            {"event", "dino_tamed"}
        };
        Send({"event", data.dump()});
    }

    void MCPBridgeClient::SendBabyBorn(uint64 steam_id, const std::string& species, int level,
                                        const std::string& mother, const std::string& father) {
        json data = {
            {"steam_id", std::to_string(steam_id)},
            {"species", species},
            {"level", level},
            {"mother", mother},
            {"father", father},
            {"event", "baby_born"}
        };
        Send({"event", data.dump()});
    }

    void MCPBridgeClient::SendDinoDied(uint64 steam_id, const std::string& species, int level) {
        json data = {
            {"steam_id", std::to_string(steam_id)},
            {"species", species},
            {"level", level},
            {"event", "dino_died"}
        };
        Send({"event", data.dump()});
    }

    void MCPBridgeClient::SendPlayerLevelUp(uint64 steam_id, int new_level) {
        json data = {
            {"steam_id", std::to_string(steam_id)},
            {"level", new_level},
            {"event", "player_levelup"}
        };
        Send({"event", data.dump()});
    }

    // ─── Singleton ────────────────────────────────────────────────────────────
    static std::unique_ptr<MCPBridgeClient> g_mcp_bridge;

    MCPBridgeClient* GetMCPBridge() {
        if (!g_mcp_bridge) {
            g_mcp_bridge = std::make_unique<MCPBridgeClient>();
        }
        return g_mcp_bridge.get();
    }
}