"""
almanart.py — https://www.almanart.al/aktivitetet-javore/  (MEC calendar plugin).

WEAKEST SOURCE: the notebook code captured title/url/location but NO date.
This site uses the "Modern Events Calendar" WordPress plugin, whose date markup
varies by theme. Below tries the common MEC selectors; if none match, the event
is skipped (start_date is required). VALIDATE selectors against live HTML —
if everything is skipped, inspect one article and adjust `_extract_date`.
"""
from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from base import Event, url_id, parse_date

URL = "https://www.almanart.al/aktivitetet-javore/"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _extract_date(article) -> str | None:
    # Common MEC date locations, in order of reliability.
    # 1) <time datetime="..."> machine-readable
    t = article.select_one("time[datetime]")
    if t and t.get("datetime"):
        return t["datetime"]
    # 2) MEC date wrapper classes
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
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        event_url = urljoin(URL, title_el["href"])

        start = parse_date(_extract_date(article))
        if not start:
            print(f"[almanart] no parseable date for {title!r} — skipped")
            continue

        loc_el = article.select_one(".mec-event-loc-place")
        location = loc_el.get_text(" ", strip=True) if loc_el else None

        out.append(Event(
            source="almanart",
            external_id=url_id(event_url),
            title=title,
            start_date=start,
            municipality="Tiranë",   # AlmanArt is the Tirana arts gallery calendar
            description=location,    # no real description; store venue here
            source_url=event_url,
        ))
    return out