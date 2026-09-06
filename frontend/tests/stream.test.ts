/**
 * The SSE reader.
 *
 * The subtle failure here is chunk boundaries: the network splits frames
 * wherever it likes, and a parser that assumes one chunk is one frame
 * drops steps or throws on half a JSON object. The frame format asserted
 * below was taken off the wire from the running API, not from the docs.
 *
 * One reader now serves both cases -- the turn this tab asked for and a run
 * it found already going -- so these frames are the whole client contract.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { watchRun } from "@/features/thread/services";

/** Serve `chunks` as a byte stream, exactly as fetch would. */
function streamOf(chunks: string[], ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    body: new ReadableStream({
      start(controller) {
        const encoder = new TextEncoder();
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    }),
  });
}

const STEP =
  'id: 1\nevent: step\ndata: {"node": "research", "label": "Searching statutes and judgments"}\n\n';
const DONE =
  'id: 2\nevent: done\ndata: {"text": "An answer.", "route": "RESEARCH"}\n\n';

async function collect(
  fetchMock: ReturnType<typeof streamOf>,
  since = 0,
) {
  vi.stubGlobal("fetch", fetchMock);
  const events = [];
  for await (const event of watchRun("r1", since)) events.push(event);
  return events;
}

afterEach(() => vi.unstubAllGlobals());

describe("frames", () => {
  it("reads a step and a done from one chunk", async () => {
    const events = await collect(streamOf([STEP + DONE]));
    expect(events.map((e) => e.type)).toEqual(["step", "done"]);
  });

  it("reassembles a frame split across chunks", async () => {
    // The exact break that loses a step if the buffer is not kept.
    const whole = STEP + DONE;
    const events = await collect(
      streamOf([whole.slice(0, 30), whole.slice(30, 90), whole.slice(90)]),
    );
    expect(events.map((e) => e.type)).toEqual(["step", "done"]);
  });

  it("survives a break in the middle of a JSON payload", async () => {
    const events = await collect(
      streamOf([
        'id: 4\nevent: step\ndata: {"node": "res',
        'earch", "label": "x"}\n\n',
      ]),
    );
    expect(events).toEqual([
      { type: "step", seq: 4, step: { node: "research", label: "x" } },
    ]);
  });

  it("yields every step of a full run in order", async () => {
    const nodes = [
      "document",
      "context_builder",
      "clarification",
      "research",
      "analyst",
      "verification",
      "draft",
    ];
    const frames = nodes.map(
      (node, index) =>
        `id: ${index + 1}\nevent: step\ndata: {"node": "${node}", "label": "l"}\n\n`,
    );
    const events = await collect(streamOf([...frames, DONE]));

    expect(events).toHaveLength(8);
    expect(
      events.flatMap((e) => (e.type === "step" ? [e.step.node] : [])),
    ).toEqual(nodes);
  });

  it("carries the seq, which is what a reconnect resumes from", async () => {
    const events = await collect(streamOf([STEP + DONE]));
    expect(events.map((e) => ("seq" in e ? e.seq : null))).toEqual([1, 2]);
  });

  it("reads the lede's chunks", async () => {
    const events = await collect(
      streamOf(['id: 3\nevent: answer_chunk\ndata: {"text": "A bail "}\n\n']),
    );
    expect(events).toEqual([{ type: "answer_chunk", seq: 3, text: "A bail " }]);
  });
});

describe("outcomes", () => {
  it("surfaces a server error event as an error, not a done", async () => {
    const events = await collect(
      streamOf([
        'event: error\ndata: {"code": "timeout", "message": "Took too long."}\n\n',
      ]),
    );
    expect(events).toEqual([{ type: "error", message: "Took too long." }]);
  });

  it("reports a non-200 without trying to read a body that is not there", async () => {
    const events = await collect(streamOf([], false, 503));
    expect(events).toEqual([
      { type: "error", message: "The server answered 503." },
    ]);
  });

  it("ignores a keep-alive comment frame", async () => {
    const events = await collect(streamOf([": ping\n\n" + DONE]));
    expect(events.map((e) => e.type)).toEqual(["done"]);
  });
});

describe("the request", () => {
  it("resumes from the last event seen", async () => {
    const fetchMock = streamOf([DONE]);
    await collect(fetchMock, 7);
    expect(fetchMock.mock.calls[0][1].headers["Last-Event-ID"]).toBe("7");
  });

  it("sends no resume header on a first attach", async () => {
    const fetchMock = streamOf([DONE]);
    await collect(fetchMock, 0);
    expect(fetchMock.mock.calls[0][1].headers["Last-Event-ID"]).toBeUndefined();
  });
});
