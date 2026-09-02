import { GraphExplorer } from "@/features/graph/component/graph-explorer";

/**
 * Screen 8 in design/UX_FLOWS.md. `searchParams` is a Promise in Next 16
 * -- there is no synchronous form left.
 */
export default async function GraphPage(props: PageProps<"/graph">) {
  const { anchor } = await props.searchParams;

  return (
    <GraphExplorer
      initialAnchor={typeof anchor === "string" ? anchor : undefined}
    />
  );
}
