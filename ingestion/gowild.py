"""gowild.py — https://gowild.al/en  (nationwide aggregator, HTML slides)."""
from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ingestion.base import Event, url_id, parse_date

BASE_URL = "https://gowild.al"
URL = "https://gowild.al/en"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
    )
}


def fetch() -> list[Event]:
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out: list[Event] = []
    for card in soup.select("a.upcoming-slide"):
        href = card.get("href")
        if not href:
            continue
        event_url = urljoin(BASE_URL, href)

        title_el = card.select_one(".event-title")
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue

        date_el = card.select_one(".event-time")
        raw_date = date_el.get_text(" ", strip=True) if date_el else None
        start = parse_date(raw_date)
        if not start:
            print(f"[gowild] unparseable date {raw_date!r} for {title!r} — skipped")
            continue

        # Background image lives in the inline style: background-image:url(...)
        image = None
        style = card.get("style", "")
        if "background-image" in style:
            s, e = style.find("url("), style.find(")", style.find("url("))
            if s != -1 and e != -1:
                image = style[s + 4:e].strip("'\"")

        out.append(Event(
            source="gowild",
            external_id=url_id(event_url),
            title=title,
            start_date=start,
            image_url=image,
            source_url=event_url,
            # municipality unknown — gowild is nationwide; left None.
        ))
    return out