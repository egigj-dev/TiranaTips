# Design Audit: For You Page

**URL:** `/foryou`  
**Component:** `ForYou.jsx` + `foryou.css`  
**States:** Guest (not logged in), Logged-in dashboard  
**Assets:** `for-you.png` (1.2MB hero bg), `skyline.png` (100KB logged-in hero)  
**Icons:** Lucide React (logged-in), Unicode symbols (guest benefits)

---

## Executive Summary

18 issues found. The For You page has two states (guest marketing page + authenticated dashboard) that share no visual DNA — they feel like two different pages from different apps stitched together. The guest page suffers from a cramped two-column layout, five-card row that overflows text, and non-functional buttons. The logged-in dashboard overuses absolute positioning and negative margins for layout, creating fragile breakpoints. Empty states lack hierarchy, and the page has no cohesive visual narrative.

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High     | 3 |
| Medium   | 9 |
| Low      | 6 |

---

## Guest (Unauthenticated) Issues

### █ Issue 1 (High) — Mode cards are `<button>` elements with no onClick handler

**URL:** `/foryou` (guest)  
**Category:** UX / Functional  
**Severity:** High  

**Description:** The five mode cards ("Local", "Student", "Tourist", "Digital Nomad", "Business Visitor") are rendered as `<button type="button">` elements with hover effects (translateY, border glow), but they have NO `onClick` handler. They appear clickable but do nothing. This is a fundamental UX violation — stared-at elements that look like interactive cards but are purely decorative.

**Code:** `ForYou.jsx:273`
```jsx
<button type="button" className="mode-card" key={mode.title}>
```

No `onClick` is passed. The modes are only informative for the guest view, but the button element implies action.

**Expected:** Either (a) remove the button element and use a `<div>` or `<article>`, or (b) make clicking them scroll to the signup CTA / open the register modal with that mode pre-selected.

**Actual:** 5 clickable-looking cards that do nothing.

---

### █ Issue 2 (High) — Guest two-column layout is cramped and misproportioned

**URL:** `/foryou` (guest)  
**Category:** Visual / UX  
**Severity:** High  

**Description:** The `.guest-top` uses `grid-template-columns: 1.05fr 0.95fr` — a near-50/50 split. This pushes the hero section (title, description, CTA buttons) into the left half, while the benefits grid occupies the right half. The hero heading ("Your personal Tirana space.") is a large serif font (`clamp(48px, 5.2vw, 72px)`) that needs space to breathe, but gets compressed into a narrow column. The CTA buttons stack awkwardly when space is tight.

At the same time, the benefits column on the right has 4 two-column benefit cards in a 2×2 grid — each card is very narrow, causing text wrapping at every word boundary.

**Code:** `foryou.css:57-60` `.guest-top` and `foryou.css:168-170` `.benefits-grid`
```css
.guest-top {
  grid-template-columns: 1.05fr 0.95fr;
}
.benefits-grid {
  grid-template-columns: repeat(2, 1fr);
}
```

**Expected:** Either stack vertically (hero above benefits) or use a wider hero column (e.g., 1.5fr / 0.5fr) so the hero text has room to breathe.

**Actual:** Both columns fight for space; hero text feels claustrophobic, benefit cards are squished.

---

### █ Issue 3 (High) — 5 mode cards in one row create overflow and tight text

**URL:** `/foryou` (guest)  
**Category:** Visual / UX  
**Severity:** High  

**Description:** The mode cards use `grid-template-columns: repeat(5, 1fr)` at full width. With card labels like "Digital Nomad" and "Business Visitor", the text wraps awkwardly in each narrow card. Each card is roughly 140-160px wide at 1180px container width. The label plus subtitle text ("Work, stay & explore", "Work trips & meetings") becomes very cramped.

At 1080px breakpoint it drops to 3 columns, which is much better, but the default wide view is the primary experience.

**Code:** `foryou.css:222-225`
```css
.mode-grid {
  grid-template-columns: repeat(5, 1fr);
}
```

**Expected:** Use 3 columns by default and let the cards breathe, or make cards more compact with single-word labels.

**Actual:** Cards are cramped with text wrapping at awkward breakpoints.

---

### ▮ Issue 4 (Medium) — Benefits grid uses inconsistent Unicode symbols

**URL:** `/foryou` (guest)  
**Category:** Visual / Content  
**Severity:** Medium  

**Description:** The four benefit cards use raw Unicode symbols as their icons: ♡ (heart), ☆ (star), ♙ (chess pawn), ⌘ (command/looped square). Three problems:

1. **Inconsistent rendering** — Unicode symbols render differently across OS/browser. ♙ (chess pawn) is particularly unrecognizable for most users as a metaphor for "Set your city mode".
2. **Mac-specific** — ⌘ (command key symbol) is strongly associated with macOS keyboards. Non-Mac users won't recognize it as an icon.
3. **No visual connection** — The icons don't form a cohesive visual language. The logged-in dashboard uses Lucide React icons, creating a jarring switch between the two page states.

**Code:** `ForYou.jsx:187-203`
```jsx
benefits = [
  { icon: "♡", title: "Save favorite places", ... },
  { icon: "☆", title: "Choose your interests", ... },
  { icon: "♙", title: "Set your city mode", ... },
  { icon: "⌘", title: "Manage preferences", ... },
];
```

**Expected:** Use the same Lucide React icon set as the rest of the dashboard for consistency. Bookmark → Save, Star → Choose interests, Map → City mode, Settings → Preferences.

**Actual:** Random Unicode symbols with poor metaphorical mapping.

---

### ▮ Issue 5 (Medium) — Guest bottom layout feels disconnected

**URL:** `/foryou` (guest)  
**Category:** UX / Visual  
**Severity:** Medium  

**Description:** The `.guest-bottom` section uses `1.25fr 0.75fr` for mode cards (left) and signup note (right). The signup note looks like a separate card glued to the side of the mode section, not part of the same flow. It uses a green radial gradient background that doesn't match any other element on the page. The section feels like two unrelated widgets rather than a cohesive call-to-action.

**Code:** `foryou.css:212-218`
```css
.guest-bottom {
  grid-template-columns: 1.25fr 0.75fr;
}
```

**Expected:** Either make the signup note span full width below the mode cards (as a clear CTA footer), or integrate it visually with matching background treatments.

**Actual:** Disconnected two-column layout with mismatched visual language.

---

### ▮ Issue 6 (Medium) — No progressive disclosure / narrative flow

**URL:** `/foryou` (guest)  
**Category:** UX  
**Severity:** Medium  

**Description:** The guest page presents four sections stacked vertically with no clear narrative progression:

1. Hero (title + CTA buttons)
2. Benefits grid (4 cards)
3. Mode cards (5 cards)
4. Signup note

There's no visual hierarchy guiding the user through "what is this page → why should I care → what do I do". Both the hero (Create account / Log in) and the signup note ("Get started") have CTAs competing for the user's attention with no priority distinction.

**Expected:** A clear funnel: hero → brief value prop → single prominent CTA. Mode cards could be shown AFTER signup during onboarding (the Register component already has a step 2 for this).

**Actual:** Multiple competing CTAs with no clear primary action.

---

### ▮ Issue 7 (Medium) — Mode cards are decorative only for guest users

**URL:** `/foryou` (guest)  
**Category:** UX  
**Severity:** Medium  

**Description:** Building on Issue 1 — even if the buttons were non-interactive divs, the mode cards take up a huge amount of vertical space describing features the user can only access after signing up. These cards would be better placed inside the onboarding flow (Register step 2) rather than consuming half the guest page. Currently the user reads descriptions of 5 city modes, then has to scroll past them to reach the signup note.

**Expected:** Either move mode selection to the registration flow (where it already partially exists), or show only 1-2 highlighted modes as teasers on the guest page.

**Actual:** 5 decorative cards consuming 350+px of vertical space before the CTA.

---

### ▮ Issue 8 (Medium) — Logged-in dashboard uses fragile negative-margin overlap

**URL:** `/foryou` (logged-in)  
**Category:** Visual / UX  
**Severity:** Medium  

**Description:** The `.profile-summary-strip` uses `margin: -38px auto 0` to create an overlap with the hero dashboard below it. This is a fragile layout pattern:

1. If the hero height changes (e.g., longer display name, more text), the overlap amount is wrong
2. At 760px the hero switches to `flex-direction: column`, making the skyline image render below the text — the negative margin now overlaps into the skyline
3. The strip uses `z-index: 4` to sit above the hero's `z-index: 3`, creating potential stacking conflicts with the map modals (z-index: 9999) and other overlay elements

**Code:** `foryou.css:470-474`
```css
.profile-summary-strip {
  width: calc(100% - 64px);
  margin: -38px auto 0;
  z-index: 4;
}
```

**Expected:** Use a standard adjacent layout or a clean card with a subtle top border/separator. Avoid negative margins for layout.

**Actual:** Fragile overlap that will break if content changes.

---

### ▮ Issue 9 (Medium) — Dashboard 3-column grid creates uneven visual weight

**URL:** `/foryou` (logged-in)  
**Category:** Visual / UX  
**Severity:** Medium  

**Description:** The `.dashboard-grid` uses `grid-template-columns: repeat(3, 1fr)` with two wrapper divs: `.dashboard-col-main` (2 columns via span) and `.dashboard-col-side` (1 column). The main column contains the large "Saved places" card + map card, while the side column has "Interests" + "Preferences". This creates:

1. The Saved places section becomes very wide (2/3 of viewport), but the cards inside use `grid-template-columns: repeat(5, 1fr)` — tiny mini-cards with just text
2. The interests/preferences side column feels squished and lacks breathing room
3. At 1080px the entire grid collapses to 1 column, meaning the careful 3-column layout only works in a narrow viewport range (~1081px to ~1440px)

**Code:** `foryou.css:576-581`
```css
.dashboard-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
```

**Expected:** Consider a 2-column layout as default with a wider sidebar, or a single-column scroll with better visual hierarchy.

**Actual:** Fragile 3-column layout that only works in a specific viewport range.

---

### ▮ Issue 10 (Medium) — Recommended carousel chevrons visible but potentially useless

**URL:** `/foryou` (logged-in)  
**Category:** UX  
**Severity:** Medium  

**Description:** The recommended places strip has left/right chevron buttons for scrolling the `.recommended-scroll` container. If the recommended cards (200px each) don't overflow the container (e.g., only 2-3 recommendations), the chevron buttons are still visible but scrolling does nothing. There's no logic to hide them when the content fits.

**Code:** `ForYou.jsx:479-527` — the buttons always render when `recommended.length > 0`

**Expected:** Only show scroll buttons when `recommended-scroll` overflows its container (`scrollWidth > clientWidth`).

**Actual:** Potentially non-functional scroll buttons visible.

---

### ▯ Issue 11 (Low) — "Your AI local assistant" subtitle appears in sidebar but not in page

**URL:** `/foryou`  
**Category:** Content / UX  
**Severity:** Low  

**Description:** The sidebar has a subtitle "Your AI local assistant" under "Ask Tirana" heading. The For You page guest view shows a pill "For You" (small green chip) and the heading "Your personal Tirana space." — but no subtitle that mirrors the sidebar/Ask page vertical rhythm. The page header lacks a consistent pattern.

---

### ▯ Issue 12 (Low) — Guest page has no scroll indicator or visual separation between sections

**URL:** `/foryou` (guest)  
**Category:** Visual / UX  
**Severity:** Low  

**Description:** The hero, benefits, modes, and signup note sections transition with different background colors but very similar border treatments (all 1px rgba borders). At a glance, the sections blend into each other. A user scanning the page might not immediately see there are 4 distinct content blocks.

---

### ▯ Issue 13 (Low) — `foryou.css` has extensive commented-out CSS

**URL:** `/foryou`  
**Category:** General  
**Severity:** Low  

**Description:** There are large blocks of commented-out CSS throughout foryou.css (lines ~583-594, ~664-669, ~858-863, plus the commented-out background gradient on `.logged-hero-dashboard`). This suggests iterative design changes that were never cleaned up. The commented code increases the file size and makes future maintenance harder.

---

### ▯ Issue 14 (Low) — Empty states share identical `.empty-cta` style with different text

**URL:** `/foryou` (logged-in)  
**Category:** Visual / UX  
**Severity:** Low  

**Description:** The "Find places to save" and "Add interests" empty states both use the `.empty-cta` class — a plus icon + strong text + small helper text. The plus icon and layout are identical. These CTAs link to different destinations (/explore vs edit preferences) but visually there's no distinction between them.

---

### ▯ Issue 15 (Low) — No dark mode support

**URL:** `/foryou`  
**Category:** Visual  
**Severity:** Low  

**Description:** Same issue as the Ask tab — all colors in `foryou.css` are hardcoded to the cream/green palette with no `@media (prefers-color-scheme: dark)` overrides.

---

### ▯ Issue 16 (Low) — Profile summary strip columns don't work well at tablet

**URL:** `/foryou` (logged-in)  
**Category:** Visual  
**Severity:** Low  

**Description:** At 1080px breakpoint, the `.profile-summary-strip` switches from 5 columns to 2 columns. The 4 summary items (Budget, Currency, Language, Member since) stack in a 2×2 grid with the profile avatar at full width above. The "Language" select dropdown appears in a narrow cell, and the column widths (`1fr 1fr`) push labels to overflow or wrap ungracefully.

---

### ▯ Issue 17 (Low) — `logged-hero-actions` position z-index may conflict with skyline

**URL:** `/foryou` (logged-in)  
**Category:** Visual  
**Severity:** Low  

**Description:** The "Edit profile" button has `z-index: 3` via `.logged-hero-text, .logged-hero-actions { z-index: 3 }`. The skyline image has `z-index: 1`. Since both are in the same stacking context, this is fine — but if the hero background gradient (`z-index: default`) overlaps, or if the skyline image has a different stacking, the button could become unclickable in some viewport configurations.

---

### ▯ Issue 18 (Low) — Signup note icon is another Unicode orphan

**URL:** `/foryou` (guest)  
**Category:** Visual  
**Severity:** Low  

**Description:** The signup note in the guest bottom uses `✣` (open centre cross / saltire) as its icon. Like the benefits grid, this is a raw Unicode character that renders inconsistently across platforms and doesn't match the Lucide icon language used elsewhere.

---

## Summary Table

| # | Issue | Sev | Category |
|---|-------|-----|----------|
| 1 | Mode cards are clickable buttons that do nothing | High | UX / Functional |
| 2 | Guest two-column layout is cramped and misproportioned | High | Visual / UX |
| 3 | 5 mode cards in one row create overflow and tight text | High | Visual / UX |
| 4 | Benefits grid uses inconsistent Unicode symbols | Med | Visual / Content |
| 5 | Guest bottom layout feels disconnected | Med | UX / Visual |
| 6 | No progressive disclosure / narrative flow | Med | UX |
| 7 | Mode cards are decorative only for guest users | Med | UX |
| 8 | Logged-in dashboard uses fragile negative-margin overlap | Med | Visual / UX |
| 9 | Dashboard 3-column grid creates uneven visual weight | Med | Visual / UX |
| 10 | Recommended carousel chevrons visible but potentially useless | Med | UX |
| 11 | No subtitle/micro-copy in page header | Low | Content |
| 12 | Guest sections lack visual separation | Low | Visual |
| 13 | Commented-out CSS cruft | Low | General |
| 14 | Empty state CTAs share identical visual treatment | Low | Visual |
| 15 | No dark mode support | Low | Visual |
| 16 | Profile summary strip columns fragile at tablet | Low | Visual |
| 17 | Z-index overlap risk with skyline image | Low | Visual |
| 18 | Signup note uses Unicode orphan icon | Low | Visual |

---

## Design Recommendations (Prioritized)

### 1. Fix the guest page layout
- Stack hero above benefits vertically instead of side-by-side
- Reduce mode cards to 3 per row (or carousel)
- Replace `<button>` on mode cards with `<article>` or route them to signup
- Replace Unicode symbols with Lucide icons matching the dashboard

### 2. Give the guest page a narrative flow
- Hero → "Create account" as the primary CTA
- Remove the second CTA at the bottom or make it a secondary link
- Move mode selection into registration flow (step 2 already exists)

### 3. Replace negative-margin overlap on profile strip
- Use a clean card below the hero with a subtle top separator
- Avoid z-index stacking complications

### 4. Reconsider dashboard grid at medium widths
- Use 2-column layout as default instead of 3
- Keep saved places and map as a single column, interests + preferences as a second column

### 5. Hide carousel chevrons when content fits
- Add `useEffect` check on `scrollWidth > clientWidth` to conditionally render

### 6. Clean up CSS
- Remove commented-out blocks
- Add dark mode media queries consistent with `index.css`

### 7. Add micro-copy and scroll indicators
- Give the guest page a subtitle matching the Ask page pattern
- Add subtle section dividers between content blocks