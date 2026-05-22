"""Command-line interface for the Sheldon Bridge."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

import aiohttp
from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(
        prog="sheldon-bridge",
        description="Sheldon AI Bridge — LLM-powered assistant for ARK: Survival Ascended",
    )
    subparsers = parser.add_subparsers(dest="command")

    # init command
    init_parser = subparsers.add_parser("init", help="Create a new config file")
    init_parser.add_argument(
        "--path", default="config.json", help="Config file path (default: config.json)"
    )

    # run command
    run_parser = subparsers.add_parser("run", help="Start the bridge server")
    run_parser.add_argument(
        "--config", default="config.json", help="Config file path (default: config.json)"
    )
    run_parser.add_argument(
        "--env-file", default=None, help="Path to .env file for API keys"
    )
    run_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )

    # secret command
    secret_parser = subparsers.add_parser("secret", help="Generate a new shared secret")

    # serve command — lightweight HTTP server for health checks / config
    serve_parser = subparsers.add_parser(
        "serve",
        help="Run a lightweight HTTP server for health checks and config without the full WS bridge",
    )
    serve_parser.add_argument(
        "--config", default="config.json", help="Config file path"
    )
    serve_parser.add_argument(
        "--port", type=int, default=8080, help="HTTP port (default: 8080)"
    )
    serve_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )

    serve_parser.add_argument(
        "--config", default="config.json", help="Config file path"
    )
    serve_parser.add_argument(
        "--port", type=int, default=8080, help="HTTP port (default: 8080)"
    )
    serve_parser.add_argument(
        "--env-file", default=None, help="Path to .env file for API keys"
    )
    serve_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )

    args = parser.parse_args()

    if args.command == "init":
        from sheldon_bridge.config import initialize_config
        initialize_config(args.path)

    elif args.command == "run":
        # Load .env file if specified
        env_file = getattr(args, "env_file", None)
        if env_file:
            load_dotenv(env_file)
        else:
            # Try common locations
            for env_path in [".env", Path.home() / ".sheldon-bridge.env"]:
                if Path(env_path).exists():
                    load_dotenv(env_path)
                    break

        # Configure logging
        log_level = logging.DEBUG if args.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Load config
        from sheldon_bridge.config import load_config
        config = load_config(args.config)

        # Load knowledge base
        from sheldon_bridge.tools.knowledge import load_data
        load_data(config.data_dirs)

        # Run server
        from sheldon_bridge.server import run_server
        asyncio.run(run_server(config))

    elif args.command == "secret":
        from sheldon_bridge.auth import TokenAuthenticator
        secret = TokenAuthenticator.generate_secret()
        print(f"Generated secret: {secret}")
        print("Add this to both your bridge config.json and your mod's GameUserSettings.ini")

    elif args.command == "serve":
        # Load .env
        env_file = getattr(args, "env_file", None)
        if env_file:
            load_dotenv(env_file)
        else:
            for env_path in [".env", Path.home() / ".sheldon-bridge.env"]:
                if Path(env_path).exists():
                    load_dotenv(env_path)
                    break

        log_level = logging.DEBUG if args.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        from sheldon_bridge.config import load_config
        from sheldon_bridge.rest_admin import create_rest_app
        from aiohttp import web

        config = load_config(args.config)

        async def run_serve(port: int) -> None:
            async def health_only(request):
                return web.json_response({"status": "ok", "service": "duckbot-bridge"})

            app = create_rest_app(config, None)
            app.router.add_get("/health", health_only)

            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", port)
            await site.start()
            print(f"DuckBot Bridge HTTP server running on http://0.0.0.0:{port}")
            print("Endpoints:")
            print(f"  GET /health       — health check")
            print(f"  GET /api/v1/announce  — arkduckbot:// discovery")
            print(f"  GET /api/v1/server-info  — server info")
            print()
            print("Press Ctrl+C to stop.")

            stop = asyncio.get_event_loop().create_future()

            def handle_signal():
                if not stop.done():
                    stop.set_result(None)

            for sig in (signal.SIGTERM, signal.SIGINT):
                asyncio.get_event_loop().add_signal_handler(sig, handle_signal)

            await stop
            await runner.cleanup()
            print("Server stopped.")

        asyncio.run(run_serve(args.port))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
