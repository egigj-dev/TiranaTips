// src/lib/api.js
// Single place where the frontend talks to the FastAPI backend.
//
// Base URL comes from Vite env (`VITE_API_BASE` in .env.development /
// .env.production). Falls back to same-origin "" so a reverse-proxied
// production deploy (nginx serving the SPA + proxying /chat etc.) works
// with zero config. CORS on the backend is already `allow_origins=["*"]`,
// so a cross-origin dev setup (Vite on :5173 → API on :8000) also works.
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

// ---------------------------------------------------------------------------
// Identity — the backend is anonymous-by-design: user_id is "whatever UUID
// the client generated and kept in localStorage" (see main.py preferences
// section). session_id scopes chat history; user_id scopes preferences.
// Both must match ^[a-zA-Z0-9_-]{8,64}$ — crypto.randomUUID() (36 chars,
// hyphens) satisfies that.
// ---------------------------------------------------------------------------

function generateId() {
  // crypto.randomUUID() exists only in SECURE contexts (https / localhost).
  // The VPS currently serves plain http, where calling it throws and crashes
  // React on mount. crypto.getRandomValues() works in all contexts, so fall
  // back to 32 hex chars — still matches ^[a-zA-Z0-9_-]{8,64}$.
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function getOrCreateId(storageKey) {
  let id = localStorage.getItem(storageKey);
  if (!id) {
    id = generateId();
    localStorage.setItem(storageKey, id);
  }
  return id;
}

export const getUserId = () => getOrCreateId("tiranatips_user_id");
export const getSessionId = () => getOrCreateId("tiranatips_session_id");

/** Start a fresh chat thread (history is keyed by session_id). */
export function newSession() {
  const id = generateId();
  localStorage.setItem("tiranatips_session_id", id);
  return id;
}

/** Switch the active thread to an existing session. */
export function setSessionId(id) {
  localStorage.setItem("tiranatips_session_id", id);
}

// ---------------------------------------------------------------------------
// Small JSON helper
// ---------------------------------------------------------------------------

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${options.method || "GET"} ${path} → ${res.status} ${body}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Chat — POST /chat/stream (SSE over fetch)
//
// EventSource only supports GET, and this endpoint is POST with a JSON body,
// so we read the response body stream ourselves and parse `data:` lines.
// Event types emitted by the backend:
//   sources        → {sources: [{title, url?, type?}]}   (always first)
//   cache          → cached answer is being replayed
//   token          → {token: "..."}                      (append to answer)
//   translation    → {text: "..."}                       (REPLACES the answer)
//   low_confidence → {message: "..."}                    (fallback message)
//   done           → stream finished
// ---------------------------------------------------------------------------

export async function streamChat(
  { question, language = "auto", model = null, isRetry = false },
  { onSources, onToken, onTranslation, onLowConfidence } = {},
  signal = undefined
) {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({
      session_id: getSessionId(),
      user_id: getUserId(),
      question,
      language,
      is_retry: isRetry,
      ...(model ? { model } : {}),
    }),
    signal,
  });

  if (!res.ok || !res.body) {
    const err = new Error(`chat/stream failed: HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    // SSE frames are newline-delimited; the last element may be a partial
    // line that continues in the next chunk — keep it in the buffer.
    const lines = buffer.split("\n");
    buffer = lines.pop();

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      let evt;
      try {
        evt = JSON.parse(line.slice(6));
      } catch {
        continue; // malformed frame — skip rather than kill the stream
      }
      switch (evt.type) {
        case "sources":        onSources?.(evt.sources); break;
        case "token":          onToken?.(evt.token); break;
        case "translation":    onTranslation?.(evt.text); break;
        case "low_confidence": onLowConfidence?.(evt.message); break;
        case "done":           return;
        // "cache" is informational — tokens follow either way.
      }
    }
  }
}

// ---------------------------------------------------------------------------
// History / feedback
// ---------------------------------------------------------------------------

/** → {messages: [{role: "user"|"assistant", content: string, ...}]} */
export const getHistory = () => request(`/history/${getSessionId()}`);

// ---------------------------------------------------------------------------
// Sessions — list past chat threads, rename, delete. The active thread is
// whatever getSessionId() returns; the sidebar switches it via setSessionId.
// Backend returns { sessions: [{ session_id, display_name }] }, newest first.
// ---------------------------------------------------------------------------

export const getSessions = () => request("/sessions");

export const getHistoryFor = (sessionId) =>
  request(`/history/${sessionId}`);

export const renameSession = (sessionId, displayName) =>
  request(`/sessions/${sessionId}/rename`, {
    method: "PATCH",
    body: JSON.stringify({ display_name: displayName }),
  });

export const deleteSession = (sessionId) =>
  request(`/sessions/${sessionId}`, { method: "DELETE" });

/** rating: 1 (thumbs up) | -1 (thumbs down). Question = the USER question
 *  that produced the rated answer (backend evicts its cache entries on -1). */
export const sendFeedback = (question, rating) =>
  request("/feedback", {
    method: "POST",
    body: JSON.stringify({ session_id: getSessionId(), question, rating }),
  });

// ---------------------------------------------------------------------------
// Preferences (anonymous, keyed by the localStorage user_id)
// ---------------------------------------------------------------------------

/** Canonical option lists: {modes, price_tiers, currencies, interests} */
export const getPreferenceOptions = () => request("/preferences/options");

/** Always 200; brand-new users get all-null fields + onboarded:false */
export const getPreferences = () => request(`/preferences/${getUserId()}`);

/** Partial upsert — omit any field to leave it unchanged on the server. */
export const savePreferences = (prefs) =>
  request(`/preferences/${getUserId()}`, {
    method: "PUT",
    body: JSON.stringify(prefs),
  });

export const deletePreferences = () =>
  request(`/preferences/${getUserId()}`, { method: "DELETE" });

// ---------------------------------------------------------------------------
// Places — ready, but currently has no consumer in the new UI (cards are
// demo-only until the chat emits structured place data).
// Returns {found: bool, place: {name, rating, address, hours, maps_url, ...}}
// ---------------------------------------------------------------------------

export const searchPlace = (name) =>
  request("/places/search", { method: "POST", body: JSON.stringify({ name }) });

// Multi-result search for the Explore page. Categories are preset queries.
// Returns { count, places: [{ name, rating, reviews, address, type, price,
// open_now, maps_url, gps, ... }] }.
export const explorePlaces = (query, limit = 12) =>
  request("/places/explore", {
    method: "POST",
    body: JSON.stringify({ query, limit }),
  });

// Filtered semantic search over the OWNED OSM index (vector match + payload
// filter on category/neighborhood/max_price). Returns {count, places:[{slug,
// name, category, neighborhood, price_tier, interest_tags, gps}]}. Note these
// rows have NO rating/open_now/address — OSM doesn't carry them; that's the
// live-Google enrichment layer (a later increment). Use for category/filter
// browsing over the whole dataset; use explorePlaces() for free-text + rich
// Google cards.
export const browsePlaces = (params) =>
  request("/places/browse", {
    method: "POST",
    body: JSON.stringify(params),
  });
// ---------------------------------------------------------------------------
// City notes — cached live data for the Home "Smart Local Notes" cards.
// Shape: { weather, exchange, departures, arrivals } — any section can be
// null until the backend's first refresh completes; render placeholders.
// ---------------------------------------------------------------------------

export const getCityNotes = () => request("/city/notes");

// Upcoming events for the Explore page — from the same ingested events table
// the chat uses. {count, events:[{title, description, category, start_date,
// end_date, venue, image_url, ticket_url, source_url}]}.
export const getEvents = (days = 30, category = null) => {
  const qs = new URLSearchParams({ days });
  if (category) qs.set("category", category);
  return request(`/events?${qs.toString()}`);
};