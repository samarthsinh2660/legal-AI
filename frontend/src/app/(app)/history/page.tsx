import type { Metadata } from "next";

import { ThreadHistory } from "@/features/thread/component/thread-history";

export const metadata: Metadata = { title: "History · Pramāṇa AI" };

/** Composes only. Every state belongs to the organism. */
export default function HistoryPage() {
  return (
    <main className="mx-auto w-full max-w-4xl px-6 py-8">
      <h1 className="text-heading font-semibold text-ink">History</h1>
      <p className="mt-1.5 mb-6 text-ink-variant">
        Every question you have asked. Open one to read the answer or carry
        it on.
      </p>
      <ThreadHistory />
    </main>
  );
}
