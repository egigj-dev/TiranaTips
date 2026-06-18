# Design Audit: Explore Page

**URL:** `/explore`  
**Component:** `Explore.jsx` + `explore.css`  
**Max-width:** 1100px (vs 1440px for Ask / For You pages)  
**Data sources:** Google Places API (text search), OSM browse (category), events table  
**States:** Empty (no search), loading, results (place cards), events mode, error

---

## Executive Summary

16 issues found. The Explore page is functionally solid — the search, browse categories, neighborhood filter, save flow, and events mode all work correctly. The design problems are around **inconsistent page width**, **information density imbalance** (big header, sparse results), **text-only cards with no visual hierarchy**, and **coupling between Explore's "People also saved" and ForYou's recommended cards**.

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High     | 1 |
| Medium   | 9 |
| Low      | 6 |

---

## Issues

### █ Issue 1 (High) — Page max-width (1100px) is inconsistent with other pages

**URL:** `/explore`  
**Category:** Visual / UX  
**Severity:** High  

**Description:** The Explore page uses `max-width: 1100px` while the Ask page and For You page use `width: min(1440px, calc(100% - 48px))`. Every other page in the app extends to 1440px, but Explore is 340px narrower. Navigating between pages causes the entire content area to shift — the header navigation bar is fixed at full width, but the content below jumps inward on Explore.

**Code:** `explore.css:2`
```css
.explore-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 48px 24px 80px;
}
```
vs Ask page (`ask.css:2`):
```css
.ask-page {
  width: min(1440px, calc(100% - 48px));
}
```

**Expected:** Consistent page width across all tabs — use the same `min(1440px, calc(100% - 48px))` formula.

**Actual:** Explore is 340px narrower, causing a visual jump between pages.

---

### ▮ Issue 2 (Medium) — Text-only cards with no visual images

**URL:** `/explore` (with results)  
**Category:** Visual / UX  
**Severity:** Medium  

**Description:** Place cards are text-only — just a name, type, rating/price row, and address. No photos, no icons differentiating categories, no color coding. Compared to the Ask tab's `RecommendationListCard` which has images, tags, and rich visual cards, the Explore results feel sparse and indistinguishable. A row of 3-4 restaurant cards all look identical — only the name and rating differentiate them.

**Code:** `Explore.jsx:399-462` — the place card renders `h3.name`, `span.type`, `.place-meta` (rating/price/open), `p.address`.

**Expected:** Either add category-specific icons/colors to the card headers (a fork+knife for Eat, a wine glass for Drink), or load a small thumbnail from Google Maps / OSM. At minimum, visually distinguish categories through accent colors on the left border.

**Actual:** All cards are identical gray text boxes with no visual differentiation.

---

### ▮ Issue 3 (Medium) — Category chips + hood select + Events chip have awkward layout

**URL:** `/explore`  
**Category:** Visual / UX  
**Severity:** Medium  

**Description:** The `.explore-categories` flex row contains: 6 category chips + a neighborhood `<select>` (only visible when a category is active) + the Events chip. Three problems:

1. **Hood select breaks the pill rhythm** — Category chips are rounded pills with `border-radius: 999px`. The neighborhood `<select>` has `border-radius: 999px` too but is substantially wider (due to option text) and has a native OS dropdown arrow, making it look like a different component family.

2. **Events chip uses `margin-left: auto`** — It's always pinned to the far right edge. If the hood select is present, the Events chip sits after the select, looking disconnected from the category buttons.

3. **On narrow widths, chips wrap unpredictably** — With 6 categories + hood select + Events, the flex row wraps in an uncontrolled way, often leaving one chip stranded on its own line.

**Code:** `explore.css:60-65`, `240-256`
```css
.explore-categories { display: flex; flex-wrap: wrap; gap: 10px; }
.events-chip { margin-left: auto; }
```

**Expected:** Group Events as a separate row or a consistent separator (e.g., a vertical divider before Events, flush with the hood select on the same logical level).

**Actual:** Layout rhythm broken by mixed element types and `margin-left: auto` positioning.

---

### ▮ Issue 4 (Medium) — "Personalized for you" badge logic skips interests for budget users

**URL:** `/explore`  
**Category:** Functional / UX  
**Severity:** Medium  

**Description:** Two conditional badges appear below the search bar — one for price-tier personalization, one for interests-based ranking. The logic is:

```jsx
{userPrefs?.price_tier && (
  <div className="explore-prefs-badge">✦ Personalized for you</div>
)}
{userPrefs?.interests?.length > 0 && !userPrefs?.price_tier && (
  <div className="explore-prefs-badge">✦ Ranked by your interests</div>
)}
```

If a user has BOTH a price tier and interests, only the first badge shows. The interests badge is suppressed when `price_tier` is truthy. Users who filled out both sections never see "Ranked by your interests."

**Expected:** Show both badges when applicable, or combine them into a single message like "Personalized by your budget & interests."

**Actual:** Interests badging is silently hidden for users who also set a budget.

---

### ▮ Issue 5 (Medium) — Empty-state takes too much vertical space

**URL:** `/explore` (first visit, no search)  
**Category:** UX / Visual  
**Severity:** Medium  

**Description:** On first load, the page shows: h1 "Explore Tirana" → subtitle → search bar (with icon + input + button) → 7 category chips → Events chip → "Pick a category or search to see places." That's roughly **200px+ of header content** with a single line of small text below it. Below 1100px wide, chips wrap and the header grows even taller. The actual content area feels like an afterthought below the massive header.

**Code:** `Explore.jsx:393-396`
```jsx
{!loading && !hasSearched && (
  <p className="explore-status">
    Pick a category or search to see places.
  </p>
)}
```

**Expected:** Reduce header padding, move the status text inline, or show a compelling preview/illustration in the empty state to fill the visual gap.

**Actual:** 200px+ of chrome before any useful content on first visit.

---

### ▮ Issue 6 (Medium) — "People also saved" uses ForYou's `.recommended-card` class

**URL:** `/explore` (with results + saved places)  
**Category:** Maintenance / UX  
**Severity:** Medium  

**Description:** The "People also saved" strip at the bottom of Explore uses `.recommended-card` and `.recommended-card-body` CSS classes (defined in `foryou.css`), plus `flex: 0 0 240px` set in `explore.css:383`. These cards are semantically different from ForYou's recommended cards but share the same CSS class namespace. If someone updates ForYou's cards (e.g., changes padding, font sizes, or hover effects), Explore's "People also saved" cards change too — potentially in undesirable ways.

Additionally, Explore's cards have slightly different content (co-save count, no interest tags) compared to ForYou's, but the same class name suggests they should look identical.

**Code:** `explore.css:332-392` sets `.also-saved-scroll .recommended-card { flex: 0 0 240px }` but the base styles come from `foryou.css:1466-1478`.

**Expected:** Define Explore-specific card classes for the "People also saved" section to decouple it from ForYou's component styles.

**Actual:** Cross-page CSS coupling — changes to ForYou's recommended cards can break Explore's appearance.

---

### ▮ Issue 8 (Medium) — No scroll-snap or scroll restoration on results grid

**URL:** `/explore` (scrolled results)  
**Category:** UX  
**Severity:** Medium  

**Description:** The explore grid uses `auto-fill` with responsive card widths. When the user scrolls down, clicks a card (which opens Google Maps in a new tab), and returns, the scroll position is lost — the page resets to the top. There's no `scroll-snap` behavior or scroll restoration for the grid.

The "People also saved" horizontal scroll strip has `scroll-snap-type: x mandatory` but no scroll-position preservation when returning from a link click.

**Expected:** Implement scroll restoration or use `scroll-snap-align` consistent with the cards.

**Actual:** Scroll position lost on tab return.

---


### ▮ Issue 10 (Medium) — Rating filter dropdown is narrow and easy to miss

**URL:** `/explore` (after a search)  
**Category:** UX / Visual  
**Severity:** Medium  

**Description:** The "Min rating" filter is a small `<select>` with `padding: 4px 8px` and no visible border highlighting. On the same row as the "Open now" checkbox (which has a native checkbox + label), the select looks visually different from the checkbox — two different control types sitting side by side with different heights, borders, and interaction patterns.

**Code:** `explore.css:111-118` — small select with minimal padding and thin border.

---

### ▯ Issue 11 (Low) — Place meta layout causes wrapping at awkward points

**URL:** `/explore` (results)  
**Category:** Visual  
**Severity:** Low  

**Description:** `.place-meta` uses `flex-wrap: wrap` with `gap: 12px`. A card showing `★ 4.5 (1,234) · $$ · Open` can wrap mid-content on narrow cards: the rating, price, and open status each occupy separate lines unpredictably. The `gap: 12px` is generous for small label text.

---

### ▯ Issue 12 (Low) — Filter count shows "X of Y" without pluralization

**URL:** `/explore` (filtered results)  
**Category:** Content  
**Severity:** Low  

**Description:** The filter bar shows `"{filtered.length} of {results.length}"` — e.g., "1 of 5 results". There's no word "result" and no pluralization ("1 of 5"). It's just a number pair.

**Code:** `Explore.jsx:332-333`
```jsx
<span className="filter-count">
  {filtered.length} of {results.length}
</span>
```

**Expected:** "Showing 3 of 12 results" or similar descriptive text.

---

### ▯ Issue 13 (Low) — Card hover shadow jump

**URL:** `/explore` (results)  
**Category:** Visual  
**Severity:** Low  

**Description:** `.place-card` has no default `box-shadow`, but on hover it adds `0 10px 28px rgba(16, 33, 22, 0.1)`. The transition is `0.18s` but the shadow appears from `none` to a significant blur, creating a visible "pop" rather than a smooth fade-in. The card lift (`translateY(-3px)`) also lacks a matching perspective shadow.

---

### ▯ Issue 14 (Low) — Events chip uses `margin-left: auto` inconsistently

**URL:** `/explore`  
**Category:** Visual  
**Severity:** Low  

**Description:** When no category is active and the hood select is hidden, the Events chip is at the far right edge while the 6 category chips are left-aligned. When a category IS active, the hood select appears before Events. The layout rhythm changes between these two states.

---

### ▯ Issue 15 (Low) — "Eat" category results show no restaurant images or icons

**URL:** `/explore` (Eat category)  
**Category:** Visual  
**Severity:** Low  

**Description:** The eat category returns 12 restaurant names. Without images, each card is just a text block. Restaurant names like "Fresku Restorant" appear twice (different locations), and the cards look identical — only the name changes. No visual cues help the user scan and differentiate results.

---

### ▯ Issue 16 (Low) — Explore uses `max-width: 1100px` but other pages use `width: min(...)` — different box model

**URL:** `/explore`  
**Category:** Visual  
**Severity:** Low  

**Description:** `max-width: 1100px` doesn't constrain margins the same way as the `width: min(1440px, calc(100% - 48px))` pattern used on other pages. On very wide screens, the Explore page content is narrower and left-aligned differently than Ask or For You pages, breaking the visual rhythm when tab-switching.

---

## Summary Table

| # | Issue | Sev | Category |
|---|-------|-----|----------|
| 1 | Page max-width 1100px inconsistent with other pages (1440px) | High | Visual |
| 2 | Text-only cards with no images or visual differentiation | Med | Visual / UX |
| 3 | Category chips + hood select + Events chip layout awkward | Med | Visual |
| 4 | "Personalized for you" badge logic skips interests for budget users | Med | Functional / UX |
| 5 | Empty state takes too much vertical space | Med | UX / Visual |
| 6 | "People also saved" reuses ForYou's `.recommended-card` class | Med | Maintenance |
| 7 | Save button hidden on Google results without explanation | Med | UX |
| 8 | No scroll-snap or scroll restoration on results grid | Med | UX |
| 9 | No dark mode support | Med | Visual |
| 10 | Rating filter dropdown is narrow and easy to miss | Med | UX / Visual |
| 11 | Place meta wraps at awkward breakpoints | Low | Visual |
| 12 | Filter count lacks descriptive text or pluralization | Low | Content |
| 13 | Card hover shadow jumps from none to full blur | Low | Visual |
| 14 | Events chip positioning inconsistent between states | Low | Visual |
| 15 | Restaurant category results lack visual differentiation | Low | Visual |
| 16 | Inconsistent box model vs other pages | Low | Visual |

---

## Design Recommendations (Prioritized)

### 1. Fix page width consistency
Use the same `width: min(1440px, calc(100% - 48px))` formula as Ask and For You pages so the content area doesn't jump between tabs.

### 2. Add visual hierarchy to cards
- Add category-specific left border colors or thin accent strips (green = Eat, purple = Drink, orange = See, blue = Outdoors)
- Add a small category icon above the card name
- Consider a fallback thumbnail for owned OSM places (use category-based emoji/icon as placeholder)

### 3. Show save button on all results
The `g:<place_id>` namespace and `externalPayload()` function already support saving Google Places results. Show the bookmark button on ALL cards, not just OSM-owned ones.

### 4. Fix badge logic
Show both badges when applicable, or combine: "Personalized by your budget & interests ✦"

### 5. Reduce empty-state vertical weight
- Condense the header padding
- Show category chips in a more compact layout
- Add a small illustration or sample card preview in the empty state

### 6. Decouple "People also saved" from ForYou CSS
Define independent classes for Explore's "also saved" cards to prevent cross-page CSS coupling.

### 7. Add scroll restoration
Use `scroll-snap-align` and consider `history.scrollRestoration = 'manual'` with saved scroll positions per search.

### 8. Standardize filter controls
Make the "Min rating" select match the chip/checkbox visual language (rounded, same height, same border treatment).