/**
 * Renaming and deleting a thread.
 *
 * The title is all a user may edit: a thread is the record of what was
 * asked and what the system answered, and a rewritten question above the
 * old answer would be a false record. The backend has no route for it
 * either, so this only checks the title path.
 */

import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { useThreadActions } from "@/features/thread/hooks/useThreadActions";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renamed(title: string) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      success: true,
      data: {
        thread_id: "t1",
        title,
        case_id: null,
        created_at: "2026-09-01T10:00:00Z",
        updated_at: "2026-09-01T10:00:00Z",
      },
    }),
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("renaming", () => {
  it("sends the new title and leaves edit mode", async () => {
    const fetchMock = renamed("Refund claim");
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useThreadActions("t1", "Old"), {
      wrapper,
    });

    act(() => result.current.startEditing());
    act(() => result.current.setDraft("Refund claim"));
    await act(async () => {
      await result.current.save();
    });

    const options = fetchMock.mock.calls[0][1];
    expect(options.method).toBe("PATCH");
    expect(JSON.parse(options.body)).toEqual({ title: "Refund claim" });
    expect(result.current.editing).toBe(false);
  });

  it("refuses an empty title rather than leaving a row nobody can identify", async () => {
    const fetchMock = renamed("");
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useThreadActions("t1", "Old"), {
      wrapper,
    });

    act(() => result.current.startEditing());
    act(() => result.current.setDraft("   "));
    await act(async () => {
      await result.current.save();
    });

    expect(result.current.error).toMatch(/needs a title/i);
    expect(fetchMock).not.toHaveBeenCalled();
    // Still editing: the user has to fix it, not lose their edit.
    expect(result.current.editing).toBe(true);
  });

  it("spends no request when the title did not change", async () => {
    const fetchMock = renamed("Old");
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useThreadActions("t1", "Old"), {
      wrapper,
    });

    act(() => result.current.startEditing());
    await act(async () => {
      await result.current.save();
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.editing).toBe(false);
  });

  it("trims before comparing, so whitespace is not a change", async () => {
    const fetchMock = renamed("Old");
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useThreadActions("t1", "Old"), {
      wrapper,
    });

    act(() => result.current.startEditing());
    act(() => result.current.setDraft("  Old  "));
    await act(async () => {
      await result.current.save();
    });

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps the user in edit mode when the server refuses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({
          success: false,
          error: { code: "not_found", message: "No such thread." },
        }),
      }),
    );
    const { result } = renderHook(() => useThreadActions("t1", "Old"), {
      wrapper,
    });

    act(() => result.current.startEditing());
    act(() => result.current.setDraft("New"));
    await act(async () => {
      await result.current.save();
    });

    expect(result.current.error).toBe("No such thread.");
    expect(result.current.editing).toBe(true);
  });

  it("starts each edit from the current title, not the last abandoned draft", () => {
    const { result } = renderHook(() => useThreadActions("t1", "Current"), {
      wrapper,
    });

    act(() => result.current.startEditing());
    act(() => result.current.setDraft("abandoned"));
    act(() => result.current.cancel());
    act(() => result.current.startEditing());

    expect(result.current.draft).toBe("Current");
  });
});

describe("deleting", () => {
  it("is a real delete, and reports that it happened", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true, data: { deleted: "t1" } }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useThreadActions("t1", "Old"), {
      wrapper,
    });

    let done: boolean | undefined;
    await act(async () => {
      done = await result.current.remove();
    });

    expect(done).toBe(true);
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
  });

  it("reports a failure rather than pretending the row is gone", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({
          success: false,
          error: { code: "server_error", message: "boom" },
        }),
      }),
    );
    const { result } = renderHook(() => useThreadActions("t1", "Old"), {
      wrapper,
    });

    let done: boolean | undefined;
    await act(async () => {
      done = await result.current.remove();
    });

    expect(done).toBe(false);
    expect(result.current.error).toMatch(/could not delete/i);
  });
});
