"""Core arbitrage detection.

For each event, examine every market type (h2h, spreads, totals) and find
combinations where the inverse-odds across the best price for each side
sum to less than 1.0 — that's a guaranteed-profit arbitrage.

We require the two/three legs to come from DIFFERENT books (otherwise
it's a single-book mistake, not an arb you can act on).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from odds_api import Event, Outcome


@dataclass
class ArbLeg:
    book_key: str
    book_title: str
    outcome_name: str       # "49ers", "Over", "Draw"
    decimal_odds: float
    point: float | None     # for spreads/totals; None for h2h
    stake: float            # USD allocated to this leg given total bankroll


@dataclass
class Arb:
    event: Event
    market_key: str         # "h2h" | "spreads" | "totals"
    legs: list[ArbLeg]
    profit_pct: float       # e.g. 3.4 means 3.4% guaranteed return
    profit_usd: float       # absolute profit on the bankroll
    total_stake: float

    def signature(self) -> str:
        legs = "|".join(
            f"{l.book_key}:{l.outcome_name}:{l.decimal_odds}:{l.point or 'na'}"
            for l in sorted(self.legs, key=lambda x: x.book_key)
        )
        return f"{self.event.event_id}:{self.market_key}:{legs}"


def american_from_decimal(d: float) -> str:
    """Render decimal odds as American for display."""
    if d <= 1.0:
        return f"{d:.2f}"
    if d >= 2.0:
        return f"+{int(round((d - 1) * 100))}"
    return f"-{int(round(100 / (d - 1)))}"


def _allocate_stakes(prices: list[float], bankroll: float) -> list[float]:
    """Equal-payout allocation: stake_i = bankroll * (1/d_i) / sum(1/d_j)."""
    inv_sum = sum(1.0 / p for p in prices)
    return [bankroll * (1.0 / p) / inv_sum for p in prices]


def _check_arb(
    sides: list[tuple[str, str, str, float, float | None]],  # (side_name, book_key, book_title, price, point)
    bankroll: float,
    min_profit_pct: float,
) -> tuple[float, float, list[float]] | None:
    """Given best price per side, return (profit_pct, profit_usd, stakes) if arb."""
    prices = [s[3] for s in sides]
    inv_sum = sum(1.0 / p for p in prices)
    if inv_sum >= 1.0:
        return None

    payout = bankroll / inv_sum  # what we get back regardless of outcome
    profit = payout - bankroll
    profit_pct = (1.0 / inv_sum - 1.0) * 100
    if profit_pct < min_profit_pct:
        return None

    stakes = _allocate_stakes(prices, bankroll)
    return profit_pct, profit, stakes


def _find_h2h_arbs(event: Event, bankroll: float, min_profit_pct: float) -> list[Arb]:
    """Head-to-head: 2-way (most US sports) or 3-way (soccer w/ Draw)."""
    # side_name -> [(book_key, book_title, price, point=None)]
    by_side: dict[str, list[tuple[str, str, float, float | None]]] = defaultdict(list)
    for bm in event.markets:
        if bm.market_key != "h2h":
            continue
        for o in bm.outcomes:
            by_side[o.name].append((bm.book_key, bm.book_title, o.price, None))

    if len(by_side) < 2:
        return []

    # Best price per side
    best_per_side: list[tuple[str, str, str, float, float | None]] = []
    for side_name, options in by_side.items():
        book_key, book_title, price, point = max(options, key=lambda x: x[2])
        best_per_side.append((side_name, book_key, book_title, price, point))

    # Need legs from different books
    if len({s[1] for s in best_per_side}) < len(best_per_side):
        return []

    result = _check_arb(best_per_side, bankroll, min_profit_pct)
    if result is None:
        return []
    profit_pct, profit, stakes = result
    legs = [
        ArbLeg(book_key=bk, book_title=bt, outcome_name=name, decimal_odds=price, point=pt, stake=st)
        for (name, bk, bt, price, pt), st in zip(best_per_side, stakes)
    ]
    return [Arb(event=event, market_key="h2h", legs=legs, profit_pct=profit_pct, profit_usd=profit, total_stake=bankroll)]


def _best_per_team_point(
    event: Event, market_key: str
) -> dict[tuple[str, float], tuple[str, str, float]]:
    """For a given market, find the best (highest) decimal price per
    (outcome_name, point) combination across every book in the event.

    Returns: {(name, point): (book_key, book_title, price)}
    """
    best: dict[tuple[str, float], tuple[str, str, float]] = {}
    for bm in event.markets:
        if bm.market_key != market_key:
            continue
        for o in bm.outcomes:
            if o.point is None:
                continue
            key = (o.name, o.point)
            existing = best.get(key)
            if existing is None or o.price > existing[2]:
                best[key] = (bm.book_key, bm.book_title, o.price)
    return best


def _build_arb(
    event: Event,
    market_key: str,
    sides: list[tuple[str, str, str, float, float]],
    bankroll: float,
    min_profit_pct: float,
) -> Arb | None:
    if len({s[1] for s in sides}) < len(sides):
        return None  # legs must be from different books
    sides_for_check: list[tuple[str, str, str, float, float | None]] = [
        (n, bk, bt, p, pt) for (n, bk, bt, p, pt) in sides
    ]
    result = _check_arb(sides_for_check, bankroll, min_profit_pct)
    if result is None:
        return None
    profit_pct, profit, stakes = result
    legs = [
        ArbLeg(book_key=bk, book_title=bt, outcome_name=name, decimal_odds=price, point=pt, stake=st)
        for (name, bk, bt, price, pt), st in zip(sides, stakes)
    ]
    return Arb(
        event=event,
        market_key=market_key,
        legs=legs,
        profit_pct=profit_pct,
        profit_usd=profit,
        total_stake=bankroll,
    )


def _find_spread_arbs(event: Event, bankroll: float, min_profit_pct: float) -> list[Arb]:
    """For each unique spread magnitude L, pair home_team at -L with away_team at +L
    (and the reverse). The two legs MUST be opposite sides of the SAME line:
    one wins iff the margin exceeds L, the other wins iff it doesn't.
    """
    best = _best_per_team_point(event, "spreads")
    arbs: list[Arb] = []
    seen_pairings: set[tuple] = set()

    magnitudes = {abs(point) for (_, point) in best.keys() if point != 0}
    for L in magnitudes:
        for home_sign in (-1, 1):
            home_pt = home_sign * L
            away_pt = -home_sign * L
            home_key = (event.home_team, home_pt)
            away_key = (event.away_team, away_pt)
            if home_key not in best or away_key not in best:
                continue
            hbk, hbt, hp = best[home_key]
            abk, abt, ap = best[away_key]

            sig = tuple(sorted(((hbk, event.home_team, home_pt, hp), (abk, event.away_team, away_pt, ap))))
            if sig in seen_pairings:
                continue
            seen_pairings.add(sig)

            sides = [
                (event.home_team, hbk, hbt, hp, home_pt),
                (event.away_team, abk, abt, ap, away_pt),
            ]
            arb = _build_arb(event, "spreads", sides, bankroll, min_profit_pct)
            if arb is not None:
                arbs.append(arb)
    return arbs


def _find_totals_arbs(event: Event, bankroll: float, min_profit_pct: float) -> list[Arb]:
    """For each total line value L, pair Over @ L with Under @ L."""
    best = _best_per_team_point(event, "totals")
    arbs: list[Arb] = []
    line_values = {point for (_, point) in best.keys()}
    for L in line_values:
        over_key = ("Over", L)
        under_key = ("Under", L)
        if over_key not in best or under_key not in best:
            continue
        obk, obt, op = best[over_key]
        ubk, ubt, up = best[under_key]
        sides = [
            ("Over", obk, obt, op, L),
            ("Under", ubk, ubt, up, L),
        ]
        arb = _build_arb(event, "totals", sides, bankroll, min_profit_pct)
        if arb is not None:
            arbs.append(arb)
    return arbs


def find_arbs(events: list[Event], bankroll: float, min_profit_pct: float) -> list[Arb]:
    """Scan every event across h2h, spreads, totals and return all qualifying arbs."""
    arbs: list[Arb] = []
    for ev in events:
        arbs.extend(_find_h2h_arbs(ev, bankroll, min_profit_pct))
        arbs.extend(_find_spread_arbs(ev, bankroll, min_profit_pct))
        arbs.extend(_find_totals_arbs(ev, bankroll, min_profit_pct))
    arbs.sort(key=lambda a: a.profit_pct, reverse=True)
    return arbs
