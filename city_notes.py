"""
city_notes.py — Live data for the Home "Smart Local Notes" cards:

  weather   → Open-Meteo (free, no API key)
  exchange  → Iliria'98 homepage rate table (no public API; one light HTML
              request per refresh, attributed in the UI)
  flights   → TIA departures/arrivals pages. They are client-side rendered,
              so we reuse the in-container Playwright/Chromium already used
              by ingestion/kookooli.py. The fetcher is isolated in
              _fetch_flights() so it can be swapped for the site's XHR JSON
              endpoint later (open DevTools → Network on the departures page
              to find it) — that would drop the browser overhead entirely.

Everything is refreshed by an APScheduler job registered in main.py and kept
in an in-process cache; GET /city/notes only ever READS the cache, so a slow
or broken upstream can never block a request. On refresh failure the previous
good value is kept (stale-while-error) — each section carries its own
fetched_at so the frontend can show staleness if it wants to.

Verify standalone (one command, prints what the endpoint would serve):
    docker exec -it tirantips-api python city_notes.py
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

TIRANA_LAT, TIRANA_LON = 41.3275, 19.8187
_UA = {"User-Agent": "Mozilla/5.0 (TiranaTips city guide)"}

# Open-Meteo WMO weather codes → short labels
_WMO = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog",
    51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
    61: "Rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Snow", 73: "Snow", 75: "Heavy snow", 77: "Snow",
    80: "Showers", 81: "Showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}

# Currencies worth showing on a city-guide card.
_WANTED_CCY = ("EUR", "USD", "GBP", "CHF")

# In-process cache. Sections are independent: one failing source never
# blanks the others. None = never fetched successfully.
_cache: dict = {
    "weather": None,
    "exchange": None,
    "departures": None,
    "arrivals": None,
    "emergency": {
        "numbers": [
            {"number": "112", "label": "General emergency (EU standard)"},
            {"number": "129", "label": "Police"},
            {"number": "127", "label": "Ambulance"},
            {"number": "128", "label": "Fire brigade"},
        ],
        "note": "Toll-free from any phone, including roaming.",
    },
}


def get_notes() -> dict:
    """Read-only snapshot served by GET /city/notes."""
    return _cache


# ---------------------------------------------------------------------------
# Weather — Open-Meteo current conditions
# ---------------------------------------------------------------------------

def _fetch_weather() -> dict:
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": TIRANA_LAT,
            "longitude": TIRANA_LON,
            "current": "temperature_2m,weather_code",
            "hourly": "precipitation_probability,weather_code,temperature_2m",
            "forecast_days": 1,
            "timezone": "Europe/Tirane",
        },
        timeout=10,
    )
    r.raise_for_status()

    data = r.json()
    cur = data["current"]
    hourly = data.get("hourly", {})

    times = hourly.get("time", [])
    rain_probs = hourly.get("precipitation_probability", [])
    hourly_codes = hourly.get("weather_code", [])
    hourly_temps = hourly.get("temperature_2m", [])

    # Open-Meteo returns hourly times in Europe/Tirane because timezone is set.
    # Make now_local naive too, so comparison works safely.
    from zoneinfo import ZoneInfo

    now_local = datetime.now(ZoneInfo("Europe/Tirane")).replace(tzinfo=None)

    next_rain = None
    max_rain_probability = None

    rain_codes = {
        51, 53, 55,      # Drizzle
        61, 63, 65,      # Rain
        80, 81, 82,      # Showers
        95, 96, 99,      # Thunderstorm
    }

    for i, time_str in enumerate(times):
        try:
            hour_time = datetime.fromisoformat(time_str)
        except ValueError:
            continue

        if hour_time < now_local:
            continue

        probability = rain_probs[i] if i < len(rain_probs) else None
        code = hourly_codes[i] if i < len(hourly_codes) else None
        temp = hourly_temps[i] if i < len(hourly_temps) else None

        if probability is not None:
            max_rain_probability = (
                probability
                if max_rain_probability is None
                else max(max_rain_probability, probability)
            )

        is_rain_code = code in rain_codes if code is not None else False

        if (probability is not None and probability >= 45) or is_rain_code:
            next_rain = {
                "time": hour_time.strftime("%H:%M"),
                "probability": probability,
                "temp_c": round(temp) if temp is not None else None,
                "label": _WMO.get(int(code), "Rain") if code is not None else "Rain",
            }
            break

    current_label = _WMO.get(int(cur["weather_code"]), "—")
    current_temp = round(cur["temperature_2m"])

    if next_rain:
        alert_title = f"{next_rain['label']} possible around {next_rain['time']}"
        alert_text = (
            f"{next_rain['probability']}% chance of rain. Best to carry an umbrella."
            if next_rain.get("probability") is not None
            else "Best to carry an umbrella."
        )
    else:
        alert_title = f"{current_label} in Tirana"
        alert_text = f"Currently around {current_temp}°C."

    return {
        "temp_c": current_temp,
        "label": current_label,
        "alert_title": alert_title,
        "alert_text": alert_text,
        "next_rain": next_rain,
        "max_rain_probability": max_rain_probability,
        "fetched_at": datetime.utcnow().isoformat(),
    }
# ---------------------------------------------------------------------------
# Exchange rates — Iliria'98 homepage table
# ---------------------------------------------------------------------------
# The page renders each currency as a flag image (dist/img/flags/EUR.png)
# followed by buy/sell cells. Anchoring on the flag filename is the most
# stable selector the page offers; the surrounding markup may change, the
# flag-per-currency pattern is core to the layout.

def _fetch_exchange() -> dict:
    r = requests.get("https://iliria98.com/", timeout=15, headers=_UA)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    rates: dict[str, dict] = {}
    for img in soup.select('img[src*="flags/"]'):
        code = img["src"].rsplit("/", 1)[-1].split(".")[0].upper()
        if code not in _WANTED_CCY or code in rates:
            continue
        row = img.find_parent("tr") or img.parent
        nums = re.findall(r"\d+(?:\.\d+)?", row.get_text(" ", strip=True)) if row else []
        if len(nums) >= 2:
            rates[code] = {"buy": float(nums[0]), "sell": float(nums[1])}

    if not rates:
        # Fallback: flags may be lazy-loaded (data-src) or markup changed.
        # The visible text still reads "EUR 94.7 95.5" per currency — match
        # that pattern directly, whitelisted codes only, first hit per code.
        text = soup.get_text(" ", strip=True)
        for code in _WANTED_CCY:
            m = re.search(
                rf"\b{code}\b\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)", text)
            if m:
                rates[code] = {
                    "buy":  float(m.group(1).replace(",", ".")),
                    "sell": float(m.group(2).replace(",", ".")),
                }

    if not rates:
        # Surface WHAT came back, not just that parsing failed — a bot
        # challenge page and a layout change need different fixes.
        snippet = soup.get_text(" ", strip=True)[:200]
        raise ValueError(
            f"no currency rows parsed (status {r.status_code}, "
            f"{len(r.text)} bytes). Page starts: {snippet!r}")

    # "Përditësuar: 12:33:00 - 12.06.2026" — the site's own update stamp.
    m = re.search(r"(\d{2}:\d{2}):\d{2}\s*-\s*(\d{2}\.\d{2}\.\d{4})",
                  soup.get_text(" ", strip=True))
    return {
        "rates": rates,
        "source": "Iliria'98",
        "source_updated": f"{m.group(1)} {m.group(2)}" if m else None,
        "fetched_at": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# TIA flights — Playwright-rendered departures/arrivals
# ---------------------------------------------------------------------------

_TIME_RE   = re.compile(r"^\d{1,2}:\d{2}$")
# Flight numbers: "W9 5460", "FR 8479", "XQ 215", charter codes "XHA2198".
_FLIGHT_RE = re.compile(r"^[A-Z0-9]{2,3}\s?\d{1,4}[A-Z]?$")
# Already-flown flights — the page lists the whole day, the card wants "next".
_PAST_STATUSES = {"departed", "landed"}
# Minutes of grace behind "now" — a flight a few minutes past may still be
# boarding/closing, but anything older reads as stale on a "next" card.
_GRACE_MIN = 15


def _parse_rows(rows: list[list[str]], limit: int = 6,
                now: datetime | None = None) -> list[dict]:
    """Page columns are nominally Time, Date, Destination/Origin, Airline,
    Flight no., Status — but the live DOM has quirks:
      * each flight is followed by a ghost row carrying only the time
        (skipped via the < 3 cells check),
      * charter rows have no airline cell, shifting everything left — so the
        flight-number cell is detected by SHAPE, not position, and
      * stale rows linger with empty/'Gate closed' status long after the
        flight flew, so 'next' is decided by TIME (Tirana clock, with grace),
        not just status. Delayed flights get NO exemption: the page only
        shows the original scheduled time, so a long-past 'Delayed' row reads
        as stale data on a 'next flights' card. If nothing is upcoming (late
        night, tomorrow's rows not yet listed), fall back to whatever remains
        rather than showing an empty card."""
    from zoneinfo import ZoneInfo
    now = now or datetime.now(ZoneInfo("Europe/Tirane"))
    cutoff = now.hour * 60 + now.minute - _GRACE_MIN

    upcoming, leftover = [], []
    for cells in rows:
        cells = [c.strip() for c in cells if c.strip()]
        if len(cells) < 3 or not _TIME_RE.match(cells[0]):
            continue
        rec = {"time": cells[0], "city": cells[2],
               "airline": "", "flight": "", "status": ""}
        rest = cells[3:]
        idx = next((i for i, c in enumerate(rest) if _FLIGHT_RE.match(c)), None)
        if idx is not None:
            rec["airline"] = " ".join(rest[:idx])
            rec["flight"]  = rest[idx]
            rec["status"]  = " ".join(rest[idx + 1:])
        elif rest:
            rec["airline"] = rest[0]
            rec["status"]  = " ".join(rest[1:])
        if rec["status"].lower() in _PAST_STATUSES:
            continue
        h, m = rec["time"].split(":")
        if int(h) * 60 + int(m) >= cutoff:
            upcoming.append(rec)
        else:
            leftover.append(rec)

    return (upcoming or leftover)[:limit]


async def _fetch_flights(kind: str, limit: int = 6) -> dict:
    """kind: 'departures' | 'arrivals'.

    NOTE: swap-in point — if the page's XHR JSON endpoint is identified via
    browser DevTools, replace this whole body with a requests.get() of that
    endpoint and keep the return shape identical.
    """
    from playwright.async_api import async_playwright

    url = f"https://www.tirana-airport.com/en/flights/{kind}"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(user_agent=_UA["User-Agent"])
            await page.goto(url, timeout=45_000, wait_until="networkidle")

            # Primary: a real <table>. Fallback: list-item rows. Both reduced
            # to "list of cell texts per row" for the same parser.
            rows = await page.evaluate(
                """() => {
                    const trs = [...document.querySelectorAll('tbody tr, table tr')];
                    if (trs.length > 1)
                        return trs.map(tr =>
                            [...tr.querySelectorAll('td,th')].map(c => c.innerText));
                    return [...document.querySelectorAll('li')]
                        .map(li => li.innerText.split('\\n'));
                }"""
            )
        finally:
            await browser.close()

    flights = _parse_rows(rows, limit=limit)
    if not flights:
        raise ValueError(f"no {kind} rows parsed — check selectors against live DOM")
    return {"flights": flights, "fetched_at": datetime.utcnow().isoformat()}


# ---------------------------------------------------------------------------
# Refresh — called by APScheduler (coroutine job) from main.py
# ---------------------------------------------------------------------------

async def refresh() -> None:
    for key, fn in (("weather", _fetch_weather), ("exchange", _fetch_exchange)):
        try:
            # requests is blocking — keep it off the event loop.
            _cache[key] = await asyncio.to_thread(fn)
        except Exception as exc:
            print(f"[CityNotes] {key} refresh failed: {exc}")

    for kind in ("departures", "arrivals"):
        try:
            _cache[kind] = await _fetch_flights(kind)
        except Exception as exc:
            print(f"[CityNotes] {kind} refresh failed: {exc}")


if __name__ == "__main__":
    import json
    asyncio.run(refresh())
    print(json.dumps(get_notes(), indent=2, ensure_ascii=False))