"use client";

import { FileText, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { EmptyState } from "@/components/molecules/empty-state";
import { cn } from "@/lib/utils";
import { useCaseFiles } from "../hooks";
import { useCaseUpload } from "../hooks/useCaseUpload";
import { ACCEPTED_TYPES } from "../types";

/**
 * Organism: the matter's files, and the way to add one.
 *
 * Text is extracted at upload rather than at question time, so an
 * unreadable file fails while the reader is still looking at it. That is
 * why this reports the backend's own message on failure -- it is what
 * distinguishes an un-OCR'd scan from an unsupported type.
 */
export function DocumentUpload({ caseId }: { caseId: string }) {
  const { files, error: loadError, isLoading } = useCaseFiles(caseId);
  const { upload, isUploading, error } = useCaseUpload(caseId);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  return (
    <section>
      <label
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          const file = event.dataTransfer.files[0];
          if (file) void upload(file);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center gap-2 rounded-md border border-dashed border-line-strong bg-surface-sunken px-6 py-8 text-center transition-colors duration-[120ms] ease-out",
          over && "border-primary bg-surface-tint",
          isUploading && "opacity-60",
        )}
      >
        <input
          ref={input}
          type="file"
          accept={ACCEPTED_TYPES}
          className="sr-only"
          disabled={isUploading}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void upload(file);
            // Cleared so picking the same file twice fires again.
            event.target.value = "";
          }}
        />
        <Upload className="size-5 text-ink-muted" />
        <span className="text-sm font-medium text-ink">
          {isUploading ? "Reading the file…" : "Drop a document, or click to choose"}
        </span>
        <span className="text-xs text-ink-muted">
          PDF, DOCX, TXT or MD, up to 25MB. Text is extracted now, not later.
        </span>
      </label>

      {error && <p className="mt-2 text-sm text-danger">{error}</p>}

      <div className="mt-4">
        {isLoading && <EmptyState message="Loading documents…" />}
        {!isLoading && loadError && (
          <EmptyState message="Could not load this matter's documents." />
        )}
        {!isLoading && !loadError && files.length === 0 && (
          <EmptyState message="No documents yet." />
        )}
        {!isLoading && !loadError && files.length > 0 && (
          <ul className="divide-y divide-line rounded-md border border-line bg-surface-card">
            {files.map((file) => (
              <li
                key={file.document_id}
                className="flex items-center gap-3 px-4 py-3"
              >
                <FileText className="size-4 shrink-0 text-ink-muted" />
                <span className="truncate text-sm text-ink">{file.filename}</span>
                {/* Said plainly: an upload is the client's, and a corpus
                    search someone else runs must never return it. */}
                <span className="caps ml-auto shrink-0 rounded-sm bg-prov-document-bg px-2 py-0.5 text-prov-document">
                  Your document
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
