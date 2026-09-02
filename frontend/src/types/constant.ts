/** Where the API lives. A constant, not an environment variable: the value
 *  is baked into the bundle at build time either way, so an env var bought
 *  nothing a redeploy does not already require. Change it here. */
export const API_BASE_URL = "http://localhost:8000";

/** Where the access token is kept. One name, so nothing goes stale in a
 *  second place when logout clears it. */
export const TOKEN_KEY = "pramana_token";
