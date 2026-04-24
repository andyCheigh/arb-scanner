"""Entry point. Runs an immediate scan, then idles on the cron schedule."""

from __future__ import annotations

import asyncio
import logging
import sys

import config
from engine import Engine


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("arb_scanner.log"),
        ],
    )
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def run():
    setup_logging()
    log = logging.getLogger("main")

    cfg = config.load()
    engine = Engine(cfg)

    await engine.notifier.send_startup(cfg.sports, cfg.books, cfg.min_profit_pct, cfg.bankroll_usd)
    log.info(f"Loaded {len(cfg.odds_api_keys)} Odds API key(s); scans at PT hours {cfg.scan_hours_pt}")
    await engine.run_scan()

    engine.schedule()
    engine.start()
    log.info("Arb scanner running. Ctrl+C to stop.")

    stop = asyncio.Event()
    try:
        await stop.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("Shutting down")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
