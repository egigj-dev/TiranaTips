"""
enterevents.py — https://enterevents.al  (list page → per-event detail page).

NOTE: this is N+1 requests (one detail fetch per event), so it's the slowest
HTTP source. We filter to events whose venue mentions Tirana.
"""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from base import Event, url_id, parse_date

BASE = "https://enterevents.al"
TIRANA_KEYWORDS = ("tirana", "tirane", "tiranë")

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0"})


def _event_links():
    url = f"{BASE}/events/"
    while url:
        r = _session.get(url, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a.event-item"):
            href = a.get("href")
            if href:
                yield href
        nxt = soup.select_one("a.next")
        url = nxt["href"] if nxt else None


def _extract(url: str) -> dict:
    r = _session.get(url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    data = {"title": None, "url": url, "image": None,
            "date": None, "start_time": None, "venue": None}

    h1 = soup.find("h1")
    if h1:
        data["title"] = h1.get_text(strip=True)
    img = soup.select_one("img")
    if img:
        data["image"] = img.get("src")

    details = soup.select_one(".event-details")
    if details:
        for p in details.find_all("p"):
            strong = p.find("strong")
            if not strong:
                continue
            key = strong.get_text(strip=True).replace(":", "")
            value = p.get_text(" ", strip=True).replace(strong.get_text(strip=True), "").strip()
            if key == "Date":
                data["date"] = value
            elif key == "Start time":
                data["start_time"] = value
            elif key == "Venue":
                data["venue"] = value
    return data


def fetch() -> list[Event]:
    out: list[Event] = []
    for url in _event_links():
        try:
            ev = _extract(url)
        except Exception as e:
            print(f"[enterevents] detail failed {url}: {e}")
            continue

        venue = (ev.get("venue") or "").lower()
        if not any(k in venue for k in TIRANA_KEYWORDS):
            continue  # keep only Tirana events

        title = ev.get("title")
        if not title:
            continue

        # Date + start time may be in two fields; join for a richer parse.
        raw = " ".join(x for x in (ev.get("date"), ev.get("start_time")) if x)
        start = parse_date(raw)
        if not start:
            print(f"[enterevents] unparseable date {raw!r} for {title!r} — skipped")
            continue

        out.append(Event(
            source="enterevents",
            external_id=url_id(url),
            title=title,
            start_date=start,
            municipality="Tiranë",   # filtered to Tirana venues above
            image_url=ev.get("image"),
            source_url=url,
        ))
    return out