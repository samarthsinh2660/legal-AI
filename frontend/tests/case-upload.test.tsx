/**
 * What the upload control refuses before it sends anything.
 *
 * The server checks all of this too. Doing it here as well is not
 * duplication for its own sake: a 25MB file rejected after the upload
 * wastes the whole wait, and the reader learns nothing sooner.
 */

import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { useCaseUpload } from "@/features/case/hooks/useCaseUpload";
import { MAX_UPLOAD_BYTES } from "@/features/case/types";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

function fileOf(name: string, bytes = 10) {
  return new File(["x".repeat(bytes)], name);
}

function ok() {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      success: true,
      data: { document_id: "case-file:c1:a.pdf", filename: "a.pdf", characters: 10 },
    }),
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("what it accepts", () => {
  it.each(["deed.pdf", "notice.docx", "notes.txt", "brief.md", "DEED.PDF"])(
    "accepts %s",
    async (name) => {
      const fetchMock = ok();
      vi.stubGlobal("fetch", fetchMock);
      const { result } = renderHook(() => useCaseUpload("c1"), { wrapper });

      let accepted: boolean | undefined;
      await act(async () => {
        accepted = await result.current.upload(fileOf(name));
      });

      expect(accepted).toBe(true);
      expect(fetchMock).toHaveBeenCalled();
    },
  );
});

describe("what it refuses without sending", () => {
  it("refuses a type the extractor cannot read", async () => {
    const fetchMock = ok();
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useCaseUpload("c1"), { wrapper });

    await act(async () => {
      await result.current.upload(fileOf("scan.jpeg"));
    });

    expect(result.current.error).toMatch(/PDF, DOCX, TXT or MD/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refuses a file over the limit before spending the upload", async () => {
    const fetchMock = ok();
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useCaseUpload("c1"), { wrapper });

    await act(async () => {
      await result.current.upload(fileOf("huge.pdf", MAX_UPLOAD_BYTES + 1));
    });

    expect(result.current.error).toMatch(/25MB/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("accepts a file exactly at the limit", async () => {
    const fetchMock = ok();
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useCaseUpload("c1"), { wrapper });

    await act(async () => {
      await result.current.upload(fileOf("edge.pdf", MAX_UPLOAD_BYTES));
    });

    expect(result.current.error).toBeNull();
    expect(fetchMock).toHaveBeenCalled();
  });
});

describe("when the server refuses it", () => {
  it("shows the backend's message, which says why", async () => {
    // Only the server can tell an un-OCR'd scan from an unsupported type.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({
          success: false,
          error: {
            code: "invalid_request",
            message: "That PDF has no text layer.",
          },
        }),
      }),
    );
    const { result } = renderHook(() => useCaseUpload("c1"), { wrapper });

    let accepted: boolean | undefined;
    await act(async () => {
      accepted = await result.current.upload(fileOf("scan.pdf"));
    });

    expect(accepted).toBe(false);
    expect(result.current.error).toBe("That PDF has no text layer.");
  });

  it("clears the previous error when the next attempt starts", async () => {
    const { result } = renderHook(() => useCaseUpload("c1"), { wrapper });

    await act(async () => {
      await result.current.upload(fileOf("bad.jpeg"));
    });
    expect(result.current.error).not.toBeNull();

    vi.stubGlobal("fetch", ok());
    await act(async () => {
      await result.current.upload(fileOf("good.pdf"));
    });
    expect(result.current.error).toBeNull();
  });
});
