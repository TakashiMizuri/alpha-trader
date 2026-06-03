"""Configuration dataclasses — phase 1+."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArbConfig:
    min_edge: float = 0.03
    min_tau_sec: float = 30.0
    taker_fee: float = 0.01
    sigma_ewma_span: int = 60


@dataclass(frozen=True)
class MMConfig:
    quote_half_spread: float = 0.02
    min_tau_sec: float = 30.0
    max_inventory: float = 100.0


@dataclass(frozen=True)
class LoggerConfig:
    interval_ms: int = 250
    sigma_floor_ann: float = 0.15


@dataclass(frozen=True)
class RebateConfig:
    entry_minutes_before: int = 15
    force_flat_minutes_before: int = 1
    entry_offset_from_mid: float = 0.01
    exit_offset_from_mid: float = 0.01
    quote_relative_to_mid: bool = True
    max_mid_deviation: float = 0.04
