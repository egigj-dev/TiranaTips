// src/lib/auth.js
// Backend-authenticated sessions. Replaces the old client-side users.json
// approach — accounts now live server-side (durable, cross-device, properly
// hashed) and link to user_preferences for personalization. Same exported
// names as before, so App.jsx and Login.jsx don't change.

import { request } from "./api";

const TOKEN_KEY = "tiranatips_session_token";
const USER_KEY = "tiranatips_user_id";
const LANG_KEY = "tiranatips_language";

export function getSessionToken() {
  return localStorage.getItem(TOKEN_KEY);
}

/** The logged-in account's user_id, or null. Personalization (preferences,
 *  language) is keyed on this — so prefs follow the account across devices. */
export function getUserId() {
  return localStorage.getItem(USER_KEY);
}

/** The user's stored language preference from their last login/register.
 *  Falls back to "auto" (detect per-request) when no account is linked. */
export function getUserLanguage() {
  return localStorage.getItem(LANG_KEY) || "auto";
}

function store(data) {
  localStorage.setItem(TOKEN_KEY, data.token);
  localStorage.setItem(USER_KEY, data.user_id);
  if (data.language) {
    localStorage.setItem(LANG_KEY, data.language);
  }
}

function clearStorage() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(LANG_KEY);
}


/** Log in against the backend. Returns { display_name }. Throws on failure. */
export async function login(username, password) {
  const data = await request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  store(data);
  return { display_name: data.display_name };
}
 
/** Register a new account, then it's immediately logged in. */
export async function register(username, password, displayName, language = "en") {
  const data = await request("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      username,
      password,
      display_name: displayName || username,
      language: language || "en",
    }),
  });
  store(data);
  return { display_name: data.display_name };
}
 
/** Fetch the authenticated user's full profile from the backend.
 *  Returns {authenticated, user_id, username, display_name, language}
 *  or null if not logged in. */
export async function getUserProfile() {
  const token = getSessionToken();
  if (!token) return null;
  try {
    return await request("/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    return null;
  }
}

/** Validate the stored token with the backend. Returns true if a valid
 *  session exists. Public browsing doesn't require this — it only gates
 *  personalization features. */
export async function checkSession() {
  const token = getSessionToken();
  if (!token) return false;
  try {
    await request("/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    return true;
  } catch {
    // Token invalid/expired — clear it.
    clearStorage();
    return false;
  }
}

export async function logout() {
  clearStorage();
}