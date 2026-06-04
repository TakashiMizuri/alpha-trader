"""Market log formats: v3 CSV (default) + legacy JSONL compact rows."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_FORMAT_VERSION = 3

# v3: first column is row kind (0=tick, 1=settle); only ``sym`` is a string.
TICK_COLS: tuple[str, ...] = (
    "t",
    "sym",
    "te",
    "tr",
    "tp",
    "w",
    "tau",
    "s0",
    "st",
    "sig",
    "ps",
    "pm",
    "pu",
    "yb",
    "ya",
    "mk",
    "pc",
)
SETTLE_COLS: tuple[str, ...] = (
    "sym",
    "w",
    "t",
    "s0",
    "st",
    "ps",
    "pm",
    "gap",
    "up",
    "us",
    "upm",
    "src",
    "mk",
)

SRC_TO_CODE: dict[str, int] = {
    "gamma": 0,
    "spot_proxy": 1,
    "mock_spot": 2,
}
CODE_TO_SRC: dict[int, str] = {v: k for k, v in SRC_TO_CODE.items()}

V3_HEADER_LINES: tuple[str, ...] = (
    f"# alpha-trader market log v{LOG_FORMAT_VERSION}",
    f"# tick: {','.join(TICK_COLS)}",
    f"# settle: {','.join(SETTLE_COLS)}",
    "# src: 0=gamma 1=spot_proxy 2=mock_spot",
    "# upm: -1 = PM outcome not available (used spot)",
)


def _ms_to_iso(ms: int | float) -> str:
    dt = datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _iso_to_ms(iso: str) -> int:
    s = iso.rstrip("Z")
    if "." in s:
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f")
    else:
        dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _window_id(symbol: str, window_t0_ms: int) -> str:
    prefix = symbol.lower().replace("usdt", "")[:8]
    return f"{prefix}_5m_{window_t0_ms // 1000}"


def _split_csv_line(line: str) -> list[str]:
    return next(csv.reader(io.StringIO(line)))


def ensure_log_header(path: Path) -> None:
    """Write v3 column header once when creating a new log file."""
    if path.exists() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        for h in V3_HEADER_LINES:
            f.write(h + "\n")


def build_compact_row(
    *,
    symbol: str,
    window_t0_ms: int,
    ts_ms: int,
    b_event_ms: int,
    b_recv_ms: int,
    pm_recv_ms: int,
    s0: float,
    s_t: float,
    sigma: float,
    tau: float,
    p_star: float,
    p_mid: float,
    p_micro: float,
    bid: float,
    ask: float,
    pm_mock: bool,
    pm_connected: bool,
) -> dict[str, Any]:
    return {
        "t": ts_ms,
        "sym": symbol,
        "te": b_event_ms,
        "tr": b_recv_ms,
        "tp": pm_recv_ms,
        "w": window_t0_ms,
        "tau": round(tau, 3),
        "s0": round(s0, 6),
        "st": round(s_t, 6),
        "sig": round(sigma, 4),
        "ps": round(p_star, 4),
        "pm": round(p_mid, 4),
        "pu": round(p_micro, 4),
        "yb": round(bid, 4),
        "ya": round(ask, 4),
        "mock": int(pm_mock),
        "pc": int(pm_connected),
    }


def is_settle_row(row: dict[str, Any]) -> bool:
    return row.get("type") == "settle"


def build_settle_row(
    *,
    symbol: str,
    window_t0_ms: int,
    ts_ms: int,
    s0: float,
    s_t: float,
    p_star: float,
    p_mid: float,
    outcome_up: bool,
    outcome_up_spot: bool,
    outcome_source: str,
    outcome_up_pm: bool | None = None,
    pm_mock: bool = False,
    pm_slug: str | None = None,
) -> dict[str, Any]:
    gap = round(p_mid - p_star, 4)
    row: dict[str, Any] = {
        "type": "settle",
        "sym": symbol,
        "w": window_t0_ms,
        "t": ts_ms,
        "s0": round(s0, 6),
        "st": round(s_t, 6),
        "ps": round(p_star, 4),
        "pm": round(p_mid, 4),
        "gap": gap,
        "up": int(outcome_up),
        "up_spot": int(outcome_up_spot),
        "src": outcome_source,
        "mock": int(pm_mock),
    }
    if outcome_up_pm is not None:
        row["up_pm"] = int(outcome_up_pm)
    if pm_slug:
        row["slug"] = pm_slug
    return row


def _tick_csv_value(row: dict[str, Any], col: str) -> str:
    if col == "mk":
        return str(int(row.get("mock", row.get("mk", 0))))
    return str(row[col])


def _serialize_tick_csv(row: dict[str, Any]) -> str:
    fields = ["0"] + [_tick_csv_value(row, c) for c in TICK_COLS]
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(fields)
    return buf.getvalue()


def _serialize_settle_csv(row: dict[str, Any]) -> str:
    src = SRC_TO_CODE.get(str(row.get("src", "spot_proxy")), 1)
    upm = row.get("up_pm")
    upm_s = "-1" if upm is None else str(int(upm))
    fields = [
        "1",
        str(row["sym"]),
        str(int(row["w"])),
        str(int(row["t"])),
        str(row["s0"]),
        str(row["st"]),
        str(row["ps"]),
        str(row["pm"]),
        str(row["gap"]),
        str(int(row["up"])),
        str(int(row["up_spot"])),
        upm_s,
        str(src),
        str(int(row.get("mock", 0))),
    ]
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(fields)
    return buf.getvalue()


def serialize_row(row: dict[str, Any]) -> str:
    """v3 CSV line (see V3_HEADER_LINES)."""
    if is_settle_row(row):
        return _serialize_settle_csv(row)
    return _serialize_tick_csv(row)


def _parse_tick_csv(parts: list[str]) -> dict[str, Any]:
    vals = parts[1 : 1 + len(TICK_COLS)]
    if len(vals) != len(TICK_COLS):
        raise ValueError(f"tick field count {len(vals)} != {len(TICK_COLS)}")
    raw = dict(zip(TICK_COLS, vals, strict=True))
    return {
        "t": int(float(raw["t"])),
        "sym": raw["sym"].strip(),
        "te": int(float(raw["te"])),
        "tr": int(float(raw["tr"])),
        "tp": int(float(raw["tp"])),
        "w": int(float(raw["w"])),
        "tau": float(raw["tau"]),
        "s0": float(raw["s0"]),
        "st": float(raw["st"]),
        "sig": float(raw["sig"]),
        "ps": float(raw["ps"]),
        "pm": float(raw["pm"]),
        "pu": float(raw["pu"]),
        "yb": float(raw["yb"]),
        "ya": float(raw["ya"]),
        "mock": int(float(raw["mk"])),
        "pc": int(float(raw["pc"])),
    }


def _parse_settle_csv(parts: list[str]) -> dict[str, Any]:
    vals = parts[1 : 1 + len(SETTLE_COLS)]
    if len(vals) != len(SETTLE_COLS):
        raise ValueError(f"settle field count {len(vals)} != {len(SETTLE_COLS)}")
    row: dict[str, Any] = {"type": "settle"}
    for k, v in zip(SETTLE_COLS, vals, strict=True):
        row[k] = v.strip() if k == "sym" else v
    row["sym"] = str(row["sym"])
    row["w"] = int(float(row["w"]))
    row["t"] = int(float(row["t"]))
    for k in ("s0", "st", "ps", "pm", "gap"):
        row[k] = float(row[k])
    row["up"] = int(float(row["up"]))
    row["up_spot"] = int(float(row["us"]))
    upm = int(float(row["upm"]))
    row["up_pm"] = None if upm < 0 else bool(upm)
    row["src"] = CODE_TO_SRC.get(int(float(row["src"])), "spot_proxy")
    row["mock"] = int(float(row["mk"]))
    del row["us"]
    del row["upm"]
    del row["mk"]
    return row


def parse_log_line(line: str) -> dict[str, Any] | None:
    """Parse one log line (v3 CSV, legacy JSON, or None for comments)."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("{"):
        return json.loads(line)
    parts = _split_csv_line(line)
    if not parts:
        return None
    kind = parts[0]
    if kind == "0":
        return _parse_tick_csv(parts)
    if kind == "1":
        return _parse_settle_csv(parts)
    raise ValueError(f"unknown row kind {kind!r}")


def load_log_file(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = parse_log_line(line)
        if row is not None:
            rows.append(row)
    return rows


def expand_settle_row(row: dict[str, Any]) -> dict[str, Any]:
    w_ms = int(row.get("w", 0))
    sym = row.get("sym") or row.get("symbol", "BTCUSDT")
    p_star = float(row.get("ps", row.get("p_star", 0.5)))
    p_mid = float(row.get("pm", row.get("p_mkt_mid", 0.5)))
    src = row.get("src", "unknown")
    if isinstance(src, (int, float)):
        src = CODE_TO_SRC.get(int(src), "spot_proxy")
    out: dict[str, Any] = {
        "type": "settle",
        "ts_utc": _ms_to_iso(row.get("t", w_ms)),
        "symbol": sym,
        "window_id": _window_id(sym, w_ms),
        "window_t0_ms": w_ms,
        "s0": row.get("s0"),
        "s_t": row.get("st", row.get("s_t")),
        "p_star": p_star,
        "p_mkt_mid": p_mid,
        "gap_level": row.get("gap", round(p_mid - p_star, 4)),
        "outcome_up": bool(row.get("up", row.get("outcome_up", 0))),
        "outcome_up_spot": bool(row.get("up_spot", row.get("us", 0))),
        "outcome_source": src,
        "mock_pm": bool(row.get("mock", 0)),
    }
    if row.get("up_pm") is not None:
        out["outcome_up_pm"] = bool(row["up_pm"])
    if row.get("slug"):
        out["pm_slug"] = row["slug"]
    return out


def is_compact_tick_row(row: dict[str, Any]) -> bool:
    return "t" in row and "ts_utc" not in row and not is_settle_row(row)


def is_compact_row(row: dict[str, Any]) -> bool:
    return is_compact_tick_row(row)


def expand_log_row(row: dict[str, Any]) -> dict[str, Any]:
    if is_settle_row(row):
        return expand_settle_row(row)
    if not is_compact_tick_row(row):
        out = dict(row)
        if "gap_level" not in out and "p_mkt_mid" in out and "p_star" in out:
            out["gap_level"] = round(out["p_mkt_mid"] - out["p_star"], 4)
        if "spread_pm" not in out and "yes_ask" in out and "yes_bid" in out:
            out["spread_pm"] = round(out["yes_ask"] - out["yes_bid"], 4)
        return out

    sym = row["sym"]
    w_ms = int(row["w"])
    p_mid = float(row["pm"])
    p_star = float(row["ps"])
    bid = float(row["yb"])
    ask = float(row["ya"])
    return {
        "ts_utc": _ms_to_iso(row["t"]),
        "symbol": sym,
        "ts_binance_event": _ms_to_iso(row["te"]),
        "ts_recv": _ms_to_iso(row["tr"]),
        "ts_pm_recv": _ms_to_iso(row["tp"]),
        "window_id": _window_id(sym, w_ms),
        "window_t0_ms": w_ms,
        "tau_sec": row["tau"],
        "s0": row["s0"],
        "s_t": row["st"],
        "sigma_ann": row["sig"],
        "p_star": p_star,
        "p_mkt_mid": p_mid,
        "p_mkt_micro": row["pu"],
        "yes_bid": bid,
        "yes_ask": ask,
        "gap_level": round(p_mid - p_star, 4),
        "spread_pm": round(ask - bid, 4),
        "mock_pm": bool(row.get("mock", 0)),
        "pm_connected": bool(row.get("pc", 0)),
        "_tick_ms": int(row["t"]),
    }


def tick_interval_ms(rows: list[dict[str, Any]]) -> float | None:
    if len(rows) < 2:
        return None
    ts: list[int] = []
    for r in rows:
        if "_tick_ms" in r:
            ts.append(int(r["_tick_ms"]))
        elif "t" in r:
            ts.append(int(r["t"]))
        elif "ts_utc" in r:
            ts.append(_iso_to_ms(r["ts_utc"]))
    if len(ts) < 2:
        return None
    deltas = [ts[i] - ts[i - 1] for i in range(1, len(ts)) if ts[i] >= ts[i - 1]]
    if not deltas:
        return None
    deltas.sort()
    return float(deltas[len(deltas) // 2])
