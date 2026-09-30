#!/usr/bin/env python3
"""Daily live signal scanner for the base-break strategy.

Mirrors backtest.py exactly (same base detection, trigger, and exit logic).
Run AFTER the daily close:

    python3 live_scan.py --variant breakout

Reads open positions from positions.json, prints today's actions, and writes
signals.json. Entry signals mean: BUY at the NEXT open.

positions.json format (maintained by the trading bot on each fill):
    {"AAPL": {"entry_date": "2026-09-29", "entry_price": 250.10,
              "stop_px": 235.09, "target_px": 295.12, "deadline": "2026-10-27",
              "variant": "breakout"}}
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import rolling_bases, trigger_day
from download import fetch

BASE = Path(__file__).parent
DATA = BASE / "data" / "bars"
STATE = BASE / "positions.json"


def load_params(variant):
    with open(BASE / "strategy_params.json") as f:
        allp = json.load(f)
    p = dict(allp[variant])
    p["entry"] = variant
    p["signal_days"] = allp["screener"]["signal_window_days"]
    return p, allp["screener"]


def get_df(ticker, max_age_h=20):
    """Load cached bars, refreshing from Nasdaq if stale."""
    p = DATA / f"{ticker}.csv"
    stale = True
    if p.exists():
        age_h = (time.time() - p.stat().st_mtime) / 3600
        stale = age_h > max_age_h
    if stale:
        try:
            df = fetch(ticker)
            if df is not None and len(df) > 100:
                df.to_csv(p, index=False)
                return df
        except Exception as e:
            print(f"  refresh failed for {ticker}: {e}")
    if p.exists():
        df = pd.read_csv(p, parse_dates=["Date"])
        return df.sort_values("Date").reset_index(drop=True)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="breakout",
                    choices=["breakout", "undercut", "bottom"])
    args = ap.parse_args()
    cfg, scr = load_params(args.variant)

    tickers = sorted(p.stem for p in DATA.glob("*.csv"))
    positions = json.loads(STATE.read_text()) if STATE.exists() else {}

    ohlc = {}
    for t in tickers:
        df = get_df(t)
        if df is not None and len(df) > 210:
            ohlc[t] = df

    last_date = max(df["Date"].iloc[-1] for df in ohlc.values())
    print(f"variant={args.variant}  last close in data: {last_date.date()}  "
          f"tickers={len(ohlc)}")

    entries, exits, armed = [], [], []
    # --- manage open positions ---
    for t, pos in list(positions.items()):
        df = ohlc.get(t)
        if df is None:
            continue
        m = len(df) - 1
        if pos.get("variant", args.variant) != args.variant:
            continue
        lo, hi, cl = df["Low"].iloc[m], df["High"].iloc[m], df["Close"].iloc[m]
        action = None
        if lo <= pos["stop_px"]:
            action = ("EXIT-STOP", pos["stop_px"])
        elif hi >= pos["target_px"]:
            action = ("EXIT-TARGET", pos["target_px"])
        elif df["Date"].iloc[m] >= pd.to_datetime(pos["deadline"]):
            action = ("EXIT-TIME", cl)
        if action:
            exits.append({"ticker": t, "action": action[0],
                          "price": round(float(action[1]), 2)})
            del positions[t]
        # else: hold (no output)

    # --- scan for new entries ---
    bl, tn = cfg["base_len"], cfg["tightness"]
    for t, df in ohlc.items():
        if t in positions:
            continue
        h = df["High"].to_numpy(); l = df["Low"].to_numpy()
        c = df["Close"].to_numpy(); v = df["Volume"].to_numpy()
        o = df["Open"].to_numpy()
        n = len(df)
        m = n - 1  # today's (last closed) bar
        if o[m] < scr["min_price"]:
            continue
        event, bh, blo = rolling_bases(df, bl, tn)
        if cfg.get("above_200dma") and c[m] < np.mean(c[m - 200:m]):
            continue
        # dollar-volume guard over the base window
        if float(np.mean(c[m - bl + 1:m + 1] * v[m - bl + 1:m + 1])) < scr["min_base_dollar_volume"]:
            continue
        # base events still within the signal window
        sig = cfg["signal_days"]
        cands = [i for i in range(max(bl, m - sig), m)
                 if event[i] and i + sig >= m]
        if not cands:
            continue
        i = cands[-1]  # most recent base
        trig = trigger_day(h, l, c, v, n, i, bh[i], blo[i], cfg)
        if trig == m:
            entries.append({"ticker": t, "action": "BUY-NEXT-OPEN",
                            "base_high": round(float(bh[i]), 2),
                            "base_low": round(float(blo[i]), 2)})
        elif trig < 0:
            armed.append(t)

    print(f"\n--- ENTRIES (buy at next open): {len(entries)} ---")
    for e in entries:
        print(f"  BUY {e['ticker']}  base {e['base_low']:.2f}-{e['base_high']:.2f}")
    print(f"\n--- EXITS: {len(exits)} ---")
    for e in exits:
        print(f"  {e['ticker']} {e['action']} @ {e['price']:.2f}")
    print(f"\n--- ARMED (base formed, watching): {len(armed)} ---")
    if armed:
        print("  " + ", ".join(sorted(armed)[:40])
              + (" ..." if len(armed) > 40 else ""))

    STATE.write_text(json.dumps(positions, indent=1))
    (BASE / "signals.json").write_text(json.dumps(
        {"date": str(last_date.date()), "variant": args.variant,
         "entries": entries, "exits": exits, "armed": sorted(armed)}, indent=1))


if __name__ == "__main__":
    main()
