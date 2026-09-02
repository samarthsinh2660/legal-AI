/**
 * The stored session: the token and who it belongs to.
 *
 * Both are persisted so a page load can restore the session without asking
 * the server. `/auth/login` returns the identity alongside the token, so
 * what is stored here is the server's own answer rather than something the
 * client decoded and chose to believe.
 *
 * Expiry is read from the token's own `exp`. That is a claim the user could
 * edit, so it is trusted for exactly one thing: deciding not to bother. A
 * forged later `exp` buys nothing -- the signature is checked server-side
 * and every request still 401s.
 */

import { TOKEN_KEY } from "@/types/constant";
import { UserSchema, type User } from "./types";

const USER_KEY = "pramana_user";

// Subscribers are React's, through `useSyncExternalStore`. localStorage is
// an external store, and treating it as one is what lets the session be
// read during render instead of assigned in an effect -- which React
// Compiler rejects, because a synchronous setState there cascades a second
// render before paint.
const listeners = new Set<() => void>();

export function subscribe(listener: () => void) {
  listeners.add(listener);
  // `storage` fires in the *other* tabs. Signing out in one therefore signs
  // out the rest, rather than leaving a stale header behind a dead token.
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function announce() {
  for (const listener of listeners) listener();
}

export function save(token: string, user: User) {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  cached = { raw: null, user: null };
  announce();
}

/** Replace the stored name, keeping the token. Called after a successful
 *  save so the sidebar reflects it without a re-login. */
export function rename(name: string) {
  patch({ name });
}

/** Replace fields of the stored identity, keeping the token. */
function patch(fields: Partial<User>) {
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return;
  const current = UserSchema.safeParse(tryParse(raw));
  if (!current.success) return;
  window.localStorage.setItem(
    USER_KEY,
    JSON.stringify({ ...current.data, ...fields }),
  );
  cached = { raw: null, user: null };
  announce();
}

export function setEmail(email: string) {
  patch({ email });
}

export function clear() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
  cached = { raw: null, user: null };
  announce();
}

/** Seconds since the epoch at which the token stops being accepted, or null
 *  when it carries no readable `exp`. */
function expiryOf(token: string): number | null {
  const payload = token.split(".")[1];
  if (!payload) return null;
  try {
    const claims = JSON.parse(
      atob(payload.replace(/-/g, "+").replace(/_/g, "/")),
    );
    return typeof claims.exp === "number" ? claims.exp : null;
  } catch {
    return null;
  }
}

// `useSyncExternalStore` compares snapshots by identity and re-renders on
// any change, so parsing a fresh object each read would loop forever. The
// raw strings are the identity; the parsed user is derived from them once.
let cached: { raw: string | null; user: User | null } = { raw: null, user: null };

/** The stored session, or null when there is none or it has expired.
 *
 *  A token with no readable `exp` is discarded rather than kept: it is not
 *  one we issued, and treating it as valid forever is the wrong way to be
 *  wrong. */
export function read(): User | null {
  const token = window.localStorage.getItem(TOKEN_KEY);
  const raw = window.localStorage.getItem(USER_KEY);
  if (!token || !raw) return null;

  const key = `${token}\u0000${raw}`;
  if (cached.raw === key) return cached.user;

  const expiry = expiryOf(token);
  const parsed = UserSchema.safeParse(tryParse(raw));
  if (expiry === null || expiry * 1000 <= Date.now() || !parsed.success) {
    clear();
    return null;
  }

  cached = { raw: key, user: parsed.data };
  return parsed.data;
}

/** Null during the server render, where there is no localStorage. The first
 *  client render therefore matches the server's, and the real session
 *  arrives on the store's first notification. */
export function serverSnapshot(): User | null {
  return null;
}

function tryParse(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
