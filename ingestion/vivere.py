"""vivere.py — https://vivere.al  (Tirana venue, HTML cards). Selectors from notebook."""
from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from base import Event, url_id, parse_date

BASE_URL = "https://vivere.al/"
URL = "https://vivere.al/index.php?lang=en"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch() -> list[Event]:
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out: list[Event] = []
    for card in soup.select("div.ev"):
        link = card.select_one("a[href]")
        if not link:
            continue
        event_url = urljoin(BASE_URL, link.get("href"))

        h4 = card.select_one("h4")
        title = h4.get_text(strip=True) if h4 else None
        if not title:
            continue

        span = card.select_one("span")
        category = span.get_text(strip=True) if span else None

        p = card.select_one(".inf--1 p")
        raw_date = p.get_text(strip=True) if p else None
        start = parse_date(raw_date)
        if not start:
            # start_date is NOT NULL — skip rather than insert garbage.
            print(f"[vivere] unparseable date {raw_date!r} for {title!r} — skipped")
            continue

        img = card.select_one("img")
        image = urljoin(BASE_URL, img.get("src")) if img else None

        out.append(Event(
            source="vivere",
            external_id=url_id(event_url),
            title=title,
            start_date=start,
            category=category,
            municipality="Tiranë",   # Vivere is a fixed Tirana venue
            image_url=image,
            source_url=event_url,
        ))
    return out