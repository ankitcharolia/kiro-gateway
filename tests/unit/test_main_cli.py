"""Unit tests for main.py CLI argument parsing."""
from __future__ import annotations

import subprocess
import sys


def test_help_shows_host_option():
    result = subprocess.run(
        [sys.executable, "main.py", "--help"],
        capture_output=True, text=True,
    )
    assert "--host" in result.stdout or "-H" in result.stdout


def test_help_shows_port_option():
    result = subprocess.run(
        [sys.executable, "main.py", "--help"],
        capture_output=True, text=True,
    )
    assert "--port" in result.stdout or "-p" in result.stdout


def test_parse_args_host():
    from main import _parse_args
    args = _parse_args.__wrapped__() if hasattr(_parse_args, "__wrapped__") else None
    # Just verify _parse_args is callable and returns a Namespace
    import argparse
    # Monkeypatch sys.argv
    import sys as _sys
    old = _sys.argv
    _sys.argv = ["main.py", "--host", "127.0.0.1"]
    try:
        from main import _parse_args as _f
        ns = _f()
        assert ns.host == "127.0.0.1"
    finally:
        _sys.argv = old


def test_parse_args_port():
    import sys as _sys
    old = _sys.argv
    _sys.argv = ["main.py", "--port", "9000"]
    try:
        from main import _parse_args as _f
        ns = _f()
        assert ns.port == 9000
    finally:
        _sys.argv = old


def test_parse_args_defaults_are_none():
    import sys as _sys
    old = _sys.argv
    _sys.argv = ["main.py"]
    try:
        from main import _parse_args as _f
        ns = _f()
        assert ns.host is None
        assert ns.port is None
    finally:
        _sys.argv = old
