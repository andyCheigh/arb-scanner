"""Show the top-10 NEAREST-to-arb opportunities, even those that don't cross threshold.

When you keep getting "0 arbs ≥ 1.0%" this answers the real question:
are books disagreeing at all (just below threshold) or perfectly aligned?

Usage: .venv/bin/python diagnose.py
"""

from __future__ import annotations

import os
import time as _time
os.environ["TZ"] = "America/Los_Angeles"
try:
    _time.tzset()
except AttributeError:
    pass

import logging
from collections import defaultdict

import config
from arb_finder import _best_per_team_point, american_from_decimal
from odds_api import fetch_odds


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def closest_h2h(event):
    """Best price per side from any book; return inv-sum (1.0 = exact arb edge)."""
    by_side = defaultdict(list)
    for bm in event.markets:
        if bm.market_key != "h2h":
            continue
        for o in bm.outcomes:
            by_side[o.name].append((bm.book_title, o.price))
    if len(by_side) < 2:
        return None
    best = {side: max(opts, key=lambda x: x[1]) for side, opts in by_side.items()}
    if len({b[0] for b in best.values()}) < len(best):
        return None  # legs from same book — useless
    inv_sum = sum(1.0 / b[1] for b in best.values())
    return inv_sum, best


def closest_line_market(event, market_key):
    best = _best_per_team_point(event, market_key)
    candidates = []
    if market_key == "spreads":
        magnitudes = {abs(p) for (_, p) in best.keys() if p != 0}
        for L in magnitudes:
            for sgn in (-1, 1):
                hk = (event.home_team, sgn * L)
                ak = (event.away_team, -sgn * L)
                if hk in best and ak in best:
                    h = best[hk]
                    a = best[ak]
                    if h[0] == a[0]:
                        continue
                    inv = 1 / h[2] + 1 / a[2]
                    candidates.append(
                        (
                            inv,
                            f"{event.home_team} {sgn * L:+g} @ {h[1]} {h[2]:.2f}d ({american_from_decimal(h[2])})  +  {event.away_team} {-sgn * L:+g} @ {a[1]} {a[2]:.2f}d ({american_from_decimal(a[2])})",
                        )
                    )
    else:  # totals
        for L in {p for (_, p) in best.keys()}:
            ok = ("Over", L)
            uk = ("Under", L)
            if ok in best and uk in best:
                o = best[ok]
                u = best[uk]
                if o[0] == u[0]:
                    continue
                inv = 1 / o[2] + 1 / u[2]
                candidates.append(
                    (
                        inv,
                        f"Over {L:g} @ {o[1]} {o[2]:.2f}d ({american_from_decimal(o[2])})  +  Under {L:g} @ {u[1]} {u[2]:.2f}d ({american_from_decimal(u[2])})",
                    )
                )
    if not candidates:
        return None
    return min(candidates, key=lambda x: x[0])


def main():
    cfg = config.load()
    print(f"Pulling {len(cfg.sports)} sports across {len(cfg.books)} books with {len(cfg.odds_api_keys)} key(s)...\n")
    events, quota = fetch_odds(cfg.odds_api_keys, cfg.sports, cfg.books)
    print(f"\nFetched {len(events)} events. Combined quota left: {quota.get('total_remaining')}\n")

    rows = []
    for ev in events:
        h2h = closest_h2h(ev)
        if h2h:
            inv, best = h2h
            legs = "  +  ".join(
                f"{side} @ {b[0]} {b[1]:.2f}d ({american_from_decimal(b[1])})"
                for side, b in best.items()
            )
            rows.append((inv, ev, "h2h", legs))
        for mk in ("spreads", "totals"):
            r = closest_line_market(ev, mk)
            if r:
                inv, legs = r
                rows.append((inv, ev, mk, legs))

    rows.sort(key=lambda r: r[0])

    print("Closest-to-arb opportunities (inv-sum 1.0000 = breakeven, <1.0 = arb)")
    print("=" * 96)
    for i, (inv, ev, mk, legs) in enumerate(rows[:15], 1):
        margin_pct = (1 / inv - 1) * 100
        flag = "  ← ARB" if inv < 1.0 else f"  (need {(1-inv)*100*-1:.2f}% movement)" if inv > 1.0 else ""
        print(f"\n{i:2d}. inv-sum={inv:.4f}  margin={margin_pct:+.2f}%{flag}")
        print(f"    {ev.sport_title}: {ev.away_team} @ {ev.home_team}  ({mk})")
        print(f"    {legs}")

    arbs_count = sum(1 for r in rows if r[0] < 1.0)
    near_count = sum(1 for r in rows if 1.0 <= r[0] < 1.005)  # within 0.5% of arb
    print()
    print(f"Total candidates examined: {len(rows)}")
    print(f"Real arbs (inv-sum <1.0):       {arbs_count}")
    print(f"Within 0.5% of arb (1.0–1.005): {near_count}")
    print(f"Best non-arb gap:               {(rows[arbs_count][0] - 1.0) * 100:.3f}% from breakeven" if rows and arbs_count < len(rows) else "")


if __name__ == "__main__":
    main()
