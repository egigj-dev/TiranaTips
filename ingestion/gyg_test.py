import asyncio
from playwright.async_api import async_playwright

async def scrape_tirana_events(date):
    """
    Scrapes events from GetYourGuide for Tirana on a specific date.
    Date format: YYYY-MM-DD
    """
    url = f"https://www.getyourguide.com/tirana-l2468/?date_from={date}&date_to={date}&adults=1"
    async with async_playwright() as p:
        # Using a common browser profile and user agent to minimize bot detection
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print(f"Navigating to: {url}")
        await page.goto(url, wait_until="networkidle")

        print("status/title:", await page.title())
        await page.screenshot(path="ingestion/gyg.png", full_page=True)

        
        # Wait for activity cards to load
        # Based on observation, activity cards are 'a' tags with role='link' containing specific classes
        try:
            await page.wait_for_selector("a[role='link']", timeout=10000)
        except:
            print("No activities found or page failed to load correctly.")
            await browser.close()
            return []

        activities = []
        # Selection logic based on the observed DOM structure
        # Activity containers often have classes like 'vertical-layout' or data attributes
        cards = await page.query_selector_all("a[role='link']")
        
        for card in cards:
            # Skip links that aren't activity cards (e.g., header/footer)
            # True activity cards usually contain price/rating info
            text_content = await card.inner_text()
            if "From" not in text_content:
                continue

            # Extract basic info from the text block
            lines = [line.strip() for line in text_content.split('\\n') if line.strip()]
            
            # Heuristic-based extraction from lines
            # Example: [ 'Top pick', 'Tirana', 'Title...', '16 hours', '4.5', '(302)', 'From $60 $56' ]
            activity = {
                "url": await card.get_attribute("href"),
                "raw_text": text_content
            }
            
            # Simple mapping (refined based on observed order)
            if lines:
                # GetYourGuide cards often start with a badge like 'Top pick' or the location
                activity["title"] = next((l for l in lines if len(l) > 20), "Unknown Title")
                activity["price"] = lines[-1] if "From" in lines[-1] or "$" in lines[-1] else "Unknown"

            activities.append(activity)

        await browser.close()
        return activities

if __name__ == "__main__":
    # Example usage for 2026-06-22
    TARGET_DATE = "2026-06-22"
    results = asyncio.run(scrape_tirana_events(TARGET_DATE))
    
    print(f"\nFound {len(results)} activities for {TARGET_DATE}:\n")
    for idx, item in enumerate(results, 1):
        print(f"{idx}. {item.get('title')}")
        print(f"   Price: {item.get('price')}")
        print(f"   URL: https://www.getyourguide.com{item.get('url')}")
        print("-" * 30)
