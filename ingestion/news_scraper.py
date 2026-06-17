"""
news_scraper.py — Scrape news headlines from 3 Albanian English-language sources.
Each source's fetch function returns list[dict] with keys: source, title, url, image_url.

Sources:
  - Tirana Times      → www.tiranatimes.com
  - Exit.al           → exit.al/en/category/analysis
  - Albanian Daily News → albaniandailynews.com/category/events

The /city/news endpoint caches results in-process (stale-while-error).
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_UA = "Mozilla/5.0 (TiranaTips news bot; +https://tiranatips.com)"
_HEADERS = {"User-Agent": _UA}
_TIMEOUT = 20

# ---------------------------------------------------------------------------
# 1. Tirana Times — WordPress theme (Newspaper/TagDiv)
#    Layout: article > figure > a > img  +  h2.entry-title > a
# ---------------------------------------------------------------------------

TT_URL = "https://www.tiranatimes.com/"


def _fetch_tiranatimes() -> list[dict]:
    r = requests.get(TT_URL, headers=_HEADERS, timeout=_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out: list[dict] = []
    for article in soup.select("article") or []:
        # Title + URL
        title_el = article.select_one(".entry-title a, h2 a, h3 a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        url   = title_el.get("href", "")
        if not title or not url:
            continue

        # Image — <figure> <a> <img> or <figure> <img>
        img = article.select_one("figure img, .td-module-thumb img, img")
        image_url = ""
        if img:
            src = (
                img.get("data-src")       # lazy-loaded
                or img.get("data-lazy-src")
                or img.get("src")
            )
            if src:
                image_url = urljoin(TT_URL, src)

        out.append({
            "source": "tiranatimes",
            "title": title.strip(),
            "url": url.strip(),
            "image_url": image_url,
            "fetched_at": datetime.utcnow().isoformat(),
        })
    return out


# ---------------------------------------------------------------------------
# 2. Exit.al — English analysis page
#    Layout: article > figure > img  +  article h3 a (or a wrapping h3)
# ---------------------------------------------------------------------------

EXIT_URL = "https://exit.al/en/category/analysis"


def _fetch_exit() -> list[dict]:
    r = requests.get(EXIT_URL, headers=_HEADERS, timeout=_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out: list[dict] = []
    for article in soup.select("article") or []:
        # Title — the <a> typically wraps the <h3>
        title_el = article.select_one("a[href*='/en/'] h3, h3 a")
        if not title_el:
            # Try direct link with heading text
            link = article.select_one("a[href*='/en/']")
            if link:
                title = link.get_text(strip=True)
                url   = link.get("href", "")
            else:
                continue
        else:
            title = title_el.get_text(strip=True)
            url   = title_el.get("href", "") or title_el.find_parent("a").get("href", "")

        if not title or not url:
            continue

        # Ensure the URL is absolute — Exit.al returns relative paths
        if not url.startswith("http"):
            url = urljoin(EXIT_URL, url)

        # Image — figure > img
        img = article.select_one("figure img")
        image_url = ""
        if img:
            src = img.get("src", "")
            if src:
                image_url = urljoin(EXIT_URL, src)

        out.append({
            "source": "exit",
            "title": title.strip(),
            "url": url.strip(),
            "image_url": image_url,
            "fetched_at": datetime.utcnow().isoformat(),
        })
    return out


# ---------------------------------------------------------------------------
# 3. Albanian Daily News — events category
#    Layout: article > figure > a > img  +  h3 > a
# ---------------------------------------------------------------------------

ADN_URL = "https://albaniandailynews.com/category/events"


def _fetch_adn() -> list[dict]:
    r = requests.get(ADN_URL, headers=_HEADERS, timeout=_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out: list[dict] = []
    for article in soup.select("article") or []:
        # Title + URL
        title_el = article.select_one("h3 a, a[href*='/news/']")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        href  = title_el.get("href", "")
        url   = href if href.startswith("http") else urljoin(ADN_URL, href)

        if not title or not url:
            continue

        # Image — figure a img
        img = article.select_one("figure img, img[src*='/foto/']")
        image_url = ""
        if img:
            src = img.get("src", "")
            if src:
                image_url = urljoin(ADN_URL, src)

        out.append({
            "source": "adn",
            "title": title.strip(),
            "url": url.strip(),
            "image_url": image_url,
            "fetched_at": datetime.utcnow().isoformat(),
        })
    return out


# ---------------------------------------------------------------------------
# Combined fetch
# ---------------------------------------------------------------------------

FETCHERS = [
    ("tiranatimes", _fetch_tiranatimes),
    ("exit",        _fetch_exit),
    ("adn",         _fetch_adn),
]


def fetch_all() -> dict[str, list[dict]]:
    """Run all 3 scrapers, return {source: [articles]}. Errors logged per-source."""
    result: dict[str, list[dict]] = {}
    for name, fn in FETCHERS:
        try:
            items = fn()
            result[name] = items
            print(f"[NewsScraper] {name}: {len(items)} headlines")
        except Exception as e:
            print(f"[NewsScraper] {name} FAILED: {e}")
            result[name] = []
    return result


def flatten(per_source: dict[str, list[dict]], limit_per_source: int = 6) -> list[dict]:
    """Flatten per-source dict into a single list, capped per source."""
    merged: list[dict] = []
    for name in ("tiranatimes", "exit", "adn"):
        merged.extend((per_source.get(name) or [])[:limit_per_source])
    return merged


if __name__ == "__main__":
    import json
    data = fetch_all()
    flat = flatten(data)
    print(json.dumps(flat, indent=2, ensure_ascii=False))