import { ResearchThread } from "@/features/thread/component/research-thread";
import { Verification } from "@/features/thread/types";

/**
 * The research thread, in its first form: the conversation and the
 * progress pane. The source panel and the citation drawer the design also
 * puts on this screen are not built yet.
 *
 * `params` and `searchParams` are Promises in Next 16 -- there is no
 * synchronous form left.
 */
export default async function ResearchPage(
  props: PageProps<"/research/[threadId]">,
) {
  const { threadId } = await props.params;
  const { ask, mode } = await props.searchParams;

  return (
    <ResearchThread
      threadId={threadId}
      initialQuestion={typeof ask === "string" ? ask : undefined}
      initialMode={mode === "verified" ? Verification.Verified : Verification.Quick}
    />
  );
}
