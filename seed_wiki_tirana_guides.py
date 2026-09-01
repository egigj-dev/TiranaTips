"""Create or refresh practical Tirana guide pages in Wiki.js.

Run with:
    set -a; . ./.env; set +a
    python3 seed_wiki_tirana_guides.py

The script reads WIKI_URL and WIKI_TOKEN from the environment. It only
creates or updates the /tirana-guide pages declared below.
"""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


WIKI_URL = os.environ.get("WIKI_URL")
WIKI_TOKEN = os.environ.get("WIKI_TOKEN")


PAGES = [
    {
        "path": "tirana-guide",
        "title": "Tirana guide",
        "description": "A practical starting point for Tirana's history, food, neighbourhoods, transport and attractions.",
        "tags": ["tirana", "travel-guide", "tourism"],
        "content": """# Tirana guide

Tirana is compact, energetic and best explored in layers: its historic centre, the neighbourhoods around it, everyday food culture, and the green hills at the city's edge. Use this guide as a starting point, then check the live links below for information that can change, such as opening hours, routes and prices.

## Explore Tirana

| Topic | What this page covers |
| --- | --- |
| [History](/tirana-guide/history) | From the older settlements around Tirana to its role as Albania's capital |
| [Cuisine](/tirana-guide/cuisine) | Albanian dishes to try and how to eat well in the city |
| [Neighbourhoods](/tirana-guide/neighbourhoods) | The character of the centre, Blloku, Pazari i Ri and other useful areas |
| [Transportation](/tirana-guide/transportation) | Walking, city buses, taxis, airport connections and Dajti travel planning |
| [Touristic attractions](/tirana-guide/attractions) | A practical shortlist of cultural sights, museums, parks and day trips |

## Good first steps

- Begin at **Skanderbeg Square** to orient yourself around the historic centre.
- Pick one nearby district to explore on foot instead of trying to cross the city repeatedly in traffic.
- Keep the official city map and bus map handy if using public transport.
- Confirm same-day hours, ticket conditions and accessibility directly with each attraction.

## Official planning sources

- [Tirana Municipality tourism portal](https://tirana.al/en/)
- [Tirana city and bus map (PDF)](https://tirana.al/uploads/2024/8/20240816104642_harta_tiranes.pdf)
- [Official Albanian Tourism website](https://akt.gov.al/en/)
""",
    },
    {
        "path": "tirana-guide/history",
        "title": "History of Tirana",
        "description": "A concise guide to the historical layers that shaped Tirana.",
        "tags": ["tirana", "history", "heritage"],
        "content": """# History of Tirana

Tirana's story reaches beyond the modern city. Archaeological sites in the wider area, including Pëllumbas Cave and hilltop fortifications, show much older settlement. The city visitors recognise today developed in the Ottoman period, then changed rapidly after Tirana became Albania's capital in the twentieth century.

## A short timeline

- **Earlier settlement:** the municipality records prehistoric and ancient evidence in the wider Tirana area, including Pëllumbas Cave and the Tujan fortification.
- **Ottoman-era town:** modern Tirana is traditionally associated with Sulejman Pashë Bargjini, who established a mosque, bakery and hammam. The remaining Et'hem Bey Mosque and Clock Tower give the historic centre much of its character.
- **Capital city:** Tirana was proclaimed Albania's capital in 1925. New boulevards, institutions and public buildings reshaped the city during the interwar period.
- **Twentieth century to today:** Italian-period planning, the communist era, and post-1990 change all remain visible in the city's streets, institutions and neighbourhoods.

## See the history on foot

Start around **Skanderbeg Square**, then visit the Et'hem Bey Mosque and Clock Tower. Continue towards the **Tanners' Bridge** and **Pazari i Ri** for an older commercial and residential quarter. The former restricted **Blloku** district offers a contrasting view of the communist period and today's city life.

## Reading the city carefully

Historical labels can simplify a complicated past. Treat monuments and museums as starting points, and use their current exhibitions and interpretation for more detail. Observe rules at religious sites and ask before photographing people during worship.

## Trusted sources

- [Tirana Municipality — tangible cultural heritage](https://tirana.al/en/page/tangible-culture-heritage)
- [Et'hem Bey Mosque](https://tirana.al/en/points-of-interest/attractions-and-sights/the-haxhi-ethem-bey-mosque)
- [Clock Tower](https://tirana.al/en/points-of-interest/attractions-and-sights/the-clock-tower)
- [Tanners' Bridge](https://tirana.al/en/points-of-interest/attractions-and-sights/the-tanners-bridge)
""",
    },
    {
        "path": "tirana-guide/cuisine",
        "title": "Tirana cuisine",
        "description": "What to eat in Tirana, from market snacks to Albanian classics.",
        "tags": ["tirana", "food", "albanian-cuisine"],
        "content": """# Tirana cuisine

Tirana is a good place to try Albanian cooking alongside the city's cafés, bakeries and contemporary restaurants. Menus vary widely, so the most useful approach is to seek a place whose style matches the meal you want: a neighbourhood grill, a traditional restaurant, a bakery, a market-side café or a modern kitchen.

## Albanian dishes to look for

| Dish | What to expect |
| --- | --- |
| **Byrek** | A baked savoury pastry, commonly filled with cheese, spinach, meat or seasonal vegetables. |
| **Fërgesë** | A rich dish associated with central Albania, generally built around peppers, tomatoes, cheese and sometimes meat. |
| **Tavë kosi** | An oven-baked meat-and-yogurt casserole; recipes and proteins vary. |
| **Qofte** | Grilled or fried meatballs, often served with bread, salad and pickles. |
| **Speca me gjizë** | Peppers with fresh cheese, often a lighter vegetarian-friendly choice. |
| **Baklava** | Layered sweet pastry, especially common around celebrations. |

## How to eat well

- Try **byrek** for a quick breakfast or snack; ask what fillings are fresh that day.
- Visit **Pazari i Ri** in the morning for its market atmosphere, then return later for cafés and restaurants.
- In a traditional restaurant, sharing several dishes is often the easiest way to try more than one flavour.
- Tell staff about allergies or dietary requirements clearly. Vegetarian choices are available, but ingredients such as meat stock, dairy and eggs can be used unexpectedly.
- Check the menu and ask about portions and the bill before ordering if you are unsure.

## Coffee, drinks and timing

Coffee is central to everyday life in Tirana; a short coffee break is as much a social pause as a drink. For water, use sealed bottled water if that is your preference, and follow the venue's current payment options rather than assuming cards are accepted everywhere.

## Trusted sources

- [Official Albanian Tourism — culinary guide](https://akt.gov.al/en/culinary/)
- [Official Albanian Tourism — fërgesë](https://akt.gov.al/en/culinary/brush-2/)
- [Tirana Municipality — New Bazaar](https://tirana.al/en/points-of-interest/attractions-and-sights/the-new-bazaar)
""",
    },
    {
        "path": "tirana-guide/neighbourhoods",
        "title": "Tirana neighbourhoods",
        "description": "A visitor-friendly orientation to Tirana's central neighbourhoods and districts.",
        "tags": ["tirana", "neighbourhoods", "travel-guide"],
        "content": """# Tirana neighbourhoods

Tirana does not need to be understood as a checklist of districts. The central areas are close enough to combine on foot, but each has a different rhythm. Choose an area based on what you want to do, then allow time to wander side streets and stop for a coffee.

## Areas visitors often use

| Area | Character and useful highlights |
| --- | --- |
| **Centre / Skanderbeg Square** | Best first orientation: major landmarks, museums and connections are close by. |
| **Pazari i Ri (New Bazaar)** | Market area east of the centre, useful for food, casual dining and an older-quarter feel. |
| **Blloku (Ish-Blloku)** | Once a restricted area for communist leadership; now known for cafés, restaurants, boutiques and nightlife. |
| **Tirana e Re / around Wilson Square** | A lively residential-commercial area with many everyday cafés and restaurants. |
| **The Grand Park and Artificial Lake** | A green escape south of the centre, suited to walks, running and a slower afternoon. |

## Choosing where to stay or spend time

- Stay near the centre for easy walking access to museums and sights.
- Choose Blloku or Tirana e Re if restaurants, bars and evening activity matter more.
- Choose the park side for a calmer base, while remembering that the centre is not immediately outside every hotel door.
- Use a map for the exact address: neighbourhood names are informal in everyday use and listings may describe nearby landmarks rather than a precise district.

## A respectful way to explore

These are lived-in parts of the city, not just visitor zones. Keep noise low in residential streets late at night, use marked crossings where possible, and ask before photographing people or private homes.

## Trusted sources

- [Tirana Municipality — Blloku and the former Villa of Enver Hoxha](https://tirana.al/en/points-of-interest/historical-itinerary/block-area)
- [Tirana Municipality — New Bazaar](https://tirana.al/en/points-of-interest/attractions-and-sights/the-new-bazaar)
- [Tirana city map (PDF)](https://tirana.al/uploads/2024/8/20240816104642_harta_tiranes.pdf)
""",
    },
    {
        "path": "tirana-guide/transportation",
        "title": "Transportation in Tirana",
        "description": "Practical guidance for getting around Tirana by foot, bus, taxi and airport connection.",
        "tags": ["tirana", "transportation", "travel-guide"],
        "content": """# Transportation in Tirana

The central sights in Tirana are often easiest to reach on foot, while city buses help with longer cross-town trips. Traffic can make travel times variable, so leave a margin when heading to the airport, a timed ticket or an intercity departure.

## Getting around the city

### On foot

Skanderbeg Square, the Clock Tower, Pazari i Ri, Blloku and the Pyramid area can be connected by walking. Pavement quality, crossings and traffic vary, so wear comfortable shoes and take care when crossing busy streets.

### City buses

Tirana has an urban bus network. Use the municipality's current bus map to identify the route and direction, and verify stops, frequencies, ticket arrangements and service changes locally before travel. Do not rely on an old screenshot or a third-party timetable for a time-critical journey.

### Taxi and ride services

For a taxi, use a licensed, clearly marked vehicle or arrange one through your accommodation or a reputable operator. Agree the fare or confirm that the meter is in use before departing. Keep an address or map pin ready, particularly for places with similar names.

## Airport and onward travel

Tirana International Airport is outside the central area. Airport buses, taxis and pre-arranged transfers are common options. Check your airline, airport or accommodation for current departure points and schedules, and build in extra time for traffic.

For travel beyond Tirana, ask the operator or terminal directly about the current departure point, ticketing and luggage rules; regional services can change.

## Getting to Dajti

The Dajti Ekspres cable car is an outing from the city rather than part of the urban network. Its official guidance describes public-bus and taxi options to the lower station. Check the operator's live opening times, weather notices, ticket conditions and accessibility information before you set out.

## Trusted sources

- [Tirana Municipality — bus lines](https://tirana.al/en/points-of-interest/bus-lines)
- [Tirana urban bus map (PDF)](https://urbani.tirana.al/Harta%20e%20Linjave%20t%C3%AB%20Urbanit%2C%20Tiran%C3%AB.pdf)
- [Dajti Ekspres — getting there](https://dajtiekspres.com/getting-here/)
- [Dajti Ekspres — tickets and opening times](https://dajtiekspres.com/rates-and-opening-hours/)
""",
    },
    {
        "path": "tirana-guide/attractions",
        "title": "Touristic attractions in Tirana",
        "description": "A practical shortlist of Tirana's historic sights, museums, parks and nearby escapes.",
        "tags": ["tirana", "attractions", "tourism"],
        "content": """# Touristic attractions in Tirana

For a first visit, concentrate on a compact core rather than racing between every landmark. Pair a few historic places with a museum, a park walk or a food stop, then check each venue's current hours and ticketing before leaving.

## Historic centre and culture

| Attraction | Why go |
| --- | --- |
| **Skanderbeg Square** | The natural starting point for the city centre and several major institutions. |
| **Et'hem Bey Mosque and Clock Tower** | A landmark Ottoman-era ensemble beside the square. Follow current visitor and worship rules. |
| **National Historical Museum** | A broad introduction to Albanian history through museum collections and exhibitions. |
| **Tanners' Bridge** | An eighteenth-century Ottoman stone footbridge near the old market area. |
| **Pazari i Ri** | A market-and-dining area with a strong local atmosphere, particularly in the morning and early evening. |

## Modern Tirana and green space

- **Blloku:** good for seeing the contrast between the former communist restricted district and today's cafés, restaurants and nightlife.
- **The Grand Park and Artificial Lake:** a useful break from the centre for walking and outdoor time.
- **Dajti Mountain:** a larger half-day outing. The Dajti Ekspres cable car gives access to mountain views and activities; always check its latest operating information before travelling.

## Simple one-day route

Begin in Skanderbeg Square, see the mosque and Clock Tower, then walk toward Pazari i Ri and the Tanners' Bridge. In the afternoon, choose a museum or Blloku, then finish with the Grand Park if time and weather allow.

## Before you go

- Confirm opening hours, admission rules and accessibility on the venue's official site or by direct contact.
- Dress respectfully for religious spaces and be prepared for restricted photography.
- For Dajti, check weather and the cable car's operating status on the day.

## Trusted sources

- [Tirana Municipality — attractions and sights](https://tirana.al/en/points-of-interest/attractions-and-sights)
- [National Historical Museum](https://tirana.al/en/points-of-interest/museums/national-historical-museum)
- [Clock Tower](https://tirana.al/en/points-of-interest/attractions-and-sights/the-clock-tower)
- [Et'hem Bey Mosque](https://tirana.al/en/points-of-interest/attractions-and-sights/the-haxhi-ethem-bey-mosque)
- [Dajti Ekspres](https://dajtiekspres.com/home/)
""",
    },
]


def graphql(query: str, variables: dict | None = None) -> dict:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    request = Request(
        WIKI_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {WIKI_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
    except (HTTPError, URLError) as error:
        raise RuntimeError(f"Wiki.js request failed: {error}") from error

    if data.get("errors"):
        raise RuntimeError(f"Wiki.js GraphQL error: {data['errors']}")
    return data["data"]


def main() -> int:
    if not WIKI_URL or not WIKI_TOKEN:
        print("WIKI_URL and WIKI_TOKEN must be set.", file=sys.stderr)
        return 1

    pages = graphql("{ pages { list { id path locale } } }")["pages"]["list"]
    existing = {(page["path"], page["locale"]): page["id"] for page in pages}

    create_mutation = """
      mutation CreatePage($content: String!, $description: String!, $editor: String!,
        $isPublished: Boolean!, $isPrivate: Boolean!, $locale: String!, $path: String!,
        $tags: [String]!, $title: String!) {
        pages {
          create(content: $content, description: $description, editor: $editor,
            isPublished: $isPublished, isPrivate: $isPrivate, locale: $locale,
            path: $path, tags: $tags, title: $title) {
            responseResult { succeeded message }
            page { id path title }
          }
        }
      }
    """
    update_mutation = """
      mutation UpdatePage($id: Int!, $content: String!, $description: String!,
        $title: String!, $tags: [String]!) {
        pages {
          update(id: $id, content: $content, description: $description,
            title: $title, tags: $tags) {
            responseResult { succeeded message }
            page { id path title }
          }
        }
      }
    """

    for item in PAGES:
        values = {
            "content": item["content"],
            "description": item["description"],
            "title": item["title"],
            "tags": item["tags"],
        }
        page_id = existing.get((item["path"], "en"))
        if page_id is None:
            values.update(
                {
                    "editor": "markdown",
                    "isPublished": True,
                    "isPrivate": False,
                    "locale": "en",
                    "path": item["path"],
                }
            )
            result = graphql(create_mutation, values)["pages"]["create"]
            action = "Created"
        else:
            values["id"] = page_id
            result = graphql(update_mutation, values)["pages"]["update"]
            action = "Updated"

        response = result["responseResult"]
        if not response["succeeded"]:
            raise RuntimeError(f"{action} {item['path']} failed: {response['message']}")
        print(f"{action}: /{result['page']['path']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
