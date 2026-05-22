# Graceful Shutdown

Initiates a graceful server shutdown with timed player warnings before the server goes down. Players receive countdown notifications at 5, 4, 3, 2, 1 minutes, then 30s, and 10s before shutdown. The server saves world data before exiting to prevent data loss.

Use this before planned maintenance, server updates, or restarts. All connected players will see the broadcast warnings.

## Triggers
shutdown, graceful shutdown, restart server, save and shutdown, 关机

## Examples
"shutdown the server in 10 minutes for maintenance"
"restart the server with 5 minute warning"
"save world and shutdown gracefully"

## Auto-Trigger-On

## Tier
admin