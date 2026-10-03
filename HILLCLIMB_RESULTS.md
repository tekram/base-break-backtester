# Auto-research results — hillclimb (Oct 1, 2026)

Karpathy-style greedy coordinate descent over entry/exit parameters (`hillclimb.py`):
change one parameter, keep it only if expectancy improves, otherwise revert, repeat for
multiple rounds. `backtest.py` frozen as the evaluator; minimum-trade floors prevent
tiny-sample optimization. 182 experiments, full keep/revert log in `results/hillclimb_log.csv`.

Original selected params untouched in `strategy_params.json`; tuned params in
`results/hillclimb_best.json`.

## Breakout: 0.265 → 0.331 R/trade
- Changed: volume filter 1.5× → 2.0×, breakout buffer 0.5% → 0.3%
- 184 trades, 62% win rate, profit factor 2.11
- ⚠️ Year-by-year: positive only 3/5 years (2022 −0.022R, 2023 −0.049R) — traded
  robustness for average expectancy vs the original 5/5

## Undercut: 0.289 → 0.327 R/trade
- Changed: stop 4% → 6%, target 2.5R → 4R, max hold 40 → 60 days
- 255 trades, 45% win rate, profit factor 1.60
- Positive 4/5 years (2022 −0.221R)

## Bottom: 0.327 → 0.769 R/trade
- Changed: base 3d → 2d, width 12% → 15%, stop 3% → 2%, target 3R → 4R, max hold 40 → 20 days
- 2,211 trades, 38% win rate, profit factor 2.18
- Positive 6/6 years (worst year 2026 at +0.316R)

## Caveats
- Tuned on the full sample; not yet validated out-of-sample or walk-forward.
- The breakout tune sacrificed year-by-year consistency — consider a robustness
  objective (e.g. worst-year expectancy) before adopting it.
- Research only: exact filters, formulas, and parameters for the user's own evaluation.
