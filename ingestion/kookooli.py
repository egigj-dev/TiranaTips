"""
kookooli.py — https://kookooli.com/event/  (JS-rendered, Playwright).

Listing uses infinite scroll, then each event has a detail page. This is the
heaviest source: a real Chromium instance + a page load per event. Date is
buried in free text and extracted by regex, then parsed.
"""
from __future__ import annotations

import asyncio
import re

from playwright.async_api import async_playwright

from ingestion.base import Event, url_id, parse_date

BASE = "https://kookooli.com"
_DATE_RE = re.compile(r"\d{1,2}\s+\w+\s+\d{4}")


async def _all_event_links(page) -> list[str]:
    await page.goto(f"{BASE}/event/", wait_until="networkidle")
    prev = 0
    while True:
        h = await page.evaluate("document.body.scrollHeight")
        if h == prev:
            break
        prev = h
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)

    hrefs = await page.eval_on_selector_all(
        'a[href*="/event/"]', "els => els.map(e => e.href)"
    )
    return sorted({
        h.split("?")[0] for h in hrefs if re.search(r"/event/[^/]+/?$", h)
    })


async def _scrape_event(page, url: str) -> dict:
    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(1000)

    data = {"url": url, "title": "", "category": "",
            "date_raw": "", "description": "", "image": ""}

    title = await page.locator("h1").first.text_content()
    data["title"] = title.strip() if title else ""
    data["image"] = await page.locator("img").first.get_attribute("src")

    paras = await page.locator("main p").all_text_contents()
    data["description"] = "\n\n".join(p.strip() for p in paras if p.strip())

    lines = [l.strip() for l in (await page.locator("main").inner_text()).splitlines() if l.strip()]
    if len(lines) > 1:
        data["category"] = lines[1]
    for line in lines:
        if _DATE_RE.search(line):
            data["date_raw"] = line
            break
    return data


async def _scrape() -> list[Event]:
    out: list[Event] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        listing = await browser.new_page()
        links = await _all_event_links(listing)
        print(f"[kookooli] found {len(links)} event links")

        page = await browser.new_page()
        for i, url in enumerate(links, 1):
            try:
                ev = await _scrape_event(page, url)
            except Exception as e:
                print(f"[kookooli] failed {url}: {e}")
                continue

            title = ev["title"]
            if not title:
                continue
            # Pull the date substring out of the matched line before parsing.
            m = _DATE_RE.search(ev["date_raw"])
            start = parse_date(m.group(0)) if m else None
            if not start:
                print(f"[kookooli] unparseable date {ev['date_raw']!r} for {title!r} — skipped")
                continue

            out.append(Event(
                source="kookooli",
                external_id=url_id(url),
                title=title,
                start_date=start,
                category=ev["category"] or None,
                description=ev["description"] or None,
                image_url=ev["image"],
                source_url=url,
            ))
        await browser.close()
    return out


def fetch() -> list[Event]:
    """Sync wrapper so run.py can call every source uniformly."""
    return asyncio.run(_scrape())