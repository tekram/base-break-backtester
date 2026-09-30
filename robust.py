"""Year-by-year robustness check for finalist configs."""
import numpy as np
import pandas as pd
from pathlib import Path

from backtest import load_ticker, rolling_bases, run_combo

BASE = Path(__file__).parent

FINALISTS = [
    ("BOTTOM 3d/12% zone=3% | stop=3% R=3 hold=40",
     {"entry": "bottom", "base_len": 3, "tightness": 0.12, "bottom_zone": 0.03,
      "above_200dma": False, "stop_pct": 0.03, "target_R": 3.0, "max_hold": 40,
      "signal_days": 10}),
    ("UNDERCUT 20d/8% depth=1.5% dma | stop=4% R=2.5 hold=40",
     {"entry": "undercut", "base_len": 20, "tightness": 0.08, "undercut_depth": 0.015,
      "above_200dma": True, "stop_pct": 0.04, "target_R": 2.5, "max_hold": 40,
      "signal_days": 10}),
    ("BREAKOUT 40d/12% buf=0.5% vol1.5x dma | stop=6% R=3 hold=20",
     {"entry": "breakout", "base_len": 40, "tightness": 0.12, "breakout_buffer": 0.005,
      "vol_mult": 1.5, "above_200dma": True, "stop_pct": 0.06, "target_R": 3.0,
      "max_hold": 20, "signal_days": 10}),
    ("UNDERCUT 10d/8% depth=1.5% dma | stop=5% R=3 hold=40",
     {"entry": "undercut", "base_len": 10, "tightness": 0.08, "undercut_depth": 0.015,
      "above_200dma": True, "stop_pct": 0.05, "target_R": 3.0, "max_hold": 40,
      "signal_days": 10}),
]


def main():
    tickers = sorted(p.stem for p in (BASE / "data" / "bars").glob("*.csv"))
    dfs = {}
    for t in tickers:
        df = load_ticker(t)
        if df is not None:
            dfs[t] = df

    for label, cfg in FINALISTS:
        pre = {}
        for t, df in dfs.items():
            event, bh, bl = rolling_bases(df, cfg["base_len"], cfg["tightness"])
            pre[t] = (df, event, bh, bl)
        trades = run_combo(list(dfs), cfg, pre)
        rows = []
        for tr in trades:
            df = dfs[tr["ticker"]]
            rows.append({"year": df["Date"].iloc[tr["exit_idx"]].year,
                         "r": tr["r_mult"], "win": tr["ret"] > 0})
        d = pd.DataFrame(rows)
        print(f"\n=== {label}  (n={len(d)}) ===")
        g = d.groupby("year").agg(trades=("r", "size"), win_rate=("win", "mean"),
                                  exp_R=("r", "mean"))
        print(g.round(3).to_string())
        yearly = g["exp_R"].values
        print(f"years positive: {(yearly > 0).sum()}/{len(yearly)}, "
              f"mean yearly exp_R: {yearly.mean():.3f}")


if __name__ == "__main__":
    main()
