"""Entry point. Runs an immediate scan, then idles on the cron schedule."""

from __future__ import annotations

# Force the process timezone to Pacific BEFORE importing logging-related modules,
# so log timestamps are PT regardless of the host (Mac local vs Linux UTC devbox).
import os
import time as _time

os.environ["TZ"] = "America/Los_Angeles"
try:
    _time.tzset()  # Unix only (macOS, Linux). Windows ignores; not a target.
except AttributeError:
    pass

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

    await engine.notifier.send_startup(
        cfg.sports,
        cfg.books,
        cfg.min_profit_pct,
        cfg.bankroll_usd,
        cfg.scan_times_pt,
        len(cfg.odds_api_keys),
    )
    times = ", ".join(f"{h:02d}:{m:02d}" for h, m in cfg.scan_times_pt)
    log.info(f"Loaded {len(cfg.odds_api_keys)} Odds API key(s); scans at PT times: {times}")
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
