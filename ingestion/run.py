"""
run.py — Mbledh të gjithë skrapuesit, deduplikon, ngarkon në SQLite.

Ekzekuto:  python run.py
"""
from __future__ import annotations

import sys
from datetime import datetime

from base import dedup_canonicalize, upsert_events
import tea, vivere, gowild, enterevents, kookooli, almanart

# (name, fetch_callable). Order here is cosmetic; canonical pick is by
# SOURCE_PRIORITY in base.py, not by run order.
SCRAPERS = [
    ("tea",         tea.fetch),
    ("vivere",      vivere.fetch),
    ("gowild",      gowild.fetch),
    ("enterevents", enterevents.fetch),
    ("kookooli",    kookooli.fetch),
    ("almanart",    almanart.fetch),
]


def run_all() -> dict:
    started = datetime.utcnow().isoformat()
    per_source: dict[str, int] = {}
    all_events = []

    for name, fn in SCRAPERS:
        try:
            evs = fn()
            per_source[name] = len(evs)
            all_events.extend(evs)
            print(f"[{name}] fetched {len(evs)} events")
        except Exception as exc:
            per_source[name] = -1
            print(f"[{name}] FAILED: {exc}", file=sys.stderr)

    rows = dedup_canonicalize(all_events)
    canonical = sum(1 for r in rows if r["is_canonical"] == 1)
    inserted, updated = upsert_events(rows)

    summary = {
        "started_at":    started,
        "finished_at":   datetime.utcnow().isoformat(),
        "per_source":    per_source,
        "total_fetched": len(all_events),
        "canonical":     canonical,
        "duplicates":    len(rows) - canonical,
        "inserted":      inserted,
        "updated":       updated,
    }
    print("\n== Run summary ==")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return summary


if __name__ == "__main__":
    run_all()