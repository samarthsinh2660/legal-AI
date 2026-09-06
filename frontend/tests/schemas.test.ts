/**
 * The Zod boundary.
 *
 * Every service parses here, so a backend shape change fails at the seam
 * with a clear error instead of arriving as `undefined` three components
 * later. These parse payloads captured from the running API.
 */

import { describe, expect, it } from "vitest";

import {
  ActiveRunSchema,
  AnswerSchema,
  MessageSchema,
  StartedRunSchema,
  ThreadSchema,
} from "@/features/thread/types";
import { CaseSchema } from "@/features/case/types";
import { NeighbourhoodSchema } from "@/features/graph/types";
import { paged } from "@/types/common";
import recorded from "./fixtures/reply.json";

describe("threads", () => {
  const thread = {
    thread_id: "t1",
    title: "Refund for late possession",
    case_id: null,
    created_at: "2026-09-01T10:56:42.740438+00:00",
    updated_at: "2026-09-01T10:56:42.740438+00:00",
  };

  it("accepts the thread the API returns", () => {
    expect(ThreadSchema.parse(thread).thread_id).toBe("t1");
  });

  it("carries the run in flight, and what kind it is", () => {
    const parsed = ThreadSchema.parse({
      ...thread,
      active_run: {
        run_id: "r1",
        kind: "research",
        status: "running",
        current_step: "analyst",
      },
    });
    expect(parsed.active_run?.current_step).toBe("analyst");
  });

  it("defaults active_run to null for a thread with nothing running", () => {
    expect(ThreadSchema.parse(thread).active_run).toBeNull();
  });

  it("accepts what sending a message returns", () => {
    expect(
      StartedRunSchema.parse({
        run_id: "r1",
        thread_id: "t1",
        status: "queued",
      }).run_id,
    ).toBe("r1");
  });

  it("refuses a run of a kind the client cannot render", () => {
    expect(
      ActiveRunSchema.safeParse({
        run_id: "r1",
        kind: "something_new",
        status: "running",
        current_step: null,
      }).success,
    ).toBe(false);
  });

  it("accepts an offset page, which is what this backend sends", () => {
    const page = paged(ThreadSchema).parse({
      items: [thread],
      total: 1,
      limit: 20,
      offset: 0,
      has_more: false,
    });
    expect(page.has_more).toBe(false);
  });

  it("rejects a cursor page, so a shape change cannot pass silently", () => {
    expect(
      paged(ThreadSchema).safeParse({
        data: [thread],
        pagination: { hasNext: false, nextCursor: 0 },
      }).success,
    ).toBe(false);
  });
});

describe("messages", () => {
  it("accepts an assistant turn carrying a structured answer", () => {
    const parsed = MessageSchema.parse({
      message_id: 4,
      role: "assistant",
      content: "text",
      answer: recorded.answer,
      created_at: "2026-09-01T11:03:14Z",
    });
    expect(parsed.role).toBe("assistant");
  });

  it("accepts a turn with no answer at all", () => {
    expect(
      MessageSchema.safeParse({
        message_id: 1,
        role: "user",
        content: "q",
        created_at: "2026-09-01T11:03:14Z",
      }).success,
    ).toBe(true);
  });

  it("refuses a role the UI has no branch for", () => {
    expect(
      MessageSchema.safeParse({
        message_id: 1,
        role: "system",
        content: "q",
        created_at: "2026-09-01T11:03:14Z",
      }).success,
    ).toBe(false);
  });
});

describe("the recorded answer", () => {
  it("parses whole", () => {
    expect(AnswerSchema.safeParse(recorded.answer).success).toBe(true);
  });

  it("keeps all four verdict buckets as separate fields", () => {
    const answer = AnswerSchema.parse(recorded.answer);
    expect(answer).toHaveProperty("key_elements");
    expect(answer).toHaveProperty("partially_supported");
    expect(answer).toHaveProperty("needs_verification");
    expect(answer).toHaveProperty("unchecked");
  });
});

describe("the graph", () => {
  it("takes truncated from the server rather than inferring it", () => {
    const parsed = NeighbourhoodSchema.parse({
      nodes: [{ id: "judgment:a", kind: "Judgment", title: "A", hops: 0 }],
      edges: [],
      truncated: true,
    });
    expect(parsed.truncated).toBe(true);
  });

  it("accepts a node label the client has not seen before", () => {
    // Neo4j could grow a label; refusing to draw the graph over it would
    // be worse than colouring one dot with the fallback.
    expect(
      NeighbourhoodSchema.safeParse({
        nodes: [{ id: "x", kind: "Tribunal", title: null, hops: 1 }],
        edges: [],
        truncated: false,
      }).success,
    ).toBe(true);
  });
});

describe("cases", () => {
  it("accepts a case with every optional field null", () => {
    const parsed = CaseSchema.parse({
      case_id: "c1",
      title: "Sharma v. Skyline",
      court: null,
      state: null,
      case_number: null,
      parties: [],
      matter_type: null,
      status: null,
      description: null,
      created_at: "2026-09-01T11:18:20Z",
      updated_at: "2026-09-01T11:18:20Z",
    });
    expect(parsed.title).toBe("Sharma v. Skyline");
  });
});
