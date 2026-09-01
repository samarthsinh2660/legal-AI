import { z } from "zod";

/**
 * A research thread. Mirrors `ThreadModel` in
 * `src/api/threads/schemas.py` -- and nothing more. The reference design
 * also showed a source count, a jurisdiction chip and a "Completed" status
 * on each row; the API returns none of those, so the UI does not show
 * them. Inventing them would be the same defect the backend spends its
 * effort avoiding, one layer up.
 */
export const ThreadSchema = z.object({
  thread_id: z.string(),
  title: z.string(),
  case_id: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type Thread = z.infer<typeof ThreadSchema>;

/** The backend's ceiling for one message (`MessageRequest.message`). */
export const QUESTION_MAX_LENGTH = 4000;

/**
 * How hard to check the answer before returning it
 * (`MessageRequest.verification_level`). Two values, not three: the
 * backend accepts "quick" and "verified" only.
 *
 * Quick still verifies that every citation exists -- what it skips is
 * whether the source actually supports the claim, which is the expensive
 * half and the one the answer reports as `support_not_checked`.
 */
export enum Verification {
  Quick = "quick",
  Verified = "verified",
}

export const MessageSchema = z.object({
  message_id: z.number(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  answer: z.record(z.string(), z.unknown()).nullable().optional(),
  created_at: z.string(),
});

export type Message = z.infer<typeof MessageSchema>;

export const ReplySchema = z.object({
  text: z.string().nullable().optional(),
  answer: z.record(z.string(), z.unknown()).nullable().optional(),
  clarification_needed: z.string().nullable().optional(),
  route: z.enum(["ANSWER", "RESEARCH"]),
  verification_level: z.string().nullable().optional(),
});

export type Reply = z.infer<typeof ReplySchema>;

/**
 * One finished graph node. `node` is the stable key -- `label` is prose
 * the backend may reword, so nothing keys off it.
 */
export type ProgressStep = { node: string; label: string };

export const ClaimSchema = z.object({
  text: z.string(),
  evidence_ids: z.array(z.string()),
  paragraph: z.string().nullable().optional(),
});

export type Claim = z.infer<typeof ClaimSchema>;

/**
 * The structured answer (`src/legal_ai/schemas/answer.py`).
 *
 * The four claim buckets are four different facts and the UI must never
 * merge them:
 *
 *   key_elements        checked, and the source supports it
 *   partially_supported the source is narrower than the claim
 *   needs_verification  the evidence is AGAINST the claim
 *   unchecked           nobody looked
 *
 * Collapsing `unchecked` into `needs_verification` presents an unexamined
 * claim as a refuted one -- or, the other way round, hands a reader a
 * refutation dressed as an open question.
 */
export const AnswerSchema = z.object({
  question: z.string(),
  lede: z.string(),
  key_elements: z.array(ClaimSchema),
  applicable_law: z.array(z.string()),
  key_judgments: z.array(z.string()),
  needs_verification: z.array(z.string()),
  unchecked: z.array(z.string()),
  partially_supported: z.array(z.string()),
  /** Semantic verification did not run -- the reader asked for quick mode.
   *  Reported once at the answer level: a caveat printed against every
   *  line is one readers learn to skip, and the citations WERE checked. */
  support_not_checked: z.boolean(),
  citations: z.array(z.string()),
  disclaimer: z.string(),
});

export type Answer = z.infer<typeof AnswerSchema>;
