"""The Odds API client. Free tier: 500 req/month at the-odds-api.com."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.the-odds-api.com/v4"


@dataclass
class Outcome:
    name: str               # team name, "Over", "Under", or "Draw"
    price: float            # decimal odds
    point: float | None     # spread/total line; None for h2h


@dataclass
class BookMarket:
    book_key: str           # e.g. "draftkings"
    book_title: str         # e.g. "DraftKings"
    market_key: str         # "h2h", "spreads", "totals"
    outcomes: list[Outcome]
    last_update: datetime | None


@dataclass
class Event:
    event_id: str
    sport_key: str
    sport_title: str
    commence_time: datetime
    home_team: str
    away_team: str
    markets: list[BookMarket]   # flattened across books

    def short_ref(self) -> str:
        when = self.commence_time.strftime("%a %b %d %I:%M%p UTC")
        return f"{self.sport_title}: {self.away_team} @ {self.home_team} ({when})"


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_odds(
    api_key: str,
    sports: Iterable[str],
    books: Iterable[str],
    markets: tuple[str, ...] = ("h2h", "spreads", "totals"),
) -> tuple[list[Event], dict[str, int]]:
    """Pull odds for each sport. Returns (events, quota_info).

    quota_info has 'remaining' and 'used' counts read from response headers,
    so we can warn when the monthly free-tier budget is running out.
    """
    bookmakers_csv = ",".join(books)
    markets_csv = ",".join(markets)

    all_events: list[Event] = []
    quota = {"remaining": -1, "used": -1}

    for sport in sports:
        url = f"{BASE_URL}/sports/{sport}/odds"
        params = {
            "apiKey": api_key,
            "regions": "us,us2,eu",
            "markets": markets_csv,
            "bookmakers": bookmakers_csv,
            "oddsFormat": "decimal",
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 422:
                logger.info(f"Sport {sport} not in season / no events")
                continue
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Odds fetch failed for {sport}: {e}")
            continue

        try:
            quota["remaining"] = int(resp.headers.get("x-requests-remaining", -1))
            quota["used"] = int(resp.headers.get("x-requests-used", -1))
        except (TypeError, ValueError):
            pass

        events = resp.json()
        logger.info(f"{sport}: {len(events)} events (quota left: {quota['remaining']})")

        for ev in events:
            commence = _parse_dt(ev.get("commence_time"))
            if not commence or commence < datetime.now(timezone.utc):
                continue

            book_markets: list[BookMarket] = []
            for bm in ev.get("bookmakers") or []:
                last_update = _parse_dt(bm.get("last_update"))
                for mk in bm.get("markets") or []:
                    outcomes = [
                        Outcome(
                            name=o.get("name", ""),
                            price=float(o.get("price", 0)),
                            point=(float(o["point"]) if o.get("point") is not None else None),
                        )
                        for o in mk.get("outcomes") or []
                        if o.get("price")
                    ]
                    if not outcomes:
                        continue
                    book_markets.append(
                        BookMarket(
                            book_key=bm.get("key", ""),
                            book_title=bm.get("title", ""),
                            market_key=mk.get("key", ""),
                            outcomes=outcomes,
                            last_update=last_update,
                        )
                    )

            if not book_markets:
                continue

            all_events.append(
                Event(
                    event_id=ev["id"],
                    sport_key=ev.get("sport_key", sport),
                    sport_title=ev.get("sport_title", sport),
                    commence_time=commence,
                    home_team=ev.get("home_team", ""),
                    away_team=ev.get("away_team", ""),
                    markets=book_markets,
                )
            )

    return all_events, quota
