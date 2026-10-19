"""Closing line value: after we recorded a forecast, did Kalshi's price move toward our number by the game start?"""
import csv, json, random, statistics as st, sys
from collections import defaultdict

rows = list(csv.DictReader(open(sys.argv[1])))
close = json.load(open(sys.argv[2]))
f = lambda x: float(x) if x not in ("", None) else None
by_market = defaultdict(list)
for r in rows:
    if r["resolved_yes"] in ("t", "f") and r["before_start"] == "t":
        by_market[r["market_ticker"]].append(r)
data = []
for t, g in by_market.items():
    r = max(g, key=lambda r: (r["created_at"], int(r["id"])))
    c = (close.get(t) or {}).get("close")
    bid, ask = f(r["yes_bid"]), f(r["yes_ask"])
    if not c or bid is None or ask is None or not (0 < bid <= ask < 1) or not (0 < c["bid"] <= c["ask"] < 1) or r["baseline_probability"] == "":
        continue
    m0, m1 = (bid + ask) / 2, (c["bid"] + c["ask"]) / 2
    data.append(dict(game=r["event_ticker"], kind=r["market_kind"], m0=m0, m1=m1, ours=f(r["probability"]), base=f(r["baseline_probability"]),
                     y=1.0 if r["resolved_yes"] == "t" else 0.0, flagged=r["meaningful"] == "t", side=r["side"],
                     ask0=ask, noask0=f(r["no_ask"]), bid1=c["bid"], ask1=c["ask"]))
print(f"markets with an opening and a closing two-sided price: {len(data)}, games {len({d['game'] for d in data})}")
print(f"average absolute price move from our record to the close: {st.fmean(abs(d['m1']-d['m0']) for d in data)*100:.2f}c")
brier = lambda key: st.fmean((d[key] - d["y"]) ** 2 for d in data)
print(f"Brier: price when we recorded {brier('m0'):.4f}; closing price {brier('m1'):.4f}; ours {brier('ours'):.4f}; plain AI {brier('base'):.4f}")


def boot_mean(vals_by_game, B=2000):
    keys = list(vals_by_game); rng = random.Random(7); means = []
    for _ in range(B):
        pick = [v for _ in keys for v in vals_by_game[keys[rng.randrange(len(keys))]]]
        means.append(st.fmean(pick))
    means.sort(); return means[int(.025 * B)], means[int(.975 * B)]


for src in ("ours", "base"):
    # signed move in the direction of our disagreement: positive = the market came toward us
    vals = defaultdict(list)
    for d in data:
        gap = d[src] - d["m0"]
        if abs(gap) >= 0.02:
            vals[d["game"]].append((d["m1"] - d["m0"]) * (1 if gap > 0 else -1))
    allv = [v for vs in vals.values() for v in vs]
    lo, hi = boot_mean(vals)
    toward = sum(1 for v in allv if v > 0); away = sum(1 for v in allv if v < 0)
    print(f"{src:5s}: where it differed from the price by 2c+ (n={len(allv)}): average move toward it {st.fmean(allv)*100:+.2f}c, 95% CI by game [{lo*100:+.2f}, {hi*100:+.2f}]c; moved toward {toward}, away {away}, flat {len(allv)-toward-away}")
    gaps = [d[src] - d["m0"] for d in data]; moves = [d["m1"] - d["m0"] for d in data]
    print(f"       correlation(our gap, later move) {st.correlation(gaps, moves):+.3f}")

# The flagged bets: did the price move for or against the side bought?
fl = [d for d in data if d["flagged"]]
if fl:
    mv = [(d["m1"] - d["m0"]) * (1 if d["side"] == "yes" else -1) for d in fl]
    print(f"flagged bets with prices at both times: {len(fl)}; average move in favour of the side bought {st.fmean(mv)*100:+.2f}c")
