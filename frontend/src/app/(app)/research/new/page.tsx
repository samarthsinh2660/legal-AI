import { NewResearch } from "@/features/thread/component/new-research";

/**
 * An empty chat, the way every other assistant opens one.
 *
 * Its own route so "New Research" always does something visible, even when
 * the reader is already on the dashboard. No thread is created until the
 * first question is sent, so clicking it repeatedly leaves nothing behind.
 */
export default function NewResearchPage() {
  return <NewResearch />;
}
