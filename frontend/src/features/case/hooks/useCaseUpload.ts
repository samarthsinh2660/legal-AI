"use client";

/** The upload control's own state: the picked file, what it refuses, and
 *  the error a rejected file produces. Only the case workspace uses it. */

import { useCallback, useState } from "react";

import { RequestError } from "@/lib/api";
import { useUploadCaseFile } from "./index";
import { MAX_UPLOAD_BYTES } from "../types";

const ALLOWED = /\.(pdf|docx|txt|md)$/i;

export function useCaseUpload(caseId: string) {
  const { fileUpload, isUploading } = useUploadCaseFile(caseId);
  const [error, setError] = useState<string | null>(null);

  const upload = useCallback(
    async (file: File) => {
      setError(null);

      // Checked here as well as server-side: a 25MB file rejected after
      // the upload wastes the wait, and the reader learns nothing sooner.
      if (!ALLOWED.test(file.name)) {
        setError("PDF, DOCX, TXT or MD only.");
        return false;
      }
      if (file.size > MAX_UPLOAD_BYTES) {
        setError("That file is over the 25MB limit.");
        return false;
      }

      try {
        await fileUpload(file);
        return true;
      } catch (caught) {
        // The backend's message is the useful one here -- it distinguishes
        // an un-OCR'd scan from an unsupported type, which the client
        // cannot tell apart.
        setError(
          caught instanceof RequestError
            ? caught.message
            : "The upload failed.",
        );
        return false;
      }
    },
    [fileUpload],
  );

  return { upload, isUploading, error };
}
