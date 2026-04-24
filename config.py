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

    # Scan window in Pacific. Default: 6 scans evenly between 9am and 11pm.
    scan_window_start_hour: int = 9
    scan_window_end_hour: int = 23
    scan_count: int = 6

    # State file for dedup
    state_path: str = "state/seen_arbs.json"

    @property
    def scan_times_pt(self) -> list[tuple[int, int]]:
        """Return [(hour, minute)] evenly spaced across the scan window."""
        if self.scan_count <= 1:
            return [(self.scan_window_start_hour, 0)]
        total_minutes = (self.scan_window_end_hour - self.scan_window_start_hour) * 60
        step = total_minutes / (self.scan_count - 1)
        out: list[tuple[int, int]] = []
        for i in range(self.scan_count):
            offset = round(i * step)
            h = self.scan_window_start_hour + offset // 60
            m = offset % 60
            out.append((h, m))
        return out


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
        scan_window_start_hour=int(os.getenv("SCAN_WINDOW_START_HOUR", "9")),
        scan_window_end_hour=int(os.getenv("SCAN_WINDOW_END_HOUR", "23")),
        scan_count=int(os.getenv("SCAN_COUNT", "6")),
    )
