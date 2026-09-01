import { z } from "zod";

/** `kind` on the wire (`GET /search?kind=`). */
export enum SearchKind {
  All = "all",
  Judgment = "judgment",
  Section = "section",
}

export const SearchResultSchema = z.object({
  document_id: z.string(),
  kind: z.string(),
  title: z.string(),
  citation: z.string().nullable().optional(),
  court: z.string().nullable().optional(),
  extract: z.string().nullable().optional(),
});

export type SearchResult = z.infer<typeof SearchResultSchema>;

/** The backend's ceiling (`GET /search?limit=`). */
export const MAX_RESULTS = 50;
