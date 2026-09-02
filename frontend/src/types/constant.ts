export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** Where the access token is kept. One name, so nothing goes stale in a
 *  second place when logout clears it. */
export const TOKEN_KEY = "pramana_token";
