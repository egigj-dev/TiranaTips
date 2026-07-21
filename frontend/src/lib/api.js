// // src/lib/api.js
// // Single place where the frontend talks to the FastAPI backend.
// import { getSessionToken } from "./auth.js";


// // Base URL comes from Vite env (`VITE_API_BASE` in .env.development /
// // .env.production). Falls back to same-origin "" so a reverse-proxied
// // production deploy (nginx serving the SPA + proxying /chat etc.) works
// // with zero config. CORS on the backend is already `allow_origins=["*"]`,
// // so a cross-origin dev setup (Vite on :5173 → API on :8000) also works.
// const API_BASE = import.meta.env.VITE_API_BASE ?? "";

// // Log the resolved API base on load so the developer can verify routing
// console.log("[api] API_BASE =", JSON.stringify(API_BASE), "— all fetch requests will go to:", API_BASE || "(same origin, relies on Vite proxy)");

// // ---------------------------------------------------------------------------
// // Identity — the backend is anonymous-by-design: user_id is "whatever UUID
// // the client generated and kept in localStorage" (see main.py preferences
// // section). session_id scopes chat history; user_id scopes preferences.
// // Both must match ^[a-zA-Z0-9_-]{8,64}$ — crypto.randomUUID() (36 chars,
// // hyphens) satisfies that.
// // ---------------------------------------------------------------------------

// function generateId() {
//   // crypto.randomUUID() exists only in SECURE contexts (https / localhost).
//   // The VPS currently serves plain http, where calling it throws and crashes
//   // React on mount. crypto.getRandomValues() works in all contexts, so fall
//   // back to 32 hex chars — still matches ^[a-zA-Z0-9_-]{8,64}$.
//   if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
//   const bytes = new Uint8Array(16);
//   crypto.getRandomValues(bytes);
//   return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
// }

// function getOrCreateId(storageKey) {
//   let id = localStorage.getItem(storageKey);
//   if (!id) {
//     id = generateId();
//     localStorage.setItem(storageKey, id);
//   }
//   return id;
// }

// export const getUserId = () => getOrCreateId("tiranatips_user_id");
// export const getSessionId = () => getOrCreateId("tiranatips_session_id");

// /** Start a fresh chat thread (history is keyed by session_id). */
// export function newSession() {
//   const id = generateId();
//   localStorage.setItem("tiranatips_session_id", id);
//   return id;
// }

// /** Switch the active thread to an existing session. */
// export function setSessionId(id) {
//   localStorage.setItem("tiranatips_session_id", id);
// }

// // ---------------------------------------------------------------------------
// // Small JSON helper
// // ---------------------------------------------------------------------------

// export async function request(path, options = {}) {
//   const { headers, ...rest } = options;
//   const res = await fetch(`${API_BASE}${path}`, {
//     // Merge caller headers onto the JSON default. Spreading `...options`
//     // directly let a caller's `headers` (e.g. authHeaders()) replace the whole
//     // object and drop Content-Type, so body-bearing POSTs (e.g. /saves) were
//     // sent without a JSON content-type and rejected with 422.
//     headers: { "Content-Type": "application/json", ...headers },
//     ...rest,
//   });
//   if (!res.ok) {
//     const body = await res.text().catch(() => "");
//     throw new Error(`${options.method || "GET"} ${path} → ${res.status} ${body}`);
//   }
//   return res.json();
// }

// // ---------------------------------------------------------------------------
// // Chat — POST /chat/stream (SSE over fetch)
// //
// // EventSource only supports GET, and this endpoint is POST with a JSON body,
// // so we read the response body stream ourselves and parse `data:` lines.
// // Event types emitted by the backend:
// //   sources        → {sources: [{title, url?, type?}]}   (always first)
// //   cache          → cached answer is being replayed
// //   token          → {token: "..."}                      (append to answer)
// //   final          → {text: "..."}                       (link-injected answer; REPLACES)
// //   low_confidence → {message: "..."}                    (fallback message)
// //   done           → stream finished
// // The model now replies directly in the user's language, so the old
// // 'translation'/'generating' events are gone — tokens stream live in-language
// // and the 'final' event swaps in the Maps-link-injected version at the end.
// // ---------------------------------------------------------------------------

// export async function streamChat(
//   { question, language = "auto", model = null, isRetry = false, context_session_id = null } = {},
//   { onSources, onToken, onLowConfidence, onFinal, onMap } = {},
//   signal = undefined,
//   _ownerRetried = false
// ) {
//   const res = await fetch(`${API_BASE}/chat/stream`, {
//     method: "POST",
//     headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...authHeaders() },
//     body: JSON.stringify({
//       session_id: getSessionId(),
//       user_id: getUserId(),
//       question,
//       language,
//       is_retry: isRetry,
//       ...(model ? { model } : {}),
//       ...(context_session_id ? { context_session_id } : {}),
//     }),
//     signal,
//   });

//   // Anonymous user landed on a session owned by an account — e.g. they were
//   // logged in earlier in this browser, then logged out, and the owned
//   // session_id still lingers in localStorage. The backend 403s to protect the
//   // account's saved history. Rather than blocking the user, mint a fresh
//   // anonymous session and retry once so anonymous chat just works.
//   if (res.status === 403 && !getSessionToken() && !_ownerRetried) {
//     newSession();
//     return streamChat(
//       { question, language, model, isRetry, context_session_id },
//       { onSources, onToken, onLowConfidence, onFinal, onMap },
//       signal,
//       true
//     );
//   }

//   if (!res.ok || !res.body) {
//     const err = new Error(`chat/stream failed: HTTP ${res.status}`);
//     err.status = res.status;
//     throw err;
//   }

//   const reader = res.body.getReader();
//   const decoder = new TextDecoder();
//   let buffer = "";

//   while (true) {
//     const { done, value } = await reader.read();
//     if (done) break;

//     buffer += decoder.decode(value, { stream: true });
//     // SSE frames are newline-delimited; the last element may be a partial
//     // line that continues in the next chunk — keep it in the buffer.
//     const lines = buffer.split("\n");
//     buffer = lines.pop();

//     for (const line of lines) {
//       if (!line.startsWith("data: ")) continue;
//       let evt;
//       try {
//         evt = JSON.parse(line.slice(6));
//       } catch {
//         continue; // malformed frame — skip rather than kill the stream
//       }
//       switch (evt.type) {
//         case "sources":        onSources?.(evt.sources); break;
//         case "token":          onToken?.(evt.token); break;
//         case "final":          onFinal?.(evt.text); break;   // link-injected answer
//         case "low_confidence": onLowConfidence?.(evt.message); break;
//         case "map":            onMap?.(evt.map); break; 
//         case "done":           return;
//         // "cache" is informational — tokens follow either way.
//       }
//     }
//   }
// }

// // ---------------------------------------------------------------------------
// // History / feedback
// // ---------------------------------------------------------------------------

// /** → {messages: [{role: "user"|"assistant", content: string, ...}]} */
// export const getHistory = () =>
//   request(`/history/${getSessionId()}`, { headers: authHeaders() });

// export const getSessions = () =>
//   request("/sessions", { headers: authHeaders() });   // user_id dropped; token decides

// export const getHistoryFor = (sessionId) =>
//   request(`/history/${sessionId}`, { headers: authHeaders() });

// export const renameSession = (sessionId, displayName) =>
//   request(`/sessions/${sessionId}/rename`, {
//     method: "PATCH",
//     headers: authHeaders(),
//     body: JSON.stringify({ display_name: displayName }),
//   });

// export const deleteSession = (sessionId) =>
//   request(`/sessions/${sessionId}`, { method: "DELETE", headers: authHeaders() });

// export const getSummaries = () => request("/summaries", { headers: authHeaders() });

// export const getSummary = (sessionId) =>
//   request(`/summary/${sessionId}`, { headers: authHeaders() });

// /** rating: 1 (thumbs up) | -1 (thumbs down). Question = the USER question
//  *  that produced the rated answer (backend evicts its cache entries on -1). */
// export const sendFeedback = (question, rating) =>
//   request("/feedback", {
//     method: "POST",
//     body: JSON.stringify({ session_id: getSessionId(), question, rating }),
//   });

// // ---------------------------------------------------------------------------
// // Preferences (anonymous, keyed by the localStorage user_id)
// // ---------------------------------------------------------------------------

// /** Canonical option lists: {modes, price_tiers, currencies, interests} */
// export const getPreferenceOptions = () => request("/preferences/options");

// /** Always 200; brand-new users get all-null fields + onboarded:false */
// export const getPreferences = () => request(`/preferences/${getUserId()}`);

// /** Partial upsert — omit any field to leave it unchanged on the server. */
// export const savePreferences = (prefs) =>
//   request(`/preferences/${getUserId()}`, {
//     method: "PUT",
//     body: JSON.stringify(prefs),
//   });

// export const deletePreferences = () =>
//   request(`/preferences/${getUserId()}`, { method: "DELETE" });

// // ---------------------------------------------------------------------------
// // Places — ready, but currently has no consumer in the new UI (cards are
// // demo-only until the chat emits structured place data).
// // Returns {found: bool, place: {name, rating, address, hours, maps_url, ...}}
// // ---------------------------------------------------------------------------

// export const searchPlace = (name) =>
//   request("/places/search", { method: "POST", body: JSON.stringify({ name }) });

// // Multi-result search for the Explore page. Categories are preset queries.
// // Returns { count, places: [{ name, rating, reviews, address, type, price,
// // open_now, maps_url, gps, ... }] }.
// export const explorePlaces = (query, limit = 12) =>
//   request("/places/explore", {
//     method: "POST",
//     body: JSON.stringify({ query, limit }),
//   });

// // Filtered semantic search over the OWNED OSM index (vector match + payload
// // filter on category/neighborhood/max_price). Returns {count, places:[{slug,
// // name, category, neighborhood, price_tier, interest_tags, gps}]}. Note these
// // rows have NO rating/open_now/address — OSM doesn't carry them; that's the
// // live-Google enrichment layer (a later increment). Use for category/filter
// // browsing over the whole dataset; use explorePlaces() for free-text + rich
// // Google cards.
// export const browsePlaces = (params) =>
//   request("/places/browse", {
//     method: "POST",
//     body: JSON.stringify(params),
//   });

// /** Personalized recommendations for a logged-in user. Returns {count, places, interests}. */
// export const getRecommendedPlaces = (userId, limit = 6) =>
//   request("/places/recommended", {
//     method: "POST",
//     body: JSON.stringify({ user_id: userId, limit }),
//   });
// // ---------------------------------------------------------------------------
// // City notes — cached live data for the Home "Smart Local Notes" cards.
// // Shape: { weather, exchange, departures, arrivals } — any section can be
// // null until the backend's first refresh completes; render placeholders.
// // ---------------------------------------------------------------------------

// export const getCityNotes = () => request("/city/notes");

// export const getNews = () => request("/city/news");

// /** Download a session's history as a plain-text file. */
// export async function downloadSession(sessionId, displayName) {
//   const { messages } = await getHistoryFor(sessionId);
//   const lines = messages.map((m) => {
//     const role = m.role === "user" ? "You" : "TiranaTips";
//     return `[${role}]\n${m.content}\n`;
//   });
//   const text = lines.join("\n---\n\n");
//   const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
//   const url = URL.createObjectURL(blob);
//   const a = document.createElement("a");
//   a.href = url;
//   a.download = `${displayName || "chat"}.txt`;
//   document.body.appendChild(a);
//   a.click();
//   document.body.removeChild(a);
//   URL.revokeObjectURL(url);
// }

// // Upcoming events for the Explore page — from the same ingested events table
// // the chat uses. {count, events:[{title, description, category, start_date,
// // end_date, venue, image_url, ticket_url, source_url}]}.
// export const getEvents = (days = 30, category = null, municipality = null) => {
//   const qs = new URLSearchParams({ days });
//   if (category) qs.set("category", category);
//   if (municipality) qs.set("municipality", municipality);
//   return request(`/events?${qs.toString()}`);
// };

// // ---------------------------------------------------------------------------
// // Authentication — pure-frontend, no backend calls.
// // Re-exported from ./auth.js which validates against local users.json.
// // ---------------------------------------------------------------------------

// export { login, register, logout, checkSession, getSessionToken, getUserProfile, getUserLanguage } from "./auth.js";


// const authHeaders = () => {
//   const token = getSessionToken();
//   return token ? { Authorization: `Bearer ${token}` } : {};
// };
 
// export const savePlace = (slug, payload = null) =>
//   request("/saves", {
//     method: "POST",
//     headers: authHeaders(),
//     body: JSON.stringify(payload ? { slug, payload } : { slug }),
//   });
 
// export const unsavePlace = (slug) =>
//   request(`/saves/${encodeURIComponent(slug)}`, {
//     method: "DELETE",
//     headers: authHeaders(),
//   });
 
// export const getSavedPlaces = () =>
//   request("/saves", { headers: authHeaders() });
 
// export const getSavedSlugs = () =>
//   request("/saves/slugs", { headers: authHeaders() });

// /** Collaborative recommendations: places that users who saved `slug` also saved.
//  * Returns {count, places: [{slug, name, category, neighborhood, co_save_count, ...}]} */
// export const getAlsoSaved = (slug, limit = 4) =>
//   request("/places/also-saved", {
//     method: "POST",
//     body: JSON.stringify({ slug, limit }),
//   });


// export const getStoredLanguage = () => {
//   return localStorage.getItem("tiranatips_language");
// };

// export const updateLanguage = (language) =>
//   request("/auth/language", {
//     method: "PATCH",
//     headers: authHeaders(),
//     body: JSON.stringify({ language }),
//   });

// export const setStoredLanguage = (language) => {
//   localStorage.setItem("tiranatips_language", language);
// };



// src/lib/api.js
// Single place where the frontend talks to the FastAPI backend.
import { getSessionToken } from "./auth.js";


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

// The account id (written by auth.js on login, under "tiranatips_user_id")
// wins when present, so preferences follow the logged-in account. Anonymous
// browsing gets its own stable key — otherwise a fresh anon id used to be
// minted into the account key and then wiped on logout.
export const getUserId = () => {
  const accountId = localStorage.getItem("tiranatips_user_id");
  if (accountId) return accountId;
  return getOrCreateId("tiranatips_anon_id");
};
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

export async function request(path, options = {}) {
  const { headers, ...rest } = options;
  const res = await fetch(`${API_BASE}${path}`, {
    // Merge caller headers onto the JSON default. Spreading `...options`
    // directly let a caller's `headers` (e.g. authHeaders()) replace the whole
    // object and drop Content-Type, so body-bearing POSTs (e.g. /saves) were
    // sent without a JSON content-type and rejected with 422.
    headers: { "Content-Type": "application/json", ...headers },
    ...rest,
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
//   final          → {text: "..."}                       (link-injected answer; REPLACES)
//   low_confidence → {message: "..."}                    (fallback message)
//   done           → stream finished
// The model now replies directly in the user's language, so the old
// 'translation'/'generating' events are gone — tokens stream live in-language
// and the 'final' event swaps in the Maps-link-injected version at the end.
// ---------------------------------------------------------------------------

export async function streamChat(
  { question, language = "auto", model = null, isRetry = false, context_session_id = null } = {},
  { onSources, onToken, onLowConfidence, onFinal, onMap } = {},
  signal = undefined,
  _ownerRetried = false
) {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...authHeaders() },
    body: JSON.stringify({
      session_id: getSessionId(),
      user_id: getUserId(),
      question,
      language,
      is_retry: isRetry,
      ...(model ? { model } : {}),
      ...(context_session_id ? { context_session_id } : {}),
    }),
    signal,
  });

  // Anonymous user landed on a session owned by an account — e.g. they were
  // logged in earlier in this browser, then logged out, and the owned
  // session_id still lingers in localStorage. The backend 403s to protect the
  // account's saved history. Rather than blocking the user, mint a fresh
  // anonymous session and retry once so anonymous chat just works.
  if (res.status === 403 && !getSessionToken() && !_ownerRetried) {
    newSession();
    return streamChat(
      { question, language, model, isRetry, context_session_id },
      { onSources, onToken, onLowConfidence, onFinal, onMap },
      signal,
      true
    );
  }

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
        case "final":          onFinal?.(evt.text); break;   // link-injected answer
        case "low_confidence": onLowConfidence?.(evt.message); break;
        case "map":            onMap?.(evt.map); break; 
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
export const getHistory = () =>
  request(`/history/${getSessionId()}`, { headers: authHeaders() });

export const getSessions = () =>
  request("/sessions", { headers: authHeaders() });   // user_id dropped; token decides

export const getHistoryFor = (sessionId) =>
  request(`/history/${sessionId}`, { headers: authHeaders() });

export const renameSession = (sessionId, displayName) =>
  request(`/sessions/${sessionId}/rename`, {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify({ display_name: displayName }),
  });

export const deleteSession = (sessionId) =>
  request(`/sessions/${sessionId}`, { method: "DELETE", headers: authHeaders() });

export const getSummaries = () => request("/summaries", { headers: authHeaders() });

export const getSummary = (sessionId) =>
  request(`/summary/${sessionId}`, { headers: authHeaders() });

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
export const getPreferences = () =>
  request(`/preferences/${getUserId()}`, { headers: authHeaders() });

/** Partial upsert — omit any field to leave it unchanged on the server. */
export const savePreferences = (prefs) =>
  request(`/preferences/${getUserId()}`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(prefs),
  });

export const deletePreferences = () =>
  request(`/preferences/${getUserId()}`, { method: "DELETE", headers: authHeaders() });

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

/** Personalized recommendations for a logged-in user. Returns {count, places, interests}. */
export const getRecommendedPlaces = (userId, limit = 6) =>
  request("/places/recommended", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, limit }),
  });
// ---------------------------------------------------------------------------
// City notes — cached live data for the Home "Smart Local Notes" cards.
// Shape: { weather, exchange, departures, arrivals } — any section can be
// null until the backend's first refresh completes; render placeholders.
// ---------------------------------------------------------------------------

export const getCityNotes = () => request("/city/notes");

export const getNews = () => request("/city/news");

/** Download a session's history as a plain-text file. */
export async function downloadSession(sessionId, displayName) {
  const { messages } = await getHistoryFor(sessionId);
  const lines = messages.map((m) => {
    const role = m.role === "user" ? "You" : "TiranaTips";
    return `[${role}]\n${m.content}\n`;
  });
  const text = lines.join("\n---\n\n");
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${displayName || "chat"}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Upcoming events for the Explore page — from the same ingested events table
// the chat uses. {count, events:[{title, description, category, start_date,
// end_date, venue, image_url, ticket_url, source_url}]}.
export const getEvents = (days = 30, category = null, municipality = null) => {
  const qs = new URLSearchParams({ days });
  if (category) qs.set("category", category);
  if (municipality) qs.set("municipality", municipality);
  return request(`/events?${qs.toString()}`);
};

// ---------------------------------------------------------------------------
// Authentication — pure-frontend, no backend calls.
// Re-exported from ./auth.js which validates against local users.json.
// ---------------------------------------------------------------------------

export { login, register, logout, checkSession, getSessionToken, getUserProfile, getUserLanguage } from "./auth.js";


const authHeaders = () => {
  const token = getSessionToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
};
 
export const savePlace = (slug, payload = null) =>
  request("/saves", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(payload ? { slug, payload } : { slug }),
  });
 
export const unsavePlace = (slug) =>
  request(`/saves/${encodeURIComponent(slug)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
 
export const getSavedPlaces = () =>
  request("/saves", { headers: authHeaders() });
 
export const getSavedSlugs = () =>
  request("/saves/slugs", { headers: authHeaders() });

/** Collaborative recommendations: places that users who saved `slug` also saved.
 * Returns {count, places: [{slug, name, category, neighborhood, co_save_count, ...}]} */
export const getAlsoSaved = (slug, limit = 4) =>
  request("/places/also-saved", {
    method: "POST",
    body: JSON.stringify({ slug, limit }),
  });


export const getStoredLanguage = () => {
  return localStorage.getItem("tiranatips_language");
};

export const updateLanguage = (language) =>
  request("/auth/language", {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify({ language }),
  });

export const setStoredLanguage = (language) => {
  localStorage.setItem("tiranatips_language", language);
};