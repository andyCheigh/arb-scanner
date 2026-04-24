"""Central config: env vars + scan tuning."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    telegram_token: str
    telegram_chat_id: str
    odds_api_keys: tuple[str, ...]   # round-robin if multiple
    min_profit_pct: float
    bankroll_usd: float
    sports: tuple[str, ...]
    books: tuple[str, ...]

    # Scan cron (Pacific). Default: every 4 hours = 6×/day
    scan_hours_pt: tuple[int, ...] = (3, 7, 11, 15, 19, 23)

    # State file for dedup
    state_path: str = "state/seen_arbs.json"


def _csv(env_key: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(env_key, default)
    return tuple(s.strip() for s in raw.split(",") if s.strip())


def load() -> Config:
    required = {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID"),
        "ODDS_API_KEY": os.getenv("ODDS_API_KEY"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    # Collect ODDS_API_KEY plus optional ODDS_API_KEY_2, _3, ... for round-robin
    keys = [required["ODDS_API_KEY"]]
    for suffix in ("_2", "_3", "_4"):
        extra = os.getenv(f"ODDS_API_KEY{suffix}")
        if extra:
            keys.append(extra)

    return Config(
        telegram_token=required["TELEGRAM_BOT_TOKEN"],
        telegram_chat_id=required["TELEGRAM_CHAT_ID"],
        odds_api_keys=tuple(keys),
        min_profit_pct=float(os.getenv("MIN_PROFIT_PCT", "1.0")),
        bankroll_usd=float(os.getenv("BANKROLL_USD", "1000")),
        sports=_csv(
            "SPORTS",
            "americanfootball_nfl,basketball_nba,baseball_mlb,icehockey_nhl,soccer_epl",
        ),
        books=_csv(
            "BOOKS",
            "draftkings,fanduel,betmgm,caesars,betrivers,espnbet,williamhill_us,pinnacle",
        ),
    )
