import os
import requests
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()

WIKI_URL = os.getenv("WIKI_URL")
WIKI_TOKEN = os.getenv("WIKI_TOKEN")

def fetch_wiki_pages():
    query = """
    {
      pages {
        list (orderBy: TITLE) {
          id
          path
          title
        }
      }
    }
    """
    headers = {"Authorization": f"Bearer {WIKI_TOKEN}"}
    response = requests.post(WIKI_URL, json={'query': query}, headers=headers)

    if response.status_code == 200:
        return response.json()['data']['pages']['list']
    else:
        print(f"Gabim gjatë lidhjes: {response.status_code}")
        return []

def get_page_content(page_id):
    query = """
    query ($id: Int!) {
      pages {
        single (id: $id) {
          content
          description
        }
      }
    }
    """
    headers = {"Authorization": f"Bearer {WIKI_TOKEN}"}
    response = requests.post(WIKI_URL, json={'query': query, 'variables': {"id": page_id}}, headers=headers)

    if response.status_code == 200:
        return response.json()['data']['pages']['single']['content']
    return ""

if __name__ == "__main__":
    pages = fetch_wiki_pages()
    print(f"U gjetën {len(pages)} faqe në Wiki.js.")

    for page in pages:
        if "banka-shqiperise" in page['path'] or "sektori-financiar" in page['path']:
            content = get_page_content(page['id'])
            print(f"\n--- Duke procesuar: {page['title']} ---")
            print(f"Gjatësia e tekstit: {len(content)} karaktere.")