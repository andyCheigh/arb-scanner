"""JSON-file dedup store — avoid re-alerting on the same arb."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class State:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.data: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load state {self.path}: {e}")
            return {}

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2, default=str)

    def is_seen(self, signature: str) -> bool:
        return signature in self.data

    def mark_seen(self, signature: str, profit_pct: float):
        self.data[signature] = {
            "seen_at": datetime.now(timezone.utc).isoformat(),
            "profit_pct": profit_pct,
        }
        self.save()

    def prune_older_than(self, cutoff: datetime):
        removed = 0
        for sig in list(self.data.keys()):
            ts = self.data[sig].get("seen_at")
            if ts:
                try:
                    if datetime.fromisoformat(ts) < cutoff:
                        del self.data[sig]
                        removed += 1
                except ValueError:
                    pass
        if removed:
            self.save()
            logger.info(f"Pruned {removed} stale arb signatures")
