#!/usr/bin/env python3
"""Backtest runner — phase 2+."""

from __future__ import annotations

import argparse


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sleeve", choices=["arb", "mm", "rebate"], required=True)
    p.add_argument("--years", nargs="+", type=int)
    p.add_argument("--lag-ms", type=float)
    args = p.parse_args()
    raise NotImplementedError("run_backtest is implemented in phase 2")


if __name__ == "__main__":
    main()
