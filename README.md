# Base-Break Pattern Backtester

Backtests a "base-break" trading pattern on S&P 500 daily bars:

1. **Base formation** — price goes sideways: the N-day high-low range is ≤ X% of price.
2. **Entry** — one of three triggers after the base completes:
   - `undercut`: price dips below the base low, then closes back above it (undercut & rally)
   - `breakout`: price closes above the base high (+ optional buffer)
   - `bottom`: price trades down into the bottom zone of the base (accumulation)
3. **Exits** — fixed % stop loss, profit target as a multiple of the stop (R), max-holding time stop.

## Files

- `backtest.py` — core engine (base detection, entries, exits, metrics)
- `sweep.py` / `refine.py` / `robust.py` — parameter sweep, refinement, year-by-year checks
- `download.py` — daily OHLCV downloader (Nasdaq public API)
- `strategy_params.json` — exact winning parameters per variant, machine-readable
- `live_scan.py` — daily live signal scanner (run after the close; mirrors backtest.py)
- `STRATEGY_SPEC.md` — full bot implementation spec
- `results/` — sweep output CSVs

## Quick start

```bash
pip install -r requirements.txt
python download.py      # fetch S&P 500 daily bars into data/bars/
python sweep.py         # run the parameter sweep -> results/coarse_sweep.csv
```

## Method notes

- Entries filled at the **next open** after the trigger close; exits use intraday
  stop/target levels (stop takes precedence if both print same day), time exits at the close.
- Costs: 5 bps slippage per side.
- Guards: $5 minimum price, $1M minimum average base dollar-volume, one position
  per ticker at a time, no overlapping bases.
- Data: Nasdaq public chart API, split-adjusted, 2021-10 → 2026-09.
- Survivorship note: the universe is *current* S&P 500 constituents, so delisted
  names are absent — expect a mild optimistic bias.
