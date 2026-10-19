"""Read-only: for each scored market, the Kalshi bid and ask in the last hourly candle before the game start (public GET only).
Slow on purpose (one request at a time, with a pause) so it does not disturb the price-test run going on at the same time."""
import csv, json, sys, time
from datetime import datetime
from pathlib import Path

from app.kalshi import KalshiClient, KalshiError
from app.research.pricetest import _num

rows = list(csv.DictReader(open(sys.argv[1])))
out_path = Path(sys.argv[2])
done = json.loads(out_path.read_text()) if out_path.exists() else {}
client = KalshiClient("https://external-api.kalshi.com/trade-api/v2", max_attempts=5, backoff_seconds=2)
ts = lambda s: int(datetime.fromisoformat(s).timestamp())

todo = [r for r in rows if r["resolved_yes"] in ("t", "f") and r["before_start"] == "t" and r["game_start"] and r["market_ticker"] not in done]
print(f"{len(todo)} markets to read", flush=True)
for i, r in enumerate(todo, 1):
    start = ts(r["game_start"])
    series = r["event_ticker"].split("-")[0]
    try:
        candles = client.get_candlesticks(series, r["market_ticker"], start_ts=ts(r["created_at"]) - 3600, end_ts=start, period_interval=60).get("candlesticks", [])
    except KalshiError as exc:
        done[r["market_ticker"]] = {"error": str(exc)}
        continue
    usable = [c for c in candles if c.get("end_period_ts") and c["end_period_ts"] <= start]
    last = None
    for c in sorted(usable, key=lambda c: c["end_period_ts"], reverse=True):
        bid, ask = _num(c.get("yes_bid")), _num(c.get("yes_ask"))
        if bid is not None and ask is not None:
            last = {"end": c["end_period_ts"], "bid": float(bid), "ask": float(ask)}
            break
    done[r["market_ticker"]] = {"close": last, "candles": len(candles)}
    if i % 25 == 0:
        out_path.write_text(json.dumps(done))
        print(f"{i} read", flush=True)
    time.sleep(1.0)
out_path.write_text(json.dumps(done))
print("finished", flush=True)
