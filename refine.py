"""Refined sweep: structure around coarse winners, then exits for finalists."""
import itertools
import time
import numpy as np
import pandas as pd
from pathlib import Path

from backtest import load_ticker, rolling_bases, run_combo, summarize

BASE = Path(__file__).parent
OUT = BASE / "results"

STOPS = [0.05]
TRS = [2.0]
HOLDS = [20]


def stage_a_grid():
    g = []
    for bl, tn, d, dma in itertools.product(
            [10, 20, 40, 60], [0.08, 0.10, 0.12], [0.01, 0.015, 0.02], [False, True]):
        g.append({"entry": "undercut", "base_len": bl, "tightness": tn,
                  "undercut_depth": d, "above_200dma": dma,
                  "stop_pct": 0.05, "target_R": 2.0, "max_hold": 20, "signal_days": 10})
    for bl, tn, buf, vm, dma in itertools.product(
            [5, 10, 20, 40], [0.08, 0.10, 0.12], [0.0, 0.005], [0, 1.5], [False, True]):
        g.append({"entry": "breakout", "base_len": bl, "tightness": tn,
                  "breakout_buffer": buf, "vol_mult": vm, "above_200dma": dma,
                  "stop_pct": 0.05, "target_R": 2.0, "max_hold": 20, "signal_days": 10})
    for bl, tn, z, dma in itertools.product(
            [3, 5, 10], [0.08, 0.10, 0.12], [0.01, 0.02, 0.03], [False, True]):
        g.append({"entry": "bottom", "base_len": bl, "tightness": tn,
                  "bottom_zone": z, "above_200dma": dma,
                  "stop_pct": 0.05, "target_R": 2.0, "max_hold": 20, "signal_days": 10})
    return g


def run_grid(grid, pre, dfs, label):
    rows = []
    t0 = time.time()
    for gi, cfg in enumerate(grid):
        key = (cfg["base_len"], cfg["tightness"])
        pc = {t: pre[(t, key[0], key[1])] for t in dfs}
        trades = run_combo(list(dfs), cfg, pc)
        s = summarize(trades)
        row = dict(cfg)
        row.update(s or {"trades": 0})
        rows.append(row)
        if (gi + 1) % 40 == 0:
            print(f"{label} {gi+1}/{len(grid)} {time.time()-t0:.0f}s", flush=True)
    return pd.DataFrame(rows)


def main():
    tickers = sorted(p.stem for p in (BASE / "data" / "bars").glob("*.csv"))
    dfs = {}
    for t in tickers:
        df = load_ticker(t)
        if df is not None:
            dfs[t] = df
    print(f"usable: {len(dfs)}", flush=True)

    pairs = set()
    for bl in [3, 5, 10, 20, 40, 60]:
        for tn in [0.08, 0.10, 0.12]:
            pairs.add((bl, tn))
    pre = {}
    for (bl, tn) in pairs:
        for t, df in dfs.items():
            event, bh, blo = rolling_bases(df, bl, tn)
            pre[(t, bl, tn)] = (df, event, bh, blo)
    print("precompute done", flush=True)

    # ---- Stage A: structure ----
    gridA = stage_a_grid()
    print(f"stage A combos: {len(gridA)}", flush=True)
    resA = run_grid(gridA, pre, dfs, "A")
    resA.to_csv(OUT / "refineA.csv", index=False)

    # top-2 structures per entry by expectancy_R (min 150 trades)
    finalists = []
    for entry in ["undercut", "breakout", "bottom"]:
        sub = resA[(resA.entry == entry) & (resA.trades >= 150)].sort_values(
            "expectancy_R", ascending=False).head(2)
        for _, r in sub.iterrows():
            finalists.append(r.to_dict())
    print("finalists:", flush=True)
    for f in finalists:
        print({k: f[k] for k in ("entry", "base_len", "tightness", "trades",
                                 "expectancy_R", "win_rate")}, flush=True)

    # ---- Stage B: exits for finalists ----
    gridB = []
    for f in finalists:
        base_cfg = {k: f[k] for k in ("entry", "base_len", "tightness", "signal_days",
                                      "undercut_depth", "breakout_buffer", "bottom_zone",
                                      "vol_mult", "above_200dma") if k in f and pd.notna(f[k])}
        # normalize types
        base_cfg["above_200dma"] = bool(f["above_200dma"])
        if "vol_mult" in base_cfg:
            base_cfg["vol_mult"] = float(base_cfg["vol_mult"])
        for st, tr, mh in itertools.product([0.03, 0.04, 0.05, 0.06, 0.08],
                                            [1.5, 2.0, 2.5, 3.0],
                                            [10, 20, 40]):
            cfg = dict(base_cfg)
            cfg.update({"stop_pct": st, "target_R": tr, "max_hold": mh})
            gridB.append(cfg)
    print(f"stage B combos: {len(gridB)}", flush=True)
    resB = run_grid(gridB, pre, dfs, "B")
    resB.to_csv(OUT / "refineB.csv", index=False)
    print("saved refineA.csv refineB.csv", flush=True)


if __name__ == "__main__":
    main()
