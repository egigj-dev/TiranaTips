// src/lib/auth.js
// Pure-frontend authentication — no backend calls.
// Reads users from a local JSON file, hashes passwords with SHA-256,
// and keeps session tokens in localStorage.

import users from "../data/users.json";

const TOKEN_KEY = "tiranatips_session_token";

/** SHA-256 hash a string, return hex digest. */
async function sha256(text) {
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Generate a random session token. */
function generateToken() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Return the stored session token, or null. */
export function getSessionToken() {
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Validate credentials against the local users list.
 * On success, stores a session token and returns { token, display_name }.
 * On failure, throws an Error.
 */
export async function login(username, password) {
  console.log("[auth] login: checking credentials for user:", username);

  const user = users.find(
    (u) => u.username.toLowerCase() === username.toLowerCase()
  );
  if (!user) {
    console.warn("[auth] login: user not found:", username);
    throw new Error("Invalid username or password.");
  }

  const hash = await sha256(password);
  console.log("[auth] login: computed hash:", hash);
  console.log("[auth] login: expected hash:", user.password_hash);

  if (hash !== user.password_hash) {
    console.warn("[auth] login: password mismatch for user:", username);
    throw new Error("Invalid username or password.");
  }

  const token = generateToken();
  localStorage.setItem(TOKEN_KEY, token);
  console.log("[auth] login: success, token stored, display_name:", user.display_name);

  return { token, display_name: user.display_name };
}

/**
 * Check whether a valid session token exists.
 * Since tokens are stateless (no server to validate against),
 * we just check that one is present in localStorage.
 */
export async function checkSession() {
  const token = getSessionToken();
  const valid = !!token;
  console.log("[auth] checkSession: token present =", valid);
  return valid;
}

/** Clear the session token. */
export async function logout() {
  console.log("[auth] logout: clearing token");
  localStorage.removeItem(TOKEN_KEY);
}
