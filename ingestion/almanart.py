"""
almanart.py — https://www.almanart.al/aktivitetet-javore/  (MEC calendar plugin).

AlmanArt is an all-Albania weekly culture calendar built on the WordPress
"Modern Events Calendar" (MEC) plugin, weekly-list skin. We scrape the listing,
keep only Tirana events, and parse each event's date.

The date lives in `.mec-event-list-weekly-date` — a day number (`.mec-date-day`)
followed by the month text — NOT in the generic MEC date classes the old version
looked for, which is why every event used to be skipped. parse_date reads the
rejoined "22 Qershor" via its Albanian-month map. Events with no parseable date
are skipped (start_date is required / NOT NULL in the schema).
"""
from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ingestion.base import Event, url_id, parse_date

URL = "https://www.almanart.al/aktivitetet-javore/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
}


def _extract_date(article) -> str | None:
    """Pull the event date from the weekly-list block.

    The weekly skin renders the date as a day number (`.mec-date-day`) followed
    by month text inside `.mec-event-list-weekly-date`. We rejoin them with a
    space so parse_date sees e.g. "22 Qershor" — its month map relies on word
    boundaries, so a glued "22Qershor" would not match.

    Falls back to the older MEC date classes in case a different layout appears
    on the page. Returns None when nothing date-like is found.
    """
    cont = article.select_one(".mec-event-list-weekly-date")
    if cont:
        day_el = cont.select_one(".mec-date-day")
        day = day_el.get_text(strip=True) if day_el else ""
        rest = cont.get_text(" ", strip=True)
        month = rest.replace(day, "", 1).strip() if day else rest
        combined = f"{day} {month}".strip()
        if combined and any(c.isdigit() for c in combined):
            return combined

    t = article.select_one("time[datetime]")
    if t and t.get("datetime"):
        return t["datetime"]
    for sel in (".mec-event-date", ".mec-start-date-label", ".mec-date-details"):
        el = article.select_one(sel)
        if el:
            return el.get_text(" ", strip=True)
    return None


def fetch() -> list[Event]:
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out: list[Event] = []
    for article in soup.select("article.mec-event-article"):
        title_el = article.select_one(".mec-event-title a")
        if not title_el or not title_el.has_attr("href"):
            continue
        title = title_el.get_text(strip=True)
        event_url = urljoin(URL, title_el["href"])

        loc_el = article.select_one(".mec-event-loc-place")
        location = loc_el.get_text(" ", strip=True) if loc_el else ""

        # AlmanArt lists all of Albania — keep only Tirana. "tiran" covers
        # Tirane / Tiranë / Tirana in either the venue or the title; non-Tirana
        # events name Vlorë / Berat / Sarandë / etc.
        if "tiran" not in f"{location} {title}".lower():
            continue

        start = parse_date(_extract_date(article))
        if not start:
            print(f"[almanart] no parseable date for {title!r} — skipped")
            continue

        out.append(Event(
            source="almanart",
            external_id=url_id(event_url),
            title=title,
            start_date=start,
            municipality="Tiranë",   # filtered to Tirana above
            description=location or None,
            source_url=event_url,
        ))
    return out