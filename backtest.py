"""
Base-break pattern backtester.

Pattern: stock goes sideways (tight N-day range) -> entry via one of:
  - undercut : dips below base low, then reclaims it (enter)
  - breakout : closes above base high (+buffer)
  - bottom   : trades down into the bottom zone of the base (accumulate)

Exits: fixed % stop, profit target as multiple of stop (R), time stop.
Costs: slippage 5bps per side. Entries filled at next open.
"""
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data" / "bars"

SLIPPAGE = 0.0005  # per side


def load_ticker(t):
    p = DATA / f"{t}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p, parse_dates=["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    # basic sanity: drop rows with bad data
    df = df[(df["Close"] > 0) & (df["High"] >= df["Low"])].reset_index(drop=True)
    if len(df) < 250:
        return None
    return df


def rolling_bases(df, base_len, tightness):
    """Return arrays: event (base completion), base_high, base_low per day."""
    n = len(df)
    high = df["High"].to_numpy()
    low = df["Low"].to_numpy()
    close = df["Close"].to_numpy()
    s_high = pd.Series(high)
    s_low = pd.Series(low)
    rmax = s_high.rolling(base_len, min_periods=base_len).max().to_numpy()
    rmin = s_low.rolling(base_len, min_periods=base_len).min().to_numpy()
    width = (rmax - rmin) / np.where(close == 0, np.nan, close)
    valid = (width <= tightness) & ~np.isnan(width)
    # base completion events: False->True transitions, with cooldown = base_len
    event = np.zeros(n, dtype=bool)
    last = -10**9
    for i in range(n):
        if valid[i] and not (i > 0 and valid[i - 1]) and i - last >= base_len:
            event[i] = True
            last = i
    return event, rmax, rmin


def trigger_day(h, l, c, v, n, i, bh, bl, cfg):
    """First trigger day j in (i, i+signal_days], capped so j+1 < n (next open exists).
    Returns -1 if no trigger. Shared by the backtester and the live scanner."""
    entry = cfg["entry"]
    sig_days = cfg.get("signal_days", 10)
    end = min(i + 1 + sig_days, n - 1)
    if entry == "undercut":
        md = cfg["undercut_depth"]
        for j in range(i + 1, end):
            if l[j] <= bl * (1 - md) and c[j] > bl:
                return j
    elif entry == "breakout":
        buf = cfg["breakout_buffer"]
        vol_mult = cfg.get("vol_mult", 0)
        for j in range(i + 1, end):
            if c[j] > bh * (1 + buf):
                if vol_mult and j >= 20:
                    if v[j] < vol_mult * np.mean(v[j - 20:j]):
                        continue
                return j
    elif entry == "bottom":
        zone = cfg["bottom_zone"]
        for j in range(i + 1, end):
            if l[j] <= bl * (1 + zone):
                return j
    return -1


def find_trades(df, event_idx, base_high, base_low, cfg):
    """Simulate trades for one ticker given base events. Returns list of dicts."""
    o = df["Open"].to_numpy()
    h = df["High"].to_numpy()
    l = df["Low"].to_numpy()
    c = df["Close"].to_numpy()
    v = df["Volume"].to_numpy()
    n = len(df)
    stop_pct = cfg["stop_pct"]
    target = cfg["target_R"] * stop_pct
    max_hold = cfg["max_hold"]
    min_dvol = cfg.get("min_dollar_vol", 1_000_000)

    trades = []
    busy_until = -1  # no overlapping positions
    for i in event_idx:
        if i + 2 >= n - 1 or i < busy_until:
            continue
        bh, bl = base_high[i], base_low[i]
        if not np.isfinite(bh) or not np.isfinite(bl) or bh <= bl:
            continue
        # liquidity filter: avg dollar volume over base
        dvol = float(np.mean(c[i - cfg["base_len"] + 1:i + 1] * v[i - cfg["base_len"] + 1:i + 1]))
        if dvol < min_dvol:
            continue
        # optional regime filter
        if cfg.get("above_200dma"):
            if i < 200 or c[i] < np.mean(c[i - 200:i]):
                continue

        trig = trigger_day(h, l, c, v, n, i, bh, bl, cfg)
        if trig < 0:
            continue
        ep = o[trig + 1]  # enter next open
        if ep <= 0 or ep < 5:  # penny-stock guard
            continue
        stop_px = ep * (1 - stop_pct)
        tgt_px = ep * (1 + target)
        exit_px, exit_day, why = None, None, None
        last_day = min(trig + 1 + max_hold, n - 1)
        for k in range(trig + 2, last_day + 1):
            if l[k] <= stop_px:  # stop first on ambiguous days (conservative)
                exit_px, exit_day, why = stop_px, k, "stop"
                break
            if h[k] >= tgt_px:
                exit_px, exit_day, why = tgt_px, k, "target"
                break
        if exit_px is None:
            exit_px, exit_day, why = c[last_day], last_day, "time"
        gross = exit_px / ep - 1
        net = gross - 2 * SLIPPAGE
        trades.append({
            "entry_idx": trig + 1, "exit_idx": exit_day,
            "ret": net, "r_mult": net / stop_pct,
            "why": why, "hold": exit_day - trig - 1,
        })
        busy_until = exit_day + 1
    return trades


def run_combo(tickers, cfg, precomputed):
    """precomputed: dict ticker -> (df, event, base_high, base_low) for this base_len/tightness."""
    all_trades = []
    for t in tickers:
        pc = precomputed.get(t)
        if pc is None:
            continue
        df, event, bh, bl = pc
        idx = np.flatnonzero(event)
        if len(idx) == 0:
            continue
        for tr in find_trades(df, idx, bh, bl, cfg):
            tr["ticker"] = t
            all_trades.append(tr)
    return all_trades


def summarize(trades):
    if not trades:
        return None
    r = np.array([t["ret"] for t in trades])
    rm = np.array([t["r_mult"] for t in trades])
    wins = r[r > 0]
    losses = r[r <= 0]
    n = len(r)
    tot = float(np.sum(r))
    avg = float(np.mean(r))
    win_rate = float(len(wins) / n)
    avg_win = float(np.mean(wins)) if len(wins) else 0.0
    avg_loss = float(np.mean(losses)) if len(losses) else 0.0
    pf = float(-np.sum(wins) / np.sum(losses)) if len(losses) and np.sum(losses) != 0 else float("inf")
    exp_r = float(np.mean(rm))
    # max drawdown on cumulative trade-return curve
    cum = np.cumsum(r)
    dd = float(np.max(np.maximum.accumulate(cum) - cum)) if n else 0.0
    return {
        "trades": n, "win_rate": win_rate, "total_ret": tot,
        "avg_ret": avg, "expectancy_R": exp_r,
        "avg_win": avg_win, "avg_loss": avg_loss,
        "profit_factor": pf, "max_dd": dd,
        "avg_hold": float(np.mean([t["hold"] for t in trades])),
    }
