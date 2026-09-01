import { QuickActions } from "@/components/molecules/quick-actions";
import { SectionHead } from "@/components/molecules/section-head";
import { Greeting } from "@/features/auth/component/greeting";
import { AskBox } from "@/features/thread/component/ask-box";
import { RecentThreads } from "@/features/thread/component/recent-threads";

/**
 * Screen 2 in design/UX_FLOWS.md. Composes organisms; builds no UI.
 *
 * `?case=` arrives from a case workspace: the same ask box, but the
 * thread it creates belongs to that matter. `searchParams` is a Promise
 * in Next 16.
 */
export default async function HomePage(props: PageProps<"/">) {
  const { case: caseId } = await props.searchParams;
  const attachTo = typeof caseId === "string" ? caseId : undefined;

  return (
    <div className="mx-auto w-full max-w-5xl">
      <Greeting />
      <AskBox caseId={attachTo} />

      <div className="mt-10 grid gap-8 lg:grid-cols-[1.6fr_1fr]">
        <section>
          <SectionHead>Recent research</SectionHead>
          <RecentThreads />
        </section>
        <section>
          <SectionHead>Quick actions</SectionHead>
          <QuickActions />
        </section>
      </div>
    </div>
  );
}
