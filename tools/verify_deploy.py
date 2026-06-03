#!/usr/bin/env python3
"""Pre-flight checks before enabling systemd on VPS."""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path

import httpx


def check_dns(host: str, port: int = 443) -> bool:
    try:
        socket.getaddrinfo(host, port)
        return True
    except socket.gaierror:
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = p.parse_args()
    errors: list[str] = []

    for host in (
        "stream.binance.com",
        "gamma-api.polymarket.com",
        "clob.polymarket.com",
        "ws-subscriptions-clob.polymarket.com",
    ):
        if not check_dns(host):
            errors.append(f"DNS failed: {host}")

    try:
        r = httpx.get("https://api.binance.com/api/v3/ping", timeout=10.0)
        r.raise_for_status()
    except Exception as e:
        errors.append(f"Binance REST ping: {e}")

    env = args.repo / ".env"
    if not env.exists():
        errors.append(f"Missing {env} — copy from .env.example")

    venv_py = args.repo / ".venv" / "bin" / "python"
    if sys.platform == "win32":
        venv_py = args.repo / ".venv" / "Scripts" / "python.exe"
    if not venv_py.exists():
        errors.append("No .venv — run: python -m venv .venv && pip install -e '.[dev]'")

    if errors:
        print("DEPLOY CHECK: FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("DEPLOY CHECK: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
