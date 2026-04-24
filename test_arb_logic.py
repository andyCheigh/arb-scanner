"""Logic tests for arb_finder — no API calls, just synthetic event data."""

from __future__ import annotations

from datetime import datetime, timezone

from arb_finder import find_arbs
from odds_api import BookMarket, Event, Outcome


def make_event(markets: list[BookMarket]) -> Event:
    return Event(
        event_id="test1",
        sport_key="icehockey_nhl",
        sport_title="NHL",
        commence_time=datetime.now(timezone.utc),
        home_team="Carolina Hurricanes",
        away_team="Ottawa Senators",
        markets=markets,
    )


def case(name: str, markets: list[BookMarket], expect_arb: bool, expect_market: str | None = None):
    arbs = find_arbs([make_event(markets)], bankroll=1000, min_profit_pct=0.5)
    if expect_arb:
        if not arbs:
            print(f"  ✗ {name}: expected an arb, got none")
            return False
        if expect_market and arbs[0].market_key != expect_market:
            print(f"  ✗ {name}: expected market={expect_market}, got {arbs[0].market_key}")
            return False
        print(f"  ✓ {name}: detected arb {arbs[0].market_key} {arbs[0].profit_pct:.2f}%")
        return True
    else:
        if arbs:
            a = arbs[0]
            legs = ", ".join(f"{l.outcome_name}{l.point or ''}@{l.book_title}" for l in a.legs)
            print(f"  ✗ {name}: expected NO arb, got {a.market_key} {a.profit_pct:.2f}% [{legs}]")
            return False
        print(f"  ✓ {name}: correctly rejected")
        return True


# CASE 1: The fake "arb" the user caught — both teams at -1.5 (same side, different books)
fake_spread = [
    BookMarket("fanduel", "FanDuel", "spreads", [
        Outcome("Carolina Hurricanes", 3.10, -1.5),
        Outcome("Ottawa Senators", 1.40, 1.5),
    ], None),
    BookMarket("pinnacle", "Pinnacle", "spreads", [
        Outcome("Carolina Hurricanes", 1.45, 1.5),
        Outcome("Ottawa Senators", 3.34, -1.5),
    ], None),
]

# CASE 2: A REAL spread arb — Carolina -1.5 (FD) + Ottawa +1.5 (Pinnacle), opposite sides same line
real_spread = [
    BookMarket("fanduel", "FanDuel", "spreads", [
        Outcome("Carolina Hurricanes", 2.50, -1.5),
        Outcome("Ottawa Senators", 1.55, 1.5),
    ], None),
    BookMarket("pinnacle", "Pinnacle", "spreads", [
        Outcome("Carolina Hurricanes", 1.60, -1.5),
        Outcome("Ottawa Senators", 2.40, 1.5),
    ], None),
]

# CASE 3: Real totals arb — Over 5.5 (DK) + Under 5.5 (FanDuel)
totals_arb = [
    BookMarket("draftkings", "DraftKings", "totals", [
        Outcome("Over", 2.10, 5.5),
        Outcome("Under", 1.80, 5.5),
    ], None),
    BookMarket("fanduel", "FanDuel", "totals", [
        Outcome("Over", 1.85, 5.5),
        Outcome("Under", 2.05, 5.5),
    ], None),
]

# CASE 4: Real h2h arb (no overlap from prior bug; just sanity)
h2h_arb = [
    BookMarket("draftkings", "DraftKings", "h2h", [
        Outcome("Carolina Hurricanes", 2.55, None),
        Outcome("Ottawa Senators", 1.55, None),
    ], None),
    BookMarket("fanduel", "FanDuel", "h2h", [
        Outcome("Carolina Hurricanes", 1.50, None),
        Outcome("Ottawa Senators", 2.65, None),
    ], None),
]

print("Arb logic tests:")
results = [
    case("user-caught fake spread (both teams -1.5)", fake_spread, expect_arb=False),
    case("real spread arb (Carolina -1.5 + Ottawa +1.5)", real_spread, expect_arb=True, expect_market="spreads"),
    case("totals arb (Over 5.5 + Under 5.5)", totals_arb, expect_arb=True, expect_market="totals"),
    case("h2h arb", h2h_arb, expect_arb=True, expect_market="h2h"),
]
print(f"\n{sum(results)}/{len(results)} passed")
exit(0 if all(results) else 1)
