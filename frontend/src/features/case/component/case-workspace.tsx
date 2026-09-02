"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/molecules/confirm-dialog";
import { EmptyState } from "@/components/molecules/empty-state";
import { PageLoader } from "@/components/molecules/loading";
import { SectionHead } from "@/components/molecules/section-head";
import { useCase, useDeleteCase } from "../hooks";
import { DocumentUpload } from "./document-upload";
import { CaseThreads } from "./case-threads";

/**
 * Organism: one matter and everything hanging off it.
 *
 * Screen 5b in design/UX_FLOWS.md. The timeline and the issues board that
 * screen also describes are not here: `case_findings` has no read route,
 * so there is nothing behind them yet.
 */
export function CaseWorkspace({ caseId }: { caseId: string }) {
  const { item, error, isLoading } = useCase(caseId);
  const { caseDelete, isDeleting } = useDeleteCase();
  const [confirming, setConfirming] = useState(false);
  const router = useRouter();

  if (isLoading) return <PageLoader />;
  if (error || !item) {
    return <EmptyState message="That case does not exist, or is not yours." />;
  }

  return (
    <div className="mx-auto w-full max-w-4xl">
      <Link
        href="/cases"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-ink-muted transition-colors duration-[120ms] ease-out hover:text-ink"
      >
        <ArrowLeft className="size-4" />
        All cases
      </Link>

      <header className="mb-8 flex items-start justify-between gap-4">
        <div className="min-w-0">
          {item.matter_type && <span className="caps text-ink-muted">{item.matter_type}</span>}
          <h1 className="mt-1 text-title">{item.title}</h1>
          <p className="mono mt-2 text-sm text-ink-muted">
            {[item.court, item.case_number].filter(Boolean).join(" · ") ||
              "No court on record"}
          </p>
        </div>
        <Button
          variant="ghost"
          disabled={isDeleting}
          onClick={() => setConfirming(true)}
          className="shrink-0 text-danger hover:bg-danger-bg hover:text-danger"
        >
          <Trash2 className="size-4" />
          Delete
        </Button>
      </header>

      {item.description && (
        <section className="mb-8">
          <SectionHead>Context</SectionHead>
          <div className="rounded-md border border-line bg-surface-card p-6">
            <p className="text-sm leading-[1.7] text-ink-variant">
              {item.description}
            </p>
            {/* Not decoration: this text is prepended to every thread in
                the matter, and the reader should know that it is. */}
            <p className="mt-3 text-xs text-ink-muted">
              Every research thread attached to this case starts from this.
            </p>
          </div>
        </section>
      )}

      <section className="mb-8">
        <SectionHead>Documents</SectionHead>
        <DocumentUpload caseId={caseId} />
      </section>

      <section>
        <SectionHead>Research threads</SectionHead>
        <CaseThreads caseId={caseId} />
      </section>

      {/* What survives is named, because it is the surprising half: the
          backend detaches the threads rather than deleting them. */}
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Delete ${item.title}?`}
        description="Its documents and findings are deleted for good. Research threads are kept, detached from the matter."
        confirmLabel="Delete case"
        isBusy={isDeleting}
        onConfirm={async () => {
          await caseDelete(caseId);
          router.push("/cases");
        }}
      />
    </div>
  );
}
