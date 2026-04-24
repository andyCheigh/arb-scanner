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
    odds_api_key: str
    min_profit_pct: float
    bankroll_usd: float
    sports: tuple[str, ...]
    books: tuple[str, ...]

    # Scan cron (Pacific). Default: 9a/1p/5p/9p = 4×/day
    scan_hours_pt: tuple[int, ...] = (9, 13, 17, 21)

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

    return Config(
        telegram_token=required["TELEGRAM_BOT_TOKEN"],
        telegram_chat_id=required["TELEGRAM_CHAT_ID"],
        odds_api_key=required["ODDS_API_KEY"],
        min_profit_pct=float(os.getenv("MIN_PROFIT_PCT", "1.0")),
        bankroll_usd=float(os.getenv("BANKROLL_USD", "1000")),
        sports=_csv(
            "SPORTS",
            "americanfootball_nfl,basketball_nba,baseball_mlb,icehockey_nhl,mma_mixed_martial_arts,soccer_epl",
        ),
        books=_csv(
            "BOOKS",
            "draftkings,fanduel,betmgm,caesars,betrivers,espnbet,williamhill_us,pinnacle",
        ),
    )
