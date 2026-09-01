"""Set the Wiki.js homepage to a simple, centered HTML welcome screen.

Run with:
    set -a; . ./.env; set +a
    python3 seed_wiki_home.py
"""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


WIKI_URL = os.environ.get("WIKI_URL")
WIKI_TOKEN = os.environ.get("WIKI_TOKEN")

CONTENT = """<div style="min-height: 70vh; display: flex; align-items: center; justify-content: center; padding: 48px 24px; box-sizing: border-box; background: linear-gradient(135deg, #f7fafc 0%, #e9f4f4 100%);">
  <main style="max-width: 850px; text-align: center; color: #173b3f; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
    <p style="margin: 0 0 20px; color: #588589; font-size: 13px; font-weight: 700; letter-spacing: 0.16em;">WELCOME TO WIKI</p>
    <h1 style="margin: 0; font-size: clamp(2.4rem, 6vw, 4.8rem); line-height: 1.12; font-weight: 700; letter-spacing: -0.04em;">Hi, I’m Wiki, your digital library and assistant, all in one.</h1>
  </main>
</div>"""


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
    home = next((page for page in pages if page["path"] == "home" and page["locale"] == "en"), None)
    if home is None:
        raise RuntimeError("The English Wiki.js homepage (/home) does not exist.")

    mutation = """
      mutation UpdatePage($id: Int!, $content: String!, $description: String!,
        $title: String!, $tags: [String]!) {
        pages {
          update(id: $id, content: $content, description: $description,
            title: $title, tags: $tags) {
            responseResult { succeeded message }
            page { path title }
          }
        }
      }
    """
    result = graphql(
        mutation,
        {
            "id": home["id"],
            "content": CONTENT,
            "description": "TiranaTips digital library and assistant.",
            "title": "Wiki",
            "tags": ["home", "tirana", "tiranatips"],
        },
    )["pages"]["update"]
    response = result["responseResult"]
    if not response["succeeded"]:
        raise RuntimeError(f"Homepage update failed: {response['message']}")
    print(f"Updated: /{result['page']['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
