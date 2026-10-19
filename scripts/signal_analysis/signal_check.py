"""Read-only diagnostics on the exported outcome records: does our forecast carry information the Kalshi price does not?"""
import csv, math, random, sys
from collections import defaultdict

import statistics

class _np:
    mean = staticmethod(statistics.fmean)
    median = staticmethod(statistics.median)
    class linalg:
        LinAlgError = ZeroDivisionError
    @staticmethod
    def corrcoef(a, b):
        r = statistics.correlation(a, b)
        return [[1, r], [r, 1]]
np = _np


def solve(A, b):
    n = len(b); M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-12: raise ZeroDivisionError
        for r in range(n):
            if r != c:
                k = M[r][c] / M[c][c]
                M[r] = [x - k * y for x, y in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] for i in range(n)]

rows = list(csv.DictReader(open(sys.argv[1])))
f = lambda x: float(x) if x not in ("", None) else None

# Same selection as score_records: resolved, made before start, latest per market, two-sided quote.
by_market = defaultdict(list)
for r in rows:
    if r["resolved_yes"] in ("t", "f") and r["before_start"] == "t":
        by_market[r["market_ticker"]].append(r)
used = [max(g, key=lambda r: (r["created_at"], int(r["id"]))) for g in by_market.values()]
data = []
for r in used:
    bid, ask = f(r["yes_bid"]), f(r["yes_ask"])
    if bid is None or ask is None or not (0 < bid <= ask < 1) or r["baseline_probability"] == "":
        continue
    data.append(dict(game=r["event_ticker"], kind=r["market_kind"], sport=r["sport"] or "?", y=1.0 if r["resolved_yes"] == "t" else 0.0,
                     mid=(bid + ask) / 2, spread=ask - bid, ours=f(r["probability"]), base=f(r["baseline_probability"]),
                     lo=f(r["prob_min"]), hi=f(r["prob_max"]), claims=int(r["supported_claims"]), flagged=r["meaningful"] == "t",
                     side=r["side"], ask=ask, no_ask=f(r["no_ask"]), mult=f(r["fee_multiplier"]) or 1.0))
games = sorted({d["game"] for d in data})
print(f"outcomes {len(data)}, games {len(games)}")

clip = lambda p: min(max(p, 0.01), 0.99)
logit = lambda p: math.log(clip(p) / (1 - clip(p)))
sig = lambda z: 1 / (1 + math.exp(-z))
brier = lambda ps, ys: sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)


def scores(sub, label):
    ys = [d["y"] for d in sub]
    print(f"  {label:28s} n={len(sub):4d} games={len({d['game'] for d in sub}):3d}  "
          f"mid {brier([d['mid'] for d in sub], ys):.4f}  ours {brier([d['ours'] for d in sub], ys):.4f}  plainAI {brier([d['base'] for d in sub], ys):.4f}")


print("\n1. Brier (lower is better)")
scores(data, "all")
for k in sorted({d["kind"] for d in data}):
    scores([d for d in data if d["kind"] == k], f"kind={k}")
for s in sorted({d["sport"] for d in data}):
    scores([d for d in data if d["sport"] == s], f"sport={s}")


def logreg(X, y, iters=50, ridge=1e-6):
    k = len(X[0]); w = [0.0] * k
    for _ in range(iters):
        p = [1 / (1 + math.exp(-max(min(sum(a * b for a, b in zip(x, w)), 30), -30))) for x in X]
        g = [sum(x[j] * (yy - pp) for x, yy, pp in zip(X, y, p)) - ridge * w[j] for j in range(k)]
        H = [[sum(x[i] * x[j] * pp * (1 - pp) for x, pp in zip(X, p)) + (ridge if i == j else 0) for j in range(k)] for i in range(k)]
        step = solve(H, g)
        w = [a + b for a, b in zip(w, step)]
    return w


def encompass(sub, other, label, B=400):
    """outcome ~ a + b*logit(mid) + c*(logit(other) - logit(mid)); c > 0 means `other` knows something the price does not."""
    X = [[1, logit(d["mid"]), logit(d[other]) - logit(d["mid"])] for d in sub]
    y = [d["y"] for d in sub]
    w = logreg(X, y)
    by_game = defaultdict(list)
    for i, d in enumerate(sub):
        by_game[d["game"]].append(i)
    keys = list(by_game)
    rng = random.Random(1)
    cs = []
    for _ in range(B):
        idx = [i for _ in keys for i in by_game[keys[rng.randrange(len(keys))]]]
        try:
            cs.append(logreg([X[i] for i in idx], [y[i] for i in idx])[2])
        except np.linalg.LinAlgError:
            pass
    cs.sort()
    lo, hi = cs[int(0.025 * len(cs))], cs[int(0.975 * len(cs))]
    print(f"  {label:34s} price weight b={w[1]:+.2f}  extra weight on ({other} - price) c={w[2]:+.2f}  95% CI by game [{lo:+.2f}, {hi:+.2f}]")


print("\n2. Does the forecast add information beyond the Kalshi price? (logistic regression, game-level bootstrap)")
encompass(data, "ours", "all outcomes, ours")
encompass(data, "base", "all outcomes, plain AI")
encompass([d for d in data if d["kind"] == "winner"], "ours", "winner markets, ours")
for s in ("Soccer", "Tennis"):
    encompass([d for d in data if d["sport"] == s], "ours", f"{s}, ours")


print("\n3. Leave-one-game-out blend: p = sigmoid((1-w)*logit(mid) + w*logit(ours)), w fitted on the other games")
grid = [i / 20 for i in range(-10, 21)]
for src in ("ours", "base"):
    preds, ws = [], []
    for g in games:
        train = [d for d in data if d["game"] != g]
        best = min(grid, key=lambda w: brier([sig((1 - w) * logit(d["mid"]) + w * logit(d[src])) for d in train], [d["y"] for d in train]))
        ws.append(best)
        preds += [(sig((1 - best) * logit(d["mid"]) + best * logit(d[src])), d["y"], d["mid"]) for d in data if d["game"] == g]
    print(f"  {src}: chosen w from {min(ws):+.2f} to {max(ws):+.2f};  held-out Brier blend {brier([p for p,_,_ in preds],[y for _,y,_ in preds]):.4f}  vs mid {brier([m for _,_,m in preds],[y for _,y,_ in preds]):.4f}")


print("\n4. When we disagree with the price, who is right? (bins of ours - mid; average of outcome - mid)")
bins = [(-1, -0.15), (-0.15, -0.05), (-0.05, 0.05), (0.05, 0.15), (0.15, 1)]
for lo, hi in bins:
    sub = [d for d in data if lo <= d["ours"] - d["mid"] < hi]
    if sub:
        gap = sum(d["ours"] - d["mid"] for d in sub) / len(sub)
        real = sum(d["y"] - d["mid"] for d in sub) / len(sub)
        print(f"  ours-mid in [{lo:+.2f},{hi:+.2f}): n={len(sub):3d}  our average gap {gap:+.3f}  what happened minus price {real:+.3f}")


print("\n5. Market calibration in this sample (mid buckets)")
for b in range(10):
    sub = [d for d in data if b / 10 <= d["mid"] < (b + 1) / 10]
    if sub:
        print(f"  {b*10:2d}-{b*10+10:3d}c n={len(sub):3d} mean price {sum(d['mid'] for d in sub)/len(sub):.3f} happened {sum(d['y'] for d in sub)/len(sub):.3f}"
              f"  ours mean {sum(d['ours'] for d in sub)/len(sub):.3f}")

print("\n6. How far ours sits from the price, and from the plain AI")
print(f"  mean |ours - mid| {np.mean([abs(d['ours']-d['mid']) for d in data]):.3f}; mean |ours - plainAI| {np.mean([abs(d['ours']-d['base']) for d in data]):.3f};"
      f" mean |plainAI - mid| {np.mean([abs(d['base']-d['mid']) for d in data]):.3f}; mean spread of forecasters {np.mean([d['hi']-d['lo'] for d in data]):.3f}")
print(f"  correlation(ours - mid, plainAI - mid) {np.corrcoef([d['ours']-d['mid'] for d in data],[d['base']-d['mid'] for d in data])[0][1]:.2f}")
print(f"  mean bid-ask spread {np.mean([d['spread'] for d in data]):.3f}; median {np.median([d['spread'] for d in data]):.3f}")

print("\n7. Cost of crossing the spread plus fee, per contract, at the ask (average over outcomes)")
cost = [d["ask"] - d["mid"] + 0.07 * d["mult"] * d["ask"] * (1 - d["ask"]) for d in data]
print(f"  half-spread + taker fee: mean {np.mean(cost)*100:.1f}c, median {np.median(cost)*100:.1f}c")

print("\n8. Lean by kind of market: average of (ours - mid), (plainAI - mid), (outcome - mid)")
for k in sorted({d["kind"] for d in data}) + ["ALL"]:
    sub = [d for d in data if k in ("ALL", d["kind"])]
    m = lambda key: sum(d[key] - d["mid"] for d in sub) / len(sub)
    print(f"  {k:7s} n={len(sub):3d} ours {m('ours'):+.3f}  plainAI {m('base'):+.3f}  outcome {m('y'):+.3f}")

print("\n9. Spread: is ours less extreme than the market? average |p - 0.5|")
for k in sorted({d["kind"] for d in data}) + ["ALL"]:
    sub = [d for d in data if k in ("ALL", d["kind"])]
    a = lambda key: sum(abs(d[key] - 0.5) for d in sub) / len(sub)
    print(f"  {k:7s} market {a('mid'):.3f}  ours {a('ours'):.3f}  plainAI {a('base'):.3f}")

print("\n10. Same as 2, but only the forecast's direction from the plain AI (does research move us the right way?)")
X = [[1, logit(d["mid"]), logit(d["ours"]) - logit(d["base"])] for d in data]
w = logreg(X, [d["y"] for d in data])
print(f"  extra weight on (ours - plainAI) given the price: {w[2]:+.2f}")
sub = [d for d in data if abs(d["ours"] - d["base"]) >= 0.05]
print(f"  outcomes where research moved us 5c+ from plain AI: n={len(sub)}; research moved toward the outcome in "
      f"{sum(1 for d in sub if (d['ours'] - d['base']) * (d['y'] - d['base']) > 0)} of them")
print(f"  Brier on those: plainAI {brier([d['base'] for d in sub],[d['y'] for d in sub]):.4f} ours {brier([d['ours'] for d in sub],[d['y'] for d in sub]):.4f} mid {brier([d['mid'] for d in sub],[d['y'] for d in sub]):.4f}")
