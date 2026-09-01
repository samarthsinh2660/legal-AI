import { ResearchThread } from "@/features/thread/component/research-thread";

/**
 * Screen 3, in its first form: the conversation and the progress pane.
 * The source panel, the verification toggle and the citation drawer that
 * design/UX_FLOWS.md also puts on this screen are not built yet.
 *
 * `params` and `searchParams` are Promises in Next 16 -- there is no
 * synchronous form left.
 */
export default async function ResearchPage(
  props: PageProps<"/research/[threadId]">,
) {
  const { threadId } = await props.params;
  const { ask } = await props.searchParams;

  return (
    <ResearchThread
      threadId={threadId}
      initialQuestion={typeof ask === "string" ? ask : undefined}
    />
  );
}
