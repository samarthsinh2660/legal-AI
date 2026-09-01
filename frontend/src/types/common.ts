/**
 * Types used by two or more features. Anything only one feature touches
 * belongs in that feature's own `types.ts`.
 */

import { z, type ZodType } from "zod";

/**
 * The backend's page shape (`api/utils/pagination.py`). Offset-based, and
 * `has_more` is computed server-side -- a client that infers it from
 * `items.length < limit` reads a short last page as "there must be more"
 * and loops.
 */
export function paged<T extends ZodType>(item: T) {
  return z.object({
    items: z.array(item),
    total: z.number(),
    limit: z.number(),
    offset: z.number(),
    has_more: z.boolean(),
  });
}

export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

/** Where a claim came from -- the product's core idiom. Rendered as a
 *  badge everywhere a source appears; see design/DESIGN_SYSTEM.md. */
export enum Provenance {
  Static = "static",
  Dynamic = "dynamic",
  Document = "document",
}
