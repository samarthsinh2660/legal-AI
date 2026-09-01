import { QuickActions } from "@/components/molecules/quick-actions";
import { SectionHead } from "@/components/molecules/section-head";
import { Greeting } from "@/features/auth/component/greeting";
import { AskBox } from "@/features/thread/component/ask-box";
import { RecentThreads } from "@/features/thread/component/recent-threads";

/** Screen 2 in design/UX_FLOWS.md. Composes organisms; builds no UI. */
export default function HomePage() {
  return (
    <div className="mx-auto w-full max-w-5xl">
      <Greeting />
      <AskBox />

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
