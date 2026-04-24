"""Telegram notifier for arb alerts."""

from __future__ import annotations

import logging

import pytz
from telegram import Bot

from arb_finder import Arb, american_from_decimal

logger = logging.getLogger(__name__)
PACIFIC = pytz.timezone("America/Los_Angeles")


def _to_pt(dt):
    """Convert a tz-aware datetime to Pacific."""
    return dt.astimezone(PACIFIC) if dt is not None else None


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.bot = Bot(token=token)
        self.chat_id = chat_id

    async def _send(self, text: str):
        try:
            if len(text) > 4000:
                text = text[:3900] + "\n...(truncated)"
            await self.bot.send_message(chat_id=self.chat_id, text=text, disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    @staticmethod
    def _format_arb(arb: Arb) -> str:
        ev = arb.event
        market_label = {"h2h": "Moneyline", "spreads": "Spread", "totals": "Total"}.get(arb.market_key, arb.market_key)
        commence = _to_pt(ev.commence_time).strftime("%a %b %d %I:%M%p PT")

        lines = [
            f"💰 ARB {arb.profit_pct:.2f}% — {ev.sport_title} {market_label}",
            f"{ev.away_team} @ {ev.home_team}  ({commence})",
            "",
        ]
        for i, leg in enumerate(arb.legs, 1):
            point = ""
            if leg.point is not None:
                if arb.market_key == "spreads":
                    point = f" {leg.point:+g}"
                else:
                    point = f" {leg.point:g}"
            lines.append(
                f"  Leg {i}: {leg.outcome_name}{point} @ {leg.book_title} "
                f"({american_from_decimal(leg.decimal_odds)} / {leg.decimal_odds:.2f}d)"
            )
            lines.append(f"          stake ${leg.stake:.2f}")
        lines.append("")
        lines.append(f"Total stake: ${arb.total_stake:.2f} → guaranteed return ${arb.total_stake + arb.profit_usd:.2f} (+${arb.profit_usd:.2f})")
        if arb.legs[0].book_title:
            updates = sorted({m.last_update for m in ev.markets if m.last_update}, reverse=True)
            if updates:
                lines.append(f"Lines pulled: {_to_pt(updates[0]).strftime('%I:%M%p PT')} — go fast")
        return "\n".join(lines)

    async def send_arb(self, arb: Arb):
        await self._send(self._format_arb(arb))

    async def send_digest(self, arbs: list[Arb], scanned_events: int, quota_remaining: int):
        if not arbs:
            await self._send(
                f"ARB SCAN — no arbs ≥ threshold across {scanned_events} events.\n"
                f"Odds API quota remaining this month: {quota_remaining}"
            )
            return
        header = f"ARB SCAN — {len(arbs)} new arb(s) across {scanned_events} events (quota: {quota_remaining})"
        body = "\n\n".join(self._format_arb(a) for a in arbs)
        await self._send(f"{header}\n\n{body}")

    async def send_startup(
        self,
        sports: tuple[str, ...],
        books: tuple[str, ...],
        min_profit: float,
        bankroll: float,
        scan_times_pt: list[tuple[int, int]],
        keys_count: int,
    ):
        times = ", ".join(f"{h:02d}:{m:02d}" for h, m in scan_times_pt)
        msg = (
            f"ARB SCANNER STARTED\n\n"
            f"Sports ({len(sports)}): {', '.join(sports)}\n"
            f"Books ({len(books)}): {', '.join(books)}\n"
            f"Min profit alert: {min_profit:.2f}%\n"
            f"Stake reference: ${bankroll:.0f}\n"
            f"Odds API keys: {keys_count}\n"
            f"Scans (PT): {times}"
        )
        await self._send(msg)
