"""Coarse parameter sweep for the base-break pattern."""
import itertools
import time
import numpy as np
import pandas as pd
from pathlib import Path

from backtest import load_ticker, rolling_bases, run_combo, summarize

BASE = Path(__file__).parent
OUT = BASE / "results"
OUT.mkdir(exist_ok=True)

BASE_LENS = [5, 10, 20, 40]
TIGHTNESS = [0.05, 0.10]
ENTRY_PARAMS = {
    "undercut": [{"undercut_depth": d} for d in (0.005, 0.015)],
    "breakout": [{"breakout_buffer": b} for b in (0.0, 0.005)],
    "bottom": [{"bottom_zone": z} for z in (0.01, 0.02)],
}
STOPS = [0.05, 0.08]
TARGET_R = [2.0]
MAX_HOLD = [20]


def build_grid():
    grid = []
    for entry, plist in ENTRY_PARAMS.items():
        for bl, tn, ep, st, tr, mh in itertools.product(
                BASE_LENS, TIGHTNESS, plist, STOPS, TARGET_R, MAX_HOLD):
            cfg = {"entry": entry, "base_len": bl, "tightness": tn,
                   "stop_pct": st, "target_R": tr, "max_hold": mh,
                   "signal_days": 10, "above_200dma": False}
            cfg.update(ep)
            grid.append(cfg)
    return grid


def main():
    tickers = sorted(p.stem for p in (BASE / "data" / "bars").glob("*.csv"))
    print(f"tickers with data: {len(tickers)}", flush=True)
    dfs = {}
    for t in tickers:
        df = load_ticker(t)
        if df is not None:
            dfs[t] = df
    print(f"usable: {len(dfs)}", flush=True)

    # precompute bases per ticker per (base_len, tightness)
    pre = {}
    for (bl, tn) in itertools.product(BASE_LENS, TIGHTNESS):
        for t, df in dfs.items():
            event, bh, blo = rolling_bases(df, bl, tn)
            pre[(t, bl, tn)] = (df, event, bh, blo)
    print("precompute done", flush=True)

    grid = build_grid()
    print(f"combos: {len(grid)}", flush=True)
    rows = []
    t0 = time.time()
    for gi, cfg in enumerate(grid):
        key = (cfg["base_len"], cfg["tightness"])
        pc = {t: pre[(t, key[0], key[1])] for t in dfs}
        trades = run_combo(list(dfs), cfg, pc)
        s = summarize(trades)
        row = {k: cfg[k] for k in ("entry", "base_len", "tightness", "stop_pct",
                                   "target_R", "max_hold")}
        row.update({k: cfg.get(k) for k in
                    ("undercut_depth", "breakout_buffer", "bottom_zone")})
        if s:
            row.update(s)
        else:
            row.update({"trades": 0})
        rows.append(row)
        if (gi + 1) % 10 == 0:
            el = time.time() - t0
            print(f"{gi+1}/{len(grid)}  {el:.0f}s", flush=True)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "coarse_sweep.csv", index=False)
    print("saved coarse_sweep.csv", flush=True)
    # quick leaderboard
    lb = res[res["trades"] >= 200].sort_values("expectancy_R", ascending=False)
    print(lb.head(15).to_string(), flush=True)


if __name__ == "__main__":
    main()
