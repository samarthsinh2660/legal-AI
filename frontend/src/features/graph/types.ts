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
  /** Nodes in the whole slice. Sent on the first batch only, so a reader
   *  can tell 100 of 36,887 from 100 of 100. */
  total: z.number().nullable().optional(),
});

export type GraphNode = z.infer<typeof GraphNodeSchema>;
export type GraphEdge = z.infer<typeof GraphEdgeSchema>;
export type Neighbourhood = z.infer<typeof NeighbourhoodSchema>;

/** Backend caps (`src/api/graph/repository.py`). Mirrored so the controls
 *  cannot offer a value the server will silently clamp. */
export const MAX_NODES = 120;

/** Nodes per batch. The graph is 50,890 nodes; a force layout stops being
 *  readable long before that, so the reader asks for the next hundred
 *  rather than being handed everything. */
export const BATCH = 100;

/** The slices a reader can ask for. `view` is either one of these or an
 *  Act id, which shows that Act's own sections. */
export const VIEWS = [
  { id: "judgments", label: "Judgments" },
  { id: "statutes", label: "Statutes" },
  { id: "act:ipc-1860", label: "Indian Penal Code" },
  { id: "act:crpc-1973", label: "CrPC" },
  { id: "act:iea-1872", label: "Evidence Act" },
  { id: "act:20062", label: "Bharatiya Nyaya Sanhita" },
] as const;
