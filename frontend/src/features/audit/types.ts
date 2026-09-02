import { z } from "zod";

/** One line in the trail. Mirrors `AuditEventModel` in
 *  `src/api/audit/schemas.py`. Carries no question, answer or document
 *  text -- see docs/API.md §4.4. */
export const AuditEventSchema = z.object({
  event_id: z.number(),
  action: z.string(),
  resource_type: z.string(),
  resource_id: z.string().nullable().optional(),
  status: z.number(),
  at: z.string(),
});

export type AuditEvent = z.infer<typeof AuditEventSchema>;

/** The backend's ceiling (`PageParams`). */
export const MAX_LIMIT = 100;
