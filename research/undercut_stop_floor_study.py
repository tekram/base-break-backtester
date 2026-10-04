"""Undercut-base playbook: does a minimum stop width (k x ATR14) improve results?

Triggered by the KOD loss (2026-10-02): card stop was ~1 ATR (8%) and got hit the
same day. Bucketing historical entries by stop/ATR showed <1 ATR stops are the
weakest bucket, but that is observational. This re-simulates the SAME entries
with the stop widened to at least k x ATR14 below the fill, under the live exit
rule (T50 armed on first close >= SMA50, 20-day max wait; gap-through stop at open).

Data: research/data/exit_study_v2 (local only). Entries = undercut-base-trader
rows with no guard/filter skip, mature, not gapped_skip.

Two lenses (a wider stop changes position size at fixed risk, so both matter):
  R      : P&L / that variant's own risk (fixed-risk sizing)
  pct    : % return on entry (fixed-capital sizing), net of 0.2% commission
Run: python scripts/research/undercut_stop_floor_study.py
"""
import os
import random
from collections import defaultdict

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = os.path.join(REPO, "research", "data", "exit_study_v2")
H = 504
MAX_WAIT = 20
COMMISSION = 0.002
SLUG = "undercut-base-trader"
FLOORS = [None, 1.0, 1.5, 2.0, 2.5, 3.0]  # None = card stop as-is


def sim(fill_idx, fill, stop, a):
    """Live exit: stop (gap-through at open) / arm-on-reclaim T50 / 20-day max wait.
    Returns (exit_price, hold_bars, reason)."""
    o, lo, c = a["o"], a["l"], a["c"]
    end = min(fill_idx + H, a["n"] - 1)
    deadline = fill_idx + MAX_WAIT - 1
    armed = False
    for i in range(fill_idx, end + 1):
        if lo[i] <= stop:
            return (stop if i == fill_idx else min(o[i], stop)), i - fill_idx, "stop"
        if not armed and i >= deadline:
            return c[i], i - fill_idx, "max_wait"
        if i == end:
            break
        if armed and c[i] < a["sma50"][i]:
            return o[i + 1], i + 1 - fill_idx, "trail"
        if not armed and c[i] >= a["sma50"][i]:
            armed = True
    return c[end], end - fill_idx, "horizon"


def load_arrays(t, cache):
    if t not in cache:
        df = pd.read_csv(os.path.join(D, "ohlcv", f"{t}.csv"), parse_dates=["date"]).set_index("date")
        df = df[~df.index.duplicated(keep="last")].sort_index()
        c = df["close"].to_numpy(float)
        h, l = df["high"].to_numpy(float), df["low"].to_numpy(float)
        prev = np.r_[c[0], c[:-1]]
        tr = np.maximum(h - l, np.maximum(abs(h - prev), abs(l - prev)))
        cache[t] = dict(
            idx=df.index, o=df["open"].to_numpy(float), l=l, c=c, n=len(df),
            sma50=pd.Series(c).rolling(50, min_periods=1).mean().to_numpy(),
            atr=pd.Series(tr).rolling(14).mean().to_numpy(),
        )
    return cache[t]


def month_ci(rows, n_boot=2000, seed=7):
    by = defaultdict(list)
    for v, d in rows:
        by[d[:7]].append(v)
    ms = sorted(by)
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        vals = [x for m in (rng.choice(ms) for _ in ms) for x in by[m]]
        means.append(sum(vals) / len(vals))
    means.sort()
    return means[int(.05 * n_boot)], means[int(.95 * n_boot) - 1]


def main():
    pe = pd.read_csv(os.path.join(D, "playbook_exits.csv"),
                     usecols=["entry_id", "playbook", "guard_skip_reason", "filter_skip_reason"])
    pe = pe[(pe.playbook == SLUG) & pe.guard_skip_reason.isna() & pe.filter_skip_reason.isna()]
    en = pd.read_csv(os.path.join(D, "entries.csv"),
                     usecols=["entry_id", "strategy", "ticker", "signal_date", "fill_date", "fill",
                              "stop", "mature", "gapped_skip"])
    df = en.merge(pe, on="entry_id")
    df = df[df.mature & ~df.gapped_skip & df.fill.notna()]
    cache, out = {}, {k: [] for k in FLOORS}
    for r in df.itertuples():
        a = load_arrays(r.ticker, cache)
        fi = a["idx"].searchsorted(pd.Timestamp(r.fill_date))
        if fi >= a["n"] or fi < 15 or np.isnan(a["atr"][fi - 1]):
            continue
        atr = a["atr"][fi - 1]  # ATR known at signal close
        fill = float(r.fill)
        for k in FLOORS:
            stop = float(r.stop) if k is None else min(float(r.stop), fill - k * atr)
            if stop <= 0 or stop >= fill:
                continue
            px, hold, why = sim(fi, fill, stop, a)
            pct = (px / fill - 1) - COMMISSION
            out[k].append(dict(R=(px - fill) / (fill - stop) - COMMISSION * fill / (fill - stop),
                               pct=pct, hold=hold, why=why, d=r.signal_date,
                               risk_pct=(fill - stop) / fill, eid=r.entry_id,
                               card_atr=(fill - float(r.stop)) / atr))
    print(f"entries: {len(out[None])}\n")
    hdr = f"{'stop floor':>10} {'n':>5} {'risk%':>6} | {'meanR':>7} {'CI90mo':>17} {'win%':>5} {'stop%':>6} | {'mean%':>7} {'CI90mo':>17} {'med%':>6}"
    print(hdr)
    for k in FLOORS:
        x = out[k]
        R = [e["R"] for e in x]
        P = [e["pct"] * 100 for e in x]
        rci = month_ci([(e["R"], e["d"]) for e in x])
        pci = month_ci([(e["pct"] * 100, e["d"]) for e in x])
        name = "card" if k is None else f"{k:.1f} ATR"
        print(f"{name:>10} {len(x):5d} {np.mean([e['risk_pct'] for e in x]) * 100:6.1f} | "
              f"{np.mean(R):+7.3f} [{rci[0]:+.3f},{rci[1]:+.3f}] {np.mean([v > 0 for v in R]) * 100:5.1f} "
              f"{np.mean([e['why'] == 'stop' for e in x]) * 100:6.1f} | "
              f"{np.mean(P):+7.2f} [{pci[0]:+.2f},{pci[1]:+.2f}] {np.median(P):+6.2f}")

    # Subset that matters for KOD: entries whose card stop is under 1.5 ATR
    # (the only ones a 1.5 ATR floor changes), same entries across every variant.
    keep = {e["eid"] for e in out[None] if e["card_atr"] < 1.5}
    keep &= set.intersection(*[{e["eid"] for e in out[k]} for k in FLOORS])
    print(f"\nSubset: card stop < 1.5 ATR, n={len(keep)}")
    for k in FLOORS:
        x = [e for e in out[k] if e["eid"] in keep]
        P = [e["pct"] * 100 for e in x]
        R = [e["R"] for e in x]
        pci = month_ci([(e["pct"] * 100, e["d"]) for e in x])
        name = "card" if k is None else f"{k:.1f} ATR"
        print(f"{name:>10} meanR={np.mean(R):+.3f} win%={np.mean([v > 0 for v in R]) * 100:.1f} "
              f"stop%={np.mean([e['why'] == 'stop' for e in x]) * 100:.1f} "
              f"mean%={np.mean(P):+.2f} [{pci[0]:+.2f},{pci[1]:+.2f}]")


if __name__ == "__main__":
    main()
