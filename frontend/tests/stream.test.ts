/**
 * The SSE reader.
 *
 * The subtle failure here is chunk boundaries: the network splits frames
 * wherever it likes, and a parser that assumes one chunk is one frame
 * drops steps or throws on half a JSON object. The frame format asserted
 * below was taken off the wire from the running API, not from the docs.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { streamMessage } from "@/features/thread/services";
import { Verification } from "@/features/thread/types";

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

const STEP = 'event: step\ndata: {"node": "research", "label": "Searching statutes and judgments"}\n\n';
const DONE =
  'event: done\ndata: {"text": "An answer.", "answer": null, "clarification_needed": null, "route": "RESEARCH", "verification_level": "verified"}\n\n';

async function collect(fetchMock: ReturnType<typeof streamOf>) {
  vi.stubGlobal("fetch", fetchMock);
  const events = [];
  for await (const event of streamMessage("t1", "q", Verification.Verified)) {
    events.push(event);
  }
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
      streamOf(['event: step\ndata: {"node": "res', 'earch", "label": "x"}\n\n']),
    );
    expect(events).toEqual([
      { type: "step", step: { node: "research", label: "x" } },
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
      (node) => `event: step\ndata: {"node": "${node}", "label": "l"}\n\n`,
    );
    const events = await collect(streamOf([...frames, DONE]));

    expect(events).toHaveLength(8);
    expect(
      events.filter((e) => e.type === "step").map((e) => e.step.node),
    ).toEqual(nodes);
  });
});

describe("outcomes", () => {
  it("parses the done payload against the reply schema", async () => {
    const events = await collect(streamOf([DONE]));
    expect(events[0]).toMatchObject({
      type: "done",
      reply: { route: "RESEARCH", text: "An answer." },
    });
  });

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
    const events = await collect(streamOf([": keep-alive\n\n" + DONE]));
    expect(events.map((e) => e.type)).toEqual(["done"]);
  });
});

describe("the request", () => {
  it("sends the chosen verification level", async () => {
    const fetchMock = streamOf([DONE]);
    await collect(fetchMock);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ message: "q", verification_level: "verified" });
  });
});
