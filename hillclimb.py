"""Karpathy-style auto-research loop for base-break parameters.

Greedy coordinate descent, exactly the keep/revert loop:
  for each parameter (entry AND exit side):
      try every candidate value with all other params fixed
      keep the value iff the objective improves, else revert
  repeat full rounds until a round produces no improvement.

The evaluator (backtest.py) is FROZEN - never modified, so the metric
can't be gamed. Only the parameter dict mutates. Every experiment is
logged to results/hillclimb_log.csv.

Objective: maximize expectancy_R (R per trade), subject to a minimum
trade-count floor so the loop can't "improve" by collapsing to a
handful of lucky trades.
"""
import csv
import itertools
import json
import time
from copy import deepcopy
from pathlib import Path

from backtest import load_ticker, rolling_bases, run_combo, summarize

BASE = Path(__file__).parent
OUT = BASE / "results"
OUT.mkdir(exist_ok=True)

MIN_TRADES = {"breakout": 150, "undercut": 150, "bottom": 1000}
MAX_ROUNDS = 8

PARAM_SPACES = {
    "breakout": {
        "base_len": [30, 40, 50],
        "tightness": [0.08, 0.10, 0.12, 0.15],
        "breakout_buffer": [0.0, 0.003, 0.005, 0.008, 0.01],
        "vol_mult": [0, 1.25, 1.5, 2.0],
        "above_200dma": [False, True],
        "stop_pct": [0.04, 0.05, 0.06, 0.08],
        "target_R": [2.0, 2.5, 3.0, 4.0],
        "max_hold": [10, 20, 30, 40],
        "signal_days": [5, 10, 15],
    },
    "undercut": {
        "base_len": [10, 15, 20, 30],
        "tightness": [0.05, 0.08, 0.10, 0.12],
        "undercut_depth": [0.005, 0.01, 0.015, 0.02, 0.03],
        "above_200dma": [False, True],
        "stop_pct": [0.03, 0.04, 0.05, 0.06],
        "target_R": [2.0, 2.5, 3.0, 4.0],
        "max_hold": [20, 30, 40, 60],
        "signal_days": [5, 10, 15],
    },
    "bottom": {
        "base_len": [2, 3, 5, 7, 10],
        "tightness": [0.08, 0.10, 0.12, 0.15],
        "bottom_zone": [0.01, 0.02, 0.03, 0.05],
        "above_200dma": [False, True],
        "stop_pct": [0.02, 0.03, 0.04, 0.05],
        "target_R": [2.0, 2.5, 3.0, 4.0],
        "max_hold": [20, 30, 40, 60],
        "signal_days": [5, 10, 15],
    },
}

# params each strategy's space actually uses (entry-specific key)
ENTRY_KEY = {"breakout": "breakout_buffer", "undercut": "undercut_depth",
             "bottom": "bottom_zone"}


def evaluate(cfg, tickers, dfs, pre):
    key = (cfg["base_len"], cfg["tightness"])
    pc = {t: (dfs[t],) + pre[key][t] for t in tickers if t in pre[key]}
    trades = run_combo(tickers, cfg, pc)
    return summarize(trades)


def score(summary, floor):
    if not summary or summary["trades"] < floor:
        return float("-inf")
    return summary["expectancy_R"]


def main():
    tickers = sorted(p.stem for p in (BASE / "data" / "bars").glob("*.csv"))
    dfs = {}
    for t in tickers:
        df = load_ticker(t)
        if df is not None:
            dfs[t] = df
    tickers = list(dfs)
    print(f"usable tickers: {len(tickers)}", flush=True)

    with open(BASE / "strategy_params.json") as f:
        selected = json.load(f)

    # precompute bases for the union of (base_len, tightness) across all spaces
    combos = set()
    for space in PARAM_SPACES.values():
        combos |= set(itertools.product(space["base_len"], space["tightness"]))
    print(f"precomputing {len(combos)} (base_len, tightness) combos...", flush=True)
    pre = {}
    t0 = time.time()
    for (bl, tn) in combos:
        d = {}
        for t, df in dfs.items():
            event, bh, blo = rolling_bases(df, bl, tn)
            d[t] = (event, bh, blo)
        pre[(bl, tn)] = d
    print(f"precompute done in {time.time()-t0:.0f}s", flush=True)

    log_path = OUT / "hillclimb_log.csv"
    logf = open(log_path, "w", newline="")
    log = csv.writer(logf)
    log.writerow(["strategy", "round", "param", "old", "new",
                  "expectancy_R", "trades", "win_rate", "profit_factor", "kept"])

    best_cfgs = {}
    for strat, space in PARAM_SPACES.items():
        floor = MIN_TRADES[strat]
        # starting point: the previously selected params
        cfg = {k: v for k, v in selected[strat].items()
               if k not in ("backtest", "label", "_note")}
        cfg["entry"] = strat
        if strat == "breakout":
            cfg.setdefault("vol_mult", 1.5)
        best = deepcopy(cfg)
        best_sum = evaluate(best, tickers, dfs, pre)
        best_score = score(best_sum, floor)
        n_exp = 0
        log.writerow([strat, 0, "(init)", "", "",
                      f"{best_score:.4f}", best_sum["trades"],
                      f"{best_sum['win_rate']:.3f}",
                      f"{best_sum['profit_factor']:.2f}", "init"])
        print(f"\n[{strat}] start expR={best_score:.3f} "
              f"trades={best_sum['trades']}", flush=True)

        for rnd in range(1, MAX_ROUNDS + 1):
            improved = False
            for param, cands in space.items():
                old = best[param]
                tried = [c for c in cands if c != old]
                results = []
                for c in tried:
                    trial = deepcopy(best)
                    trial[param] = c
                    s = evaluate(trial, tickers, dfs, pre)
                    sc = score(s, floor)
                    results.append((c, sc, s))
                    n_exp += 1
                # best candidate for this param
                results.sort(key=lambda r: r[1], reverse=True)
                c, sc, s = results[0]
                kept = sc > best_score
                log.writerow([strat, rnd, param, old, c,
                              f"{sc:.4f}" if sc > float("-inf") else "-inf",
                              s["trades"] if s else 0,
                              f"{s['win_rate']:.3f}" if s else "",
                              f"{s['profit_factor']:.2f}" if s else "",
                              "keep" if kept else "revert"])
                if kept:
                    print(f"  round {rnd}: {param} {old} -> {c}  "
                          f"expR {best_score:.3f} -> {sc:.3f} "
                          f"(n={s['trades']})  KEEP", flush=True)
                    best[param] = c
                    best_score = sc
                    best_sum = s
                    improved = True
            if not improved:
                print(f"[{strat}] converged after round {rnd} "
                      f"({n_exp} experiments)", flush=True)
                break
        else:
            print(f"[{strat}] hit max rounds ({n_exp} experiments)", flush=True)

        print(f"[{strat}] FINAL expR={best_score:.3f} trades={best_sum['trades']} "
              f"win={best_sum['win_rate']:.0%} pf={best_sum['profit_factor']:.2f}",
              flush=True)
        best_cfgs[strat] = {"params": best, "summary": best_sum}

    logf.close()
    print(f"\nlog -> {log_path}", flush=True)

    # save tuned params alongside the original file's schema
    tuned = {}
    for strat in PARAM_SPACES:
        b = best_cfgs[strat]
        tuned[strat] = dict(b["params"])
        tuned[strat]["tuned_backtest"] = {
            "expectancy_R": round(b["summary"]["expectancy_R"], 3),
            "trades": b["summary"]["trades"],
            "win_rate": round(b["summary"]["win_rate"], 3),
            "profit_factor": round(b["summary"]["profit_factor"], 2),
        }
    with open(OUT / "hillclimb_best.json", "w") as f:
        json.dump(tuned, f, indent=2)
    print("best params -> results/hillclimb_best.json", flush=True)


if __name__ == "__main__":
    main()
