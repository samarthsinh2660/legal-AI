/**
 * The one HTTP client. Every call to the backend goes through here.
 *
 * The backend envelopes every response (docs/API.md §2):
 *
 *     { "success": true,  "data": ... }
 *     { "success": false, "error": { "code", "message" } }
 *
 * This unwraps it, so a service sees the payload and nothing else. A
 * `success: false` body becomes a thrown `RequestError` carrying the
 * backend's own `code` -- which is what callers branch on, not the HTTP
 * status, because the code is stable and the status is coarse.
 */

import { API_BASE_URL, TOKEN_KEY } from "@/types/constant";

export class RequestError extends Error {
  /** The backend's error code, e.g. "unauthorized", "rate_limited". */
  code: string;
  status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "RequestError";
    this.code = code;
    this.status = status;
  }
}

type Envelope<T> =
  | { success: true; data: T }
  | { success: false; error: { code: string; message: string } };

export function readToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const token = readToken();

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        ...(options.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
  } catch {
    // fetch only rejects when the request never happened -- offline, DNS,
    // CORS. Distinct from a server that answered with an error.
    throw new RequestError(
      "Could not reach the server.",
      "network_error",
      0,
    );
  }

  // A 502 from a proxy is not enveloped, so parsing can fail on a real
  // response. Both paths have to produce a RequestError, not a SyntaxError.
  let body: Envelope<T>;
  try {
    body = (await response.json()) as Envelope<T>;
  } catch {
    throw new RequestError(
      `Server returned ${response.status}.`,
      "bad_response",
      response.status,
    );
  }

  if (!body.success) {
    throw new RequestError(
      body.error.message,
      body.error.code,
      response.status,
    );
  }
  return body.data;
}

export const apiClient = {
  get: <T>(endpoint: string) => request<T>(endpoint),
  post: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, {
      method: "POST",
      body: data === undefined ? undefined : JSON.stringify(data),
    }),
  patch: <T>(endpoint: string, data: unknown) =>
    request<T>(endpoint, { method: "PATCH", body: JSON.stringify(data) }),
  delete: <T>(endpoint: string) => request<T>(endpoint, { method: "DELETE" }),

  /** Multipart upload -- Content-Type is left to the browser so it can set
   *  the multipart boundary. */
  upload: <T>(endpoint: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<T>(endpoint, { method: "POST", body: form });
  },
};
