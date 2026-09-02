/** Where the API lives.
 *
 *  Read from `NEXT_PUBLIC_API_BASE_URL` at build time, defaulting to the
 *  local API. It is still baked into the bundle -- that is what
 *  NEXT_PUBLIC_ means -- so changing it needs a rebuild either way. The
 *  variable exists so a deploy can set it in CI instead of editing this
 *  file, which was the only way to point the app at anything but
 *  localhost. */
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

/** Where the access token is kept. One name, so nothing goes stale in a
 *  second place when logout clears it. */
export const TOKEN_KEY = "pramana_token";
