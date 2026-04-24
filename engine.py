"""Orchestration: run a scan, dedup new arbs, alert."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from arb_finder import find_arbs
from config import Config
from odds_api import fetch_odds
from state import State
from telegram_bot import TelegramNotifier

logger = logging.getLogger(__name__)
PACIFIC = pytz.timezone("America/Los_Angeles")


class Engine:
    def __init__(self, config: Config):
        self.config = config
        self.state = State(config.state_path)
        self.notifier = TelegramNotifier(config.telegram_token, config.telegram_chat_id)
        self.scheduler = AsyncIOScheduler(timezone=PACIFIC)

    async def run_scan(self):
        logger.info("Scan starting")
        events, quota = fetch_odds(
            self.config.odds_api_keys,
            self.config.sports,
            self.config.books,
        )
        logger.info(
            f"Fetched {len(events)} events; "
            f"min key remaining: {quota['remaining']} ({quota.get('total_remaining', '?')} total across {quota.get('keys_used', 1)} key(s))"
        )

        arbs = find_arbs(events, self.config.bankroll_usd, self.config.min_profit_pct)
        logger.info(f"Found {len(arbs)} arbs ≥ {self.config.min_profit_pct}%")

        new_arbs = [a for a in arbs if not self.state.is_seen(a.signature())]
        logger.info(f"{len(new_arbs)} new (not previously alerted)")

        await self.notifier.send_digest(new_arbs, scanned_events=len(events), quota_remaining=quota.get("total_remaining", quota["remaining"]))

        for a in new_arbs:
            self.state.mark_seen(a.signature(), a.profit_pct)

        # Prune signatures older than 14 days
        self.state.prune_older_than(datetime.now(timezone.utc) - timedelta(days=14))

        # Warn if any single key is dangerously low (we lose round-robin headroom)
        if 0 <= quota["remaining"] <= 50:
            await self.notifier._send(f"⚠️ Odds API quota low on at least one key: min {quota['remaining']} left this month")

    def schedule(self):
        for hour in self.config.scan_hours_pt:
            self.scheduler.add_job(
                self.run_scan,
                trigger=CronTrigger(hour=hour, minute=0, timezone=PACIFIC),
                id=f"scan_{hour}",
                replace_existing=True,
            )
        logger.info(f"Scans scheduled at PT hours: {self.config.scan_hours_pt}")

    def start(self):
        self.scheduler.start()
