"""Download daily OHLCV bars from Nasdaq's public chart API for the S&P 500 universe."""
import time
import requests
import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data" / "bars"
DATA.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
}
URL = "https://api.nasdaq.com/api/quote/{sym}/historical"


def clean_num(s):
    return float(str(s).replace("$", "").replace(",", "").strip())


def fetch(t):
    sym = t.replace(".", "-")  # BRK.B -> BRK-B
    params = {"assetclass": "stocks", "fromdate": "2021-10-01",
              "todate": "2026-09-30", "limit": "9999"}
    r = requests.get(URL.format(sym=sym), params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    d = r.json()
    rows = d["data"]["tradesTable"]["rows"]
    if not rows or len(rows) < 200:
        return None
    recs = []
    for row in rows:
        recs.append({
            "Date": pd.to_datetime(row["date"]),
            "Open": clean_num(row["open"]),
            "High": clean_num(row["high"]),
            "Low": clean_num(row["low"]),
            "Close": clean_num(row["close"]),
            "Volume": int(str(row["volume"]).replace(",", "").strip() or 0),
        })
    df = pd.DataFrame(recs).sort_values("Date").reset_index(drop=True)
    return df


def main():
    tickers = [t.strip() for t in open(BASE / "data" / "sp500_tickers.txt") if t.strip()]
    ok, fail = 0, []
    for t in tickers:
        out = DATA / f"{t}.csv"
        if out.exists() and out.stat().st_size > 5000:
            ok += 1
            continue
        try:
            df = fetch(t)
            if df is None:
                fail.append(t)
            else:
                df.to_csv(out, index=False)
                ok += 1
        except Exception as e:
            fail.append(t)
        time.sleep(0.4)
    print(f"OK: {ok}, FAILED: {len(fail)}", flush=True)
    if fail:
        print("failed:", fail[:40], flush=True)
        Path(BASE / "data" / "failed.txt").write_text("\n".join(fail))


if __name__ == "__main__":
    main()
