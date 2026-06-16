"""
base.py — Pjesët e përbashkëta për të gjithë skrapuesit e eventeve:
          Event dataclass, dedup, parsim datash (shqip + anglisht), upsert glue.

Çdo skrapues (tea.py, vivere.py, ...) importon nga këtu dhe kthen list[Event].
run.py i mbledh të gjithë, deduplikon dhe ngarkon në SQLite.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

from dateutil import parser as dtparser

# --- DB glue ---------------------------------------------------------------
# Skrapuesit jetojnë te ingestion/, por database.py është te rrënja e projektit.
# Shtojmë rrënjën në sys.path që `from database import ...` të funksionojë pa
# marrë parasysh nga ku ekzekutohet skripti.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from database import upsert_events, query_events, prune_events  # noqa: E402  (re-exported)


# ---------------------------------------------------------------------------
# Normalized schema
# ---------------------------------------------------------------------------

@dataclass
class Event:
    source:        str
    external_id:   str
    title:         str
    start_date:    str           # ISO 8601 — required, NOT NULL në DB
    description:   Optional[str] = None
    category:      Optional[str] = None
    municipality:  Optional[str] = None
    end_date:      Optional[str] = None
    lat:           Optional[float] = None
    lon:           Optional[float] = None
    image_url:     Optional[str] = None
    ticket_url:    Optional[str] = None
    source_url:    Optional[str] = None


def url_id(url: str) -> str:
    """Stable external_id for sources that don't expose their own ID."""
    return hashlib.md5(url.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Date parsing — Albanian + English, free-text → ISO 8601 date
# ---------------------------------------------------------------------------
# Sources give dates as human strings ("14 Qershor 2026", "June 10", "10.06.2026").
# We map Albanian month tokens to English, then let dateutil do the heavy lifting.
# Returns None on failure — caller MUST skip events with no parseable date,
# because start_date is NOT NULL in the schema.

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

_ALB_MONTHS = {
    "janar": "January", "shkurt": "February", "mars": "March", "prill": "April",
    "maj": "May", "qershor": "June", "korrik": "July", "gusht": "August",
    "shtator": "September", "tetor": "October", "nentor": "November",
    "nëntor": "November", "dhjetor": "December",
    # common abbreviations
    "jan": "January", "shk": "February", "mar": "March", "pri": "April",
    "qer": "June", "kor": "July", "gus": "August", "sht": "September",
    "tet": "October", "nen": "November", "nën": "November", "dhj": "December",
}

def parse_date(raw: Optional[str], year_hint: Optional[int] = None) -> Optional[str]:
    """
    Best-effort parse to ISO date (YYYY-MM-DDTHH:MM:SS). Returns None if unparseable.

    year_hint: many listing pages omit the year ("14 Qershor"). We default to the
    current year so day/month-only strings resolve sensibly. Tune if a source
    lists next-year events without a year.
    """
    if not raw:
        return None
    s = raw.strip()

    # Already ISO (e.g. TEA's startDate) — parse directly so dayfirst can't
    # flip month/day (2026-06-10 must stay June 10, not Oct 6).
    if _ISO_RE.match(s):
        try:
            return dtparser.isoparse(s).isoformat()
        except ValueError:
            pass

    # Guard against the fuzzy-parse trap: with fuzzy=True + a default date,
    # pure-text junk ("next thursday blah") silently returns Jan 1 instead of
    # failing. A real date always contains a digit (day or year); reject if none.
    if not any(ch.isdigit() for ch in s):
        return None

    s = s.lower()
    # Replace Albanian month tokens with English (word-boundary, longest first).
    for alb in sorted(_ALB_MONTHS, key=len, reverse=True):
        s = re.sub(rf"\b{alb}\b", _ALB_MONTHS[alb], s)

    default = datetime(year_hint or datetime.now().year, 1, 1)
    try:
        dt = dtparser.parse(s, fuzzy=True, default=default, dayfirst=True)
        return dt.isoformat()
    except (ValueError, OverflowError):
        return None


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------
# CHANGE from Round 1: dedup_key no longer includes municipality.
# Reason: the 5 scraped sources are Tirana-centric and mostly DON'T provide a
# municipality field, while TEA does ("Tiranë"). Keeping municipality in the key
# meant a TEA event ("...|tirane") could never match the same Vivere event
# ("...|"). For cross-source dedup to work at all, the key must use only fields
# every source reliably has: title + start-day.
#
# Tradeoff: slightly more aggressive. A touring act with the SAME title on the
# SAME day in two cities would wrongly collapse — rare enough to accept for now.

SOURCE_PRIORITY = {
    "tea": 0, "vivere": 1, "gowild": 2,
    "enterevents": 3, "kookooli": 4, "almanart": 5,
}


def _slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "", s).lower()


def make_dedup_key(title: str, start_date: str) -> str:
    """title (slug) | start-day (YYYY-MM-DD). Time + municipality dropped."""
    return f"{_slugify(title or '')}|{(start_date or '')[:10]}"


def dedup_canonicalize(events: list[Event]) -> list[dict]:
    """
    Group by dedup_key; within each group the highest-priority source is
    canonical. Returns row dicts ready for upsert_events.
    """
    groups: dict[str, list[Event]] = {}
    for e in events:
        groups.setdefault(make_dedup_key(e.title, e.start_date), []).append(e)

    rows: list[dict] = []
    for key, group in groups.items():
        group.sort(key=lambda e: SOURCE_PRIORITY.get(e.source, 99))
        for idx, ev in enumerate(group):
            row = asdict(ev)
            row["dedup_key"] = key
            row["is_canonical"] = 1 if idx == 0 else 0
            rows.append(row)
    return rows
