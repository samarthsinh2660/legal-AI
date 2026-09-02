/**
 * The one HTTP client.
 *
 * Every request in the app goes through here, so the envelope contract
 * and the error shape are worth pinning: a caller branches on the
 * backend's `code`, and a thrown SyntaxError instead of a RequestError
 * would reach the UI as an unhandled crash.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RequestError, apiClient, readToken } from "@/lib/api";
import { TOKEN_KEY } from "@/types/constant";

function respondWith(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({
    ok: status < 400,
    status,
    json: async () => body,
  });
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("unwrapping", () => {
  it("hands the service the payload, not the envelope", async () => {
    vi.stubGlobal("fetch", respondWith({ success: true, data: { id: 7 } }));
    await expect(apiClient.get("/x")).resolves.toEqual({ id: 7 });
  });

  it("passes a null payload through rather than treating it as failure", async () => {
    vi.stubGlobal("fetch", respondWith({ success: true, data: null }));
    await expect(apiClient.get("/x")).resolves.toBeNull();
  });
});

describe("failures", () => {
  it("throws the backend's own code, which is what callers branch on", async () => {
    vi.stubGlobal(
      "fetch",
      respondWith(
        { success: false, error: { code: "rate_limited", message: "Slow down." } },
        429,
      ),
    );
    await expect(apiClient.get("/x")).rejects.toMatchObject({
      code: "rate_limited",
      message: "Slow down.",
      status: 429,
    });
  });

  it("reports an unreachable server distinctly from one that answered", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));
    await expect(apiClient.get("/x")).rejects.toMatchObject({
      code: "network_error",
      status: 0,
    });
  });

  it("turns unparseable output into a RequestError, never a SyntaxError", async () => {
    // A proxy's own 502 page is HTML, and it is a real response.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => {
          throw new SyntaxError("Unexpected token <");
        },
      }),
    );
    const caught: unknown = await apiClient.get("/x").catch((error) => error);
    expect(caught).toBeInstanceOf(RequestError);
    expect((caught as RequestError).code).toBe("bad_response");
  });

  it("still surfaces the error body on a 4xx, not just the status", async () => {
    vi.stubGlobal(
      "fetch",
      respondWith(
        { success: false, error: { code: "email_taken", message: "Already registered." } },
        409,
      ),
    );
    await expect(apiClient.post("/auth/register", {})).rejects.toMatchObject({
      code: "email_taken",
    });
  });
});

describe("the token", () => {
  it("is attached when one is stored", async () => {
    window.localStorage.setItem(TOKEN_KEY, "abc123");
    const fetchMock = respondWith({ success: true, data: null });
    vi.stubGlobal("fetch", fetchMock);

    await apiClient.get("/x");

    const headers = fetchMock.mock.calls[0][1].headers;
    expect(headers.Authorization).toBe("Bearer abc123");
  });

  it("is absent, not empty, when there is no session", async () => {
    const fetchMock = respondWith({ success: true, data: null });
    vi.stubGlobal("fetch", fetchMock);

    await apiClient.get("/x");

    expect(fetchMock.mock.calls[0][1].headers).not.toHaveProperty(
      "Authorization",
    );
  });

  it("reads back what was stored", () => {
    window.localStorage.setItem(TOKEN_KEY, "xyz");
    expect(readToken()).toBe("xyz");
  });
});

describe("bodies", () => {
  it("sends JSON with a JSON content type", async () => {
    const fetchMock = respondWith({ success: true, data: null });
    vi.stubGlobal("fetch", fetchMock);

    await apiClient.post("/x", { a: 1 });

    const options = fetchMock.mock.calls[0][1];
    expect(options.headers["Content-Type"]).toBe("application/json");
    expect(options.body).toBe('{"a":1}');
  });

  it("leaves the content type off a FormData upload so the browser can set the boundary", async () => {
    const fetchMock = respondWith({ success: true, data: null });
    vi.stubGlobal("fetch", fetchMock);

    await apiClient.upload("/x", new File(["hi"], "a.txt"));

    expect(fetchMock.mock.calls[0][1].headers).not.toHaveProperty(
      "Content-Type",
    );
  });
});
