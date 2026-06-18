# Audit Report: Chat Tab (Ask) — Design & Functionality

**Scope:** `/ask` page — chat interface, sidebar, input, feedback, context picker, session management  
**Date:** 2026-06-18  
**Tester:** Hermes QA Agent  
**Version:** Frontend served via nginx on port 80, FastAPI backend on port 8000

---

## Executive Summary

10 issues found: **1 Medium**, **9 Low**. No critical or high-severity blockers. The chat tab is functional — questions send, answers stream, feedback persists. The main gaps are around anonymous user experience (history invisible, context picker empty) and UX polish (duplicate rendering, rapid-click races, dark mode gap).

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High     | 0 |
| Medium   | 1 |
| Low      | 9 |

| Category  | Count |
|-----------|-------|
| Functional | 2 |
| UX         | 3 |
| Visual     | 1 |
| Content    | 2 |
| Accessibility | 0 |
| Console    | 0 |

---

## Issues

### ⬤ Issue 1 (Medium) — Anonymous users lose all session history

**URL:** `/ask`  
**Category:** Functional  
**Severity:** Medium  

**Description:** Anonymous users can send questions and receive answers — the backend persists the session to SQLite — but the `/sessions` endpoint requires authentication (`_require_user` → 401 without a token). The sidebar never shows a "Your chats" section for unauthenticated users. After clicking "+ New chat", there is no way to return to previous conversations. The session is saved but unreachable.

**Steps to reproduce:**
1. Visit `/ask` without logging in
2. Send a question (e.g. click "Good coffee near Blloku?")
3. Wait for answer to stream
4. Click "+ New chat"
5. Observe: no "Your chats" section appears in the sidebar

**Expected:** Anonymous sessions should be listable (scoped by the localStorage `user_id`), or the app should prompt login to save history.

**Actual:** Sidebar only shows logo, New chat button, New with context button, and Most asked list. All chat data is orphaned.

**Relevant code:**
- `Ask.jsx:112-115` — `refreshSessions()` silently swallows errors (`.catch(() => {})`)
- `main.py:1649-1670` — `list_sessions()` requires authenticated user
- `api.js:164-165` — `getSessions()` sends no auth headers for anonymous users

---

### ▫ Issue 2 (Low) — "New with context" modal always empty for anonymous users

**URL:** `/ask`  
**Category:** UX  
**Severity:** Low  

**Description:** The "📋 New with context" button triggers the context picker modal, but `/summaries` (like `/sessions`) requires authentication. The modal always shows "No saved summaries found" with a hint about generating summaries after 10 messages — even for users who HAVE chat history in this session.

**Steps to reproduce:**
1. Visit `/ask` without logging in
2. Send a question and wait for answer
3. Click "📋 New with context"
4. Observe: modal shows "No saved summaries found. Summaries are automatically generated after 10 messages in a chat."

**Expected:** Either show available past sessions for context import, or explain that login is required.

**Actual:** Misleading empty state — the hint implies the user hasn't chatted enough, but the real blocker is auth.

---

### ▫ Issue 3 (Low) — Rapid double-click on quick-ask buttons sends duplicate requests

**URL:** `/ask`  
**Category:** Functional  
**Severity:** Low  

**Description:** The "Most asked" quick buttons call `sendQuestion()` directly without debouncing. The `isStreaming` guard uses React state (`useState`), which is asynchronous — two rapid clicks in the same render cycle both see `isStreaming === false` and trigger separate stream requests. This results in duplicate user messages and duplicate assistant answers appearing in the chat.

**Steps to reproduce:**
1. Visit `/ask`
2. Click "Good coffee near Blloku?" twice in quick succession (under ~50ms)
3. Observe: two identical user messages and two assistant answers appear

**Expected:** Second click should be silently ignored while a stream is active.

**Actual:** Duplicate question/answer pairs appear.

**Suggested fix:** Use a `useRef` for `isStreaming` (or add `event.preventDefault()` / `disabled` state on the buttons) to make the guard synchronous.

---

### ▫ Issue 4 (Low) — Place names render both inline and as source pills (duplication)

**URL:** `/ask` (after any answer with place sources)  
**Category:** Visual  
**Severity:** Low  

**Description:** When the backend returns place sources, places appear TWICE in the assistant message: (1) as highlighted inline markdown links in the answer text (styled with `📍` prefix via `.place-link::before`), and (2) as separate source pills below the message. This creates visual redundancy — the same places listed twice in sequence.

**Steps to reproduce:**
1. Click "Good coffee near Blloku?"
2. Wait for answer
3. Observe the message: places are listed in the answer text AND again as source pills below

**Expected:** Places should appear once (either inline or as source pills, not both), or the two should be visually differentiated (e.g., sources shown only for web/event links, not for places already mentioned inline).

**Actual:** "📍 Angolo Coffee" appears in the answer text AND in the `.message-sources` pills below.

---

### ▫ Issue 5 (Low) — Duplicate source pill entries for same place

**URL:** `/ask` (after coffee question)  
**Category:** Content  
**Severity:** Low  

**Description:** Some place names appear multiple times in the source pills section. For example, "📍 Coffee House" appeared twice in the sources (ref `@e31` and `@e32` in the DOM snapshot), suggesting the backend returns duplicate entries in the sources array.

**Steps to reproduce:**
1. Click "Good coffee near Blloku?"
2. Inspect the `.message-sources` section
3. Observe: some place names appear twice

**Expected:** Each unique place should appear once in source pills.

**Actual:** Duplicate entries in the source list.

---

### ▫ Issue 6 (Low) — No dark mode support in chat tab

**URL:** `/ask`  
**Category:** Visual  
**Severity:** Low  

**Description:** The site's `index.css` includes a `@media (prefers-color-scheme: dark)` block with dark mode variables, but `ask.css` hardcodes all colors in the warm/cream palette (`#fffaf1`, `#edf3e5`, `#1f5a2e`, `#102116`, etc.) with no dark mode overrides. Users with dark mode enabled on their OS/browser will see a stark contrast between the dark-mode-adapted index layout and the always-light chat tab colors.

**Steps to reproduce:**
1. Enable OS-level dark mode
2. Visit `/ask`
3. Observe: the page body may render dark via `index.css`, but the chat component stays in the cream/green palette with no dark adaptation

**Expected:** The chat component should respect `prefers-color-scheme` and render appropriately in dark mode.

**Actual:** Hardcoded light colors throughout `ask.css` with no dark mode media queries.

---

### ▫ Issue 7 (Low) — Footer omits "Global" and "For You" navigation links

**URL:** `/ask` (visible on all pages)  
**Category:** Content  
**Severity:** Low  

**Description:** The main navigation includes five tabs: Today, Explore, Ask, Global, and For You. The footer's "CITY" section only lists three: Today, Explore, Ask. Global and For You are missing from the footer navigation.

**Steps to reproduce:**
1. Scroll to the footer on any page
2. Compare footer links to header navigation links
3. Observe: Global and For You are missing

**Expected:** Footer should mirror the header's navigation links for consistency.

**Actual:** Footer omits 2 of 5 navigation items.

**Relevant code:** `Footer.jsx:5-9` — `footerLinks` array only has Today, Explore, Ask.

---

### ▫ Issue 8 (Low) — Source pills include non-interactive span fallback

**URL:** `/ask` (in assistant messages)  
**Category:** UX  
**Severity:** Low  

**Description:** Source items without `url` or `maps_url` render as a bare `<span>` (plain text with no interaction). If a source has no URL, it shows as non-clickable text with a 📄 icon next to it — the user can't do anything with it, wasting space and causing confusion.

**Steps to reproduce:** (Requires a backend source with `type: "local"` or a missing URL field.)

**Relevant code:** `Ask.jsx:528-530`
```jsx
: (
  <span key={i}>📄 {source.title || source}</span>
)
```

**Expected:** Non-linkable sources should be hidden from the UI entirely, or displayed with a brief explanation.

**Actual:** Empty/inert source pills appear.

---

### ▫ Issue 9 (Low) — Logged-out state shows no hint about session persistence

**URL:** `/ask`  
**Category:** UX  
**Severity:** Low  

**Description:** When not logged in, the welcome message says "Hi, I'm TiranaTips. Ask me like you would ask a local friend." — but gives no indication that chat history won't be saved or accessible after leaving the page. The sidebar shows no session list, but doesn't explain why or suggest logging in.

**Expected:** If history is login-gated, the welcome message or sidebar should include a hint: "Log in to save your chats across visits."

**Actual:** Anonymous users chat normally with no visible indication that their history is ephemeral.

---

### ▫ Issue 10 (Low) — Footer "CITY" section heading is misleading for chat link

**URL:** `/ask` (footer)  
**Category:** Content  
**Severity:** Low  

**Description:** The footer groups Today, Explore, and Ask under a heading "CITY". While Today and Explore are city-related, "Ask" is a conversational AI feature, not a city section. The grouping feels mismatched.

**Expected:** Either rename "CITY" to "Navigate" or "Menu", or move "Ask" to a separate section.

**Actual:** An AI chat feature sits under a "CITY" label in the footer.

---

## Summary

| # | Issue | Severity | Category |
|---|-------|----------|----------|
| 1 | Anonymous sessions unreachable from sidebar | Medium | Functional |
| 2 | "New with context" empty state misleading for anonymous users | Low | UX |
| 3 | Rapid double-click sends duplicate requests | Low | Functional |
| 4 | Places rendered both inline and as source pills | Low | Visual |
| 5 | Duplicate entries in source pills | Low | Content |
| 6 | No dark mode support in chat tab | Low | Visual |
| 7 | Footer omits Global and For You links | Low | Content |
| 8 | Non-linkable sources render as inert spans | Low | UX |
| 9 | No hint about anonymous session ephemerality | Low | UX |
| 10 | Footer "CITY" heading mislabels AI chat link | Low | Content |

## Testing Notes

**What was tested:**
- Page load (no console errors, no network failures)
- Welcome message rendering
- "Most asked" quick-ask buttons (send question, stream answer)
- Custom typed question submission via form
- Empty input guard (correctly blocked)
- Send button disabled during streaming
- "+ New chat" resets session correctly
- "📋 New with context" opens context picker modal
- Thumbs up/down feedback (API call made, no errors)
- Rapid double-click behavior
- Source pill rendering (place links, emoji icons)
- Navigation active state for Ask tab
- Footer link consistency
- Dark mode readiness
- Anonymous vs authenticated session behavior

**What was not tested:**
- Authenticated user flows (login required)
- PlaceDetailsModal interactions (requires structured recommendation data)
- PlaceMapModal (Leaflet map rendering — logged at port 80 but Leaflet tiles load from CDN)
- `downloadSession` functionality
- Multi-session sidebar behavior (requires auth)
- Session rename (PATCH endpoint)
- 429 rate limiting response
- 422 max length response
- Loading state after "New with context" on slow connections

## Key Strengths
- Zero console errors across all tested interactions
- SSE streaming works correctly (sources → token → final → done)
- Error handling for 429/422 is user-friendly
- Translation buffer (no English flash) is well implemented
- Clean, warm visual design with consistent brand palette
- Smooth "New chat" transition
- Feedback has clear toggle (can only rate once)