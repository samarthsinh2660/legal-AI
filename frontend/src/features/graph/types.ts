import { z } from "zod";

/** What a node is. Drives its colour and its shape in the canvas. */
export const NodeKind = z.enum(["Judgment", "Section", "Act", "Court"]);
export type NodeKind = z.infer<typeof NodeKind>;

export const EdgeKind = z.enum([
  "CITES",
  "CITES_SECTION",
  "CONTAINS",
  "DECIDED_BY",
]);
export type EdgeKind = z.infer<typeof EdgeKind>;

export const GraphNodeSchema = z.object({
  id: z.string(),
  // Neo4j could grow a label the client has not heard of. Falling back
  // beats refusing to draw the graph.
  kind: z.string(),
  title: z.string().nullable(),
  hops: z.number(),
});

export const GraphEdgeSchema = z.object({
  source: z.string(),
  target: z.string(),
  kind: z.string(),
});

export const NeighbourhoodSchema = z.object({
  nodes: z.array(GraphNodeSchema),
  edges: z.array(GraphEdgeSchema),
  /** The server's own answer, not inferred from a count. A graph quietly
   *  missing half its edges is a picture that lies about how connected
   *  something is. */
  truncated: z.boolean(),
});

export type GraphNode = z.infer<typeof GraphNodeSchema>;
export type GraphEdge = z.infer<typeof GraphEdgeSchema>;
export type Neighbourhood = z.infer<typeof NeighbourhoodSchema>;

/** Backend caps (`src/api/graph/repository.py`). Mirrored so the controls
 *  cannot offer a value the server will silently clamp. */
export const MAX_HOPS = 2;
export const MAX_NODES = 120;

export const SearchHitSchema = z.object({
  document_id: z.string(),
  kind: z.string(),
  title: z.string(),
  citation: z.string().nullable().optional(),
  court: z.string().nullable().optional(),
});

export type SearchHit = z.infer<typeof SearchHitSchema>;
