"""tea.py — api.tv4.niv.al paginated JSON API. The structured, reliable source."""
from __future__ import annotations

import requests

from ingestion.base import Event

TEA_BASE = "https://api.tv4.niv.al/api/v1/public/content-groups/all-events"


def fetch() -> list[Event]:
    out: list[Event] = []
    page = 1
    while True:
        url = f"{TEA_BASE}?entityType=all&page={page}&limit=20"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            break

        for e in items:
            eid = e.get("id")
            title = (e.get("nameI18n") or {}).get("en") or (e.get("nameI18n") or {}).get("sq")
            start = e.get("startDate")
            if not (eid and title and start):
                continue  # drop rows missing required fields

            out.append(Event(
                source="tea",
                external_id=str(eid),
                title=title.strip(),
                start_date=start,
                description=(e.get("descriptionI18n") or {}).get("en"),
                category=((e.get("category") or {}).get("nameI18n") or {}).get("en"),
                municipality=(e.get("municipalityI18n") or {}).get("sq"),
                end_date=e.get("endDate"),
                lat=e.get("latitude"),
                lon=e.get("longitude"),
                image_url=e.get("imageUrl"),
                ticket_url=e.get("ticketLink") or None,
                source_url=f"https://tea.al/event/{eid}",  # adjust if the real URL differs
            ))
        page += 1
    return out