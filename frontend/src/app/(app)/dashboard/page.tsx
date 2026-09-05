import { QuickActions } from "@/components/molecules/quick-actions";
import { SectionHead } from "@/components/molecules/section-head";
import { Greeting } from "@/features/auth/component/greeting";
import { AskBox } from "@/features/thread/component/ask-box";
import { RecentThreads } from "@/features/thread/component/recent-threads";

/**
 * Screen 2 in design/UX_FLOWS.md -- the ask box and recent research.
 * Composes organisms; builds no UI. "Home" is the landing page at `/`.
 *
 * `?case=` arrives from a case workspace: the same ask box, but the
 * thread it creates belongs to that matter. `searchParams` is a Promise
 * in Next 16.
 */
export default async function DashboardPage(props: PageProps<"/dashboard">) {
  const { case: caseId } = await props.searchParams;
  const attachTo = typeof caseId === "string" ? caseId : undefined;

  return (
    <div className="mx-auto w-full max-w-5xl">
      <Greeting />
      <AskBox caseId={attachTo} />

      {/* min-w-0 on both columns, or neither truncates. A grid item sizes
          to its content by default, and a nowrap title's min-content width
          is the whole title -- so one long question widened the research
          column and squeezed the actions beside it out of shape. */}
      <div className="mt-10 grid gap-8 lg:grid-cols-[1.6fr_1fr]">
        <section className="min-w-0">
          <SectionHead>Recent research</SectionHead>
          <RecentThreads />
        </section>
        <section className="min-w-0">
          <SectionHead>Quick actions</SectionHead>
          <QuickActions />
        </section>
      </div>
    </div>
  );
}
