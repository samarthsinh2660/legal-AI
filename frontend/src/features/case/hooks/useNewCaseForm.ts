"use client";

/** The New Case form. Only the cases screen uses it, so it is its own
 *  file; it wraps `useCreateCase` and never calls the service. */

import { useCallback, useState } from "react";

import { RequestError } from "@/lib/api";
import { useCreateCase } from "./index";
import { TITLE_MAX_LENGTH, type NewCase } from "../types";

const EMPTY: NewCase = { title: "", matter_type: "", court: "", description: "" };

type Errors = Partial<Record<keyof NewCase | "form", string>>;

export function useNewCaseForm(onCreated?: () => void) {
  const [form, setForm] = useState<NewCase>(EMPTY);
  const [errors, setErrors] = useState<Errors>({});
  const { caseCreate, isCreating } = useCreateCase();

  const handleChange = useCallback((field: keyof NewCase, value: string) => {
    setForm((previous) => ({ ...previous, [field]: value }));
    setErrors((previous) => ({ ...previous, [field]: undefined, form: undefined }));
  }, []);

  const handleSubmit = useCallback(async () => {
    // Collect every error before setting state, so the form does not
    // reveal its problems one at a time.
    const found: Errors = {};
    if (!form.title.trim()) found.title = "A case needs a title";
    if (form.title.length > TITLE_MAX_LENGTH) {
      found.title = `Titles are limited to ${TITLE_MAX_LENGTH} characters`;
    }
    if (Object.keys(found).length) {
      setErrors(found);
      return;
    }

    try {
      // Empty optional strings are dropped rather than sent as "": the
      // column is nullable, and "" is not the same fact as unknown.
      await caseCreate({
        title: form.title.trim(),
        matter_type: form.matter_type?.trim() || undefined,
        court: form.court?.trim() || undefined,
        description: form.description?.trim() || undefined,
      });
      setForm(EMPTY);
      onCreated?.();
    } catch (caught) {
      setErrors({
        form:
          caught instanceof RequestError
            ? caught.message
            : "Could not create the case.",
      });
    }
  }, [form, caseCreate, onCreated]);

  return { form, errors, isCreating, handleChange, handleSubmit };
}
