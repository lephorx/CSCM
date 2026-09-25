#!/usr/bin/env python3
"""
CLI entry point for provisioning a Minecraft server.

Delegates to server_manager.provision_server().  Useful for quick testing
without running the full Flask API.

Usage:
    python main.py
    python main.py --name "Survival SMP" --type forge --version 1.20.1 --port 25570
    python main.py --help
"""

import sys
import argparse
from server_manager import provision_server, SERVER_TYPES
from logger import get_logger

log = get_logger("cli")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision a Minecraft server, PlayIT tunnel, and optional Cloudflare DNS."
    )
    parser.add_argument("--name",    default="Minecraft test server",   help="Server display name")
    parser.add_argument("--type",    default="paper", choices=list(SERVER_TYPES.keys()), help="Server flavour (includes 'bedrock')")
    parser.add_argument("--version", default="1.21.4",                  help="Minecraft version (use 'LATEST' for bedrock)")
    parser.add_argument("--port",    type=int, default=25565,           help="Local server port (19132 is bedrock's default)")
    parser.add_argument("--mem-min", type=int, default=2,               help="Minimum JVM heap (GB)")
    parser.add_argument("--mem-max", type=int, default=4,               help="Maximum JVM heap (GB)")
    parser.add_argument("--local-only", action="store_true",            help="Skip the PlayIT tunnel — LAN/same-network access only")
    args = parser.parse_args()

    log.info(
        "Starting server provisioning: name=%s, type=%s, version=%s, port=%d, local_only=%s",
        args.name, args.type, args.version, args.port, args.local_only,
    )

    result = provision_server(
        server_name=args.name,
        server_type=args.type,
        version=args.version,
        server_port=args.port,
        mem_min=args.mem_min,
        mem_max=args.mem_max,
        local_only=args.local_only,
    )

    if result["success"]:
        log.info("Provisioning complete")
        print()
        print(f"  Server ID       : {result['server_id']}")
        if result.get("local_only"):
            print(f"  Local only      : port {result['port']} (no public tunnel created)")
        else:
            print(f"  Connect address : {result['connect_address']}")
            print(f"  External port   : {result.get('external_port', 'N/A')}")
        print()
    else:
        log.error("Provisioning failed: %s", result["message"])
        sys.exit(1)


if __name__ == "__main__":
    main()
