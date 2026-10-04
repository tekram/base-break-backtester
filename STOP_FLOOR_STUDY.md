# Undercut-base playbook: minimum stop width study (2026-10-04)

Script: `research/undercut_stop_floor_study.py`. Data: agentic-trading `research/data/exit_study_v2/` (10y, 420 tickers, local only; script reads it from the agentic-trading repo root).
Verdict: **no live change.** Wider stops raise win rate and fixed-capital return but not R, and no difference is statistically separable.

## Trigger: KOD, 2026-10-02

- KOD gapped $32 to $90 on 9/28 (+177%, 38M shares, biotech catalyst), consolidated 3 days.
- `vcp_patterns` (one of the 3 strategies `undercut-base-trader` rotates through; `undercut_base` itself did NOT fire) printed a VCP on the 10/01 close: entry $98.47, stop $90.58 (8.0%, ~1.0 ATR).
- Live and paper positions stopped out 10/02 (-1.0R / -1.0R). Day low $88.63, close $94.45.
- The VCP detector used pre-gap $32 history; the "contraction" was a post-news gap, not a base.

## Gap/catalyst filter: not supported

Of 4,857 eligible historical entries, only 11 had a 1-day close jump >= 1.3x in the prior 20 bars; they averaged +0.89R (n too small, positive). Zero entries reach KOD's +1.5x. Can't validate a gate. Not shipped.

## Stop floor re-simulation

Same 4,857 entries, stop = min(card stop, fill - k x ATR14), live exit (T50 armed on reclaim, 20-day max wait, gap-through-stop at the open), 0.2% commission. "R" = fixed-risk sizing; "%" = fixed-capital sizing.

| Floor | avg risk | mean R [90% CI by month] | win % | stopped % | mean % [90% CI] | median % |
|---|---|---|---|---|---|---|
| card | 5.5% | +0.338 [+0.07, +0.64] | 32.5 | 55.8 | +1.42 [+0.45, +2.38] | -2.54 |
| 1.0 ATR | 5.7% | +0.342 | 33.9 | 54.0 | +1.46 | -2.71 |
| 1.5 ATR | 6.8% | +0.340 [+0.10, +0.63] | 37.9 | 47.2 | +1.63 [+0.49, +2.70] | -2.62 |
| 2.0 ATR | 8.4% | +0.333 | 41.6 | 38.8 | +1.76 | -1.77 |
| 2.5 ATR | 10.4% | +0.321 | 44.6 | 30.4 | +1.93 | -0.92 |
| 3.0 ATR | 12.5% | +0.306 [+0.10, +0.57] | 46.4 | 23.7 | +2.10 [+0.70, +3.48] | -0.57 |

Subset where the card stop is under 1.5 ATR (n=3,193, the entries a floor would change): R flat (+0.13 to +0.11), win rate 28.6% to 46.9%, mean % +0.82 to +1.71.

## Reading it

- Risk-adjusted (R) is flat to slightly worse as the stop widens: wider stop = fewer shakeouts but each loss and each position risk is bigger. Nothing here beats the card stop on R.
- Fixed-capital return and win rate improve steadily, but CIs overlap almost completely across all floors.
- Anecdote only: a 1.5 ATR floor on KOD (~$84.8) would have survived 10/02.
- Caveats: the playbook `min_rr: 3.0` guard (target vs stop) would reject more entries with wider stops; not modelled. In-sample, no walk-forward. Mean R is tail-driven (median R is -1 for most variants).

## Decision

Keep the card stop. Revisit if live shadow/live results show repeated sub-1-ATR shakeouts. The script is re-runnable if the entry set changes.

## Relation to HILLCLIMB_RESULTS.md

The hillclimb undercut tune widened the stop 4% to 6% (+0.289 to +0.327 R/trade, in-sample). That is consistent in direction with the fixed-capital improvement above, but the re-simulation on the production playbook's entries shows R unchanged, so treat the hillclimb stop change as unconfirmed until validated out-of-sample.
