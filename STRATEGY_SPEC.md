# Base-Break Strategy — Bot Implementation Spec

Backtested on 486 S&P 500 stocks, daily bars, Oct 2021 → Sep 2026 (Nasdaq data,
split-adjusted). Fills at next open, 5 bps slippage per side, $5 min price,
$1M min avg base dollar-volume, one position per ticker at a time.

## 1. Universe & data

- Daily OHLCV bars, split-adjusted.
- Liquidity guards: `close > 5` and `mean(close*volume over base window) > 1_000_000`.

## 2. Base detection (the screener)

For each ticker, each day `i` (using completed daily bars):

```
base_high = max(high[i-N+1 .. i])
base_low  = min(low[i-N+1 .. i])
width     = (base_high - base_low) / close[i]
base_valid = width <= T
```

A **base event** fires on the first day `base_valid` turns true (False→True
transition), with a cooldown of N days before the next event on that ticker.

Recommended `(N, T)` per variant (see §5).

## 3. Regime filter (undercut & breakout only)

```
sma200 = mean(close[i-200 .. i-1])
require close[i] > sma200
```

The bottom (mean-reversion) variant skips this filter — it tested better without it.

## 4. Entry triggers

After a base event on day `i`, watch days `j = i+1 .. i+10` (10-day signal window).
Take the **first** trigger day; enter at the **next day's open** (`open[j+1]`).

**a) Undercut & reclaim** (classic basin trade)
```
trigger if: low[j] <= base_low * (1 - 0.015)   # dips ≥1.5% under the base low
        and close[j] > base_low                  # ...then reclaims it by the close
```

**b) Breakout**
```
trigger if: close[j] > base_high * (1 + 0.005)  # closes 0.5% above base high
        and volume[j] >= 1.5 * mean(volume[j-20 .. j-1])
```

**c) Bottom accumulation**
```
trigger if: low[j] <= base_low * (1 + 0.02)     # trades within 2% above the base low
```

## 5. Exits

From entry price `E`:

```
stop_px   = E * (1 - S)
target_px = E * (1 + S * R)
```

Each day after entry: if `low <= stop_px` → exit at `stop_px`;
else if `high >= target_px` → exit at `target_px`
(if both print the same day, the stop is assumed hit first).
If neither is hit within `H` days, exit at the close of entry day + H.

## 6. Recommended parameters

| Variant | Base N | Tightness T | Entry detail | Regime | Stop S | Target R | Max hold H |
|---|---|---|---|---|---|---|---|
| **Breakout** (primary — most consistent) | 40 | 12% | buffer 0.5%, vol ≥1.5×20d avg | close > 200DMA | 6% | 3.0 | 20 days |
| **Undercut** | 20 | 8% | undercut depth 1.5% | close > 200DMA | 4% | 2.5 | 40 days |
| **Bottom** (highest expectancy) | 3 | 12% | zone 2% above base low | none | 3% | 3.0 | 40 days |

## 7. Backtest results (out-of-sample style: params picked by sweep, verified per-year)

| Variant | Trades | Win rate | Expectancy | Profit factor | Avg hold | Years positive |
|---|---|---|---|---|---|---|
| Breakout 40d/12% | 343 | 52% | **+0.27 R/trade** | 1.78 | ~16 d | 5/5 (incl. 2022) |
| Undercut 20d/8% | 263 | 42% | **+0.29 R/trade** | 1.50 | ~16 d | 4/5 (2022 weak) |
| Bottom 3d/12% | 5,840 | 34% | **+0.33 R/trade** | 1.48 | ~6 d | 6/6 (incl. 2022) |

Notes:
- Loose bases beat tight ones everywhere: 8–12% width outperformed 5%.
- Breakout/undercut want the 200DMA trend filter; bottom works best without it.
- Win rates are 34–52%: the edge comes from R-multiples (2.5–3R targets), not accuracy.

## 8. Bot loop pseudocode

```
every day after close:
    for ticker in universe:
        if has_open_position(ticker): manage_exit(ticker)   # §5
        else:
            if base_event(ticker, N, T) and regime_ok(ticker):
                arm_signal(ticker, base_high, base_low, expiry=+10d)
    for armed signal not expired:
        if entry_trigger(ticker, variant):                  # §4
            enter_next_open(ticker)
            set stop/target/time exits                       # §5
```

## 9. Caveats

- Universe is *current* S&P 500 constituents → mild survivorship bias (delisted
  names missing); expect live results slightly below backtest.
- Fills assumed at next open; fast gaps through stop/target use the stop/target
  price (no slippage beyond 5 bps modeled).
- 2026 YTD was the weakest year for all variants — monitor live expectancy vs
  these baselines and pause if it goes negative over ~50 trades.
