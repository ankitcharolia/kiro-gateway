# -*- coding: utf-8 -*-
"""
CLI entrypoint for kiro-gateway.

Provides two subcommands:
    serve  — Start the HTTP gateway (FastAPI + uvicorn). This is the default.
    acp    — Run in ACP stdio mode (JSON-RPC 2.0 over stdin/stdout) for IDE
             integration and ACP registry compatibility.

Usage:
    kiro-gateway              # defaults to 'serve'
    kiro-gateway serve        # explicit HTTP server
    kiro-gateway acp          # ACP stdio proxy
"""
from __future__ import annotations

import argparse
import sys


def _cmd_serve(args: argparse.Namespace) -> None:
    """Start the HTTP gateway (existing behaviour from main.py)."""
    # Lazy imports so 'acp' mode doesn't pay the FastAPI/uvicorn startup cost.
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    import uvicorn
    from kiro.config import settings, APP_VERSION

    host = args.host or settings.SERVER_HOST
    port = args.port or settings.SERVER_PORT

    print(f"Kiro Gateway v{APP_VERSION} — starting HTTP server on {host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=False)


def _cmd_acp(args: argparse.Namespace) -> None:
    """Run the ACP stdio proxy."""
    from kiro.acp_stdio import run_acp_stdio
    run_acp_stdio()


def main() -> None:
    """Parse arguments and dispatch to the appropriate subcommand."""
    parser = argparse.ArgumentParser(
        prog="kiro-gateway",
        description="ACP-compliant gateway for Kiro CLI",
    )
    parser.add_argument(
        "-v", "--version", action="store_true",
        help="Print version and exit",
    )

    subparsers = parser.add_subparsers(dest="command")

    # serve (default)
    serve_parser = subparsers.add_parser(
        "serve", help="Start the HTTP gateway (default)",
    )
    serve_parser.add_argument(
        "-H", "--host", default=None, metavar="HOST",
        help="Bind address (default: SERVER_HOST env or 0.0.0.0)",
    )
    serve_parser.add_argument(
        "-p", "--port", type=int, default=None, metavar="PORT",
        help="Bind port (default: SERVER_PORT env or 8000)",
    )

    # acp
    subparsers.add_parser(
        "acp", help="Run in ACP stdio mode (JSON-RPC over stdin/stdout)",
    )

    args = parser.parse_args()

    if args.version:
        from kiro.config import APP_VERSION
        print(f"kiro-gateway {APP_VERSION}")
        sys.exit(0)

    # Default to 'serve' when no subcommand is given.
    if args.command is None or args.command == "serve":
        # If no subcommand, create a Namespace with serve defaults.
        if args.command is None:
            args.host = None
            args.port = None
        _cmd_serve(args)
    elif args.command == "acp":
        _cmd_acp(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
