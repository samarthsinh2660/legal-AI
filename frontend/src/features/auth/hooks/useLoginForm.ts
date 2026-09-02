"use client";

/**
 * Form state, validation and submit for the login screen -- and only that
 * screen, which is why it is its own file rather than part of
 * `hooks/index.ts`. It wraps `useAuth`; it never calls the service.
 */

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { RequestError } from "@/lib/api";
import type { Credentials } from "@/types/auth";
import { useAuth } from "./useAuth";
import { PASSWORD_MIN_LENGTH } from "../types";

type Errors = Partial<Record<keyof Credentials | "form", string>>;

export function useLoginForm(mode: "signIn" | "signUp") {
  const { signIn, signUp } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState<Credentials>({ email: "", password: "", name: "" });
  const [errors, setErrors] = useState<Errors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleChange = useCallback(
    (field: keyof Credentials, value: string) => {
      setForm((previous) => ({ ...previous, [field]: value }));
      // Clear this field's error as the user fixes it, but keep the others.
      setErrors((previous) => ({ ...previous, [field]: undefined, form: undefined }));
    },
    [],
  );

  const handleSubmit = useCallback(async () => {
    const found: Errors = {};
    // Sign-up only: it is what the sidebar shows, so asking for it once
    // here beats showing an address to everyone forever.
    if (mode === "signUp" && !form.name?.trim()) found.name = "Name is required";
    if (!form.email.trim()) found.email = "Email is required";
    // Only on sign-up. Telling someone signing in that their password is
    // too short reveals it is not the stored one.
    if (mode === "signUp" && form.password.length < PASSWORD_MIN_LENGTH) {
      found.password = `At least ${PASSWORD_MIN_LENGTH} characters`;
    }
    if (!form.password) found.password = "Password is required";
    if (Object.keys(found).length) {
      setErrors(found);
      return;
    }

    setIsSubmitting(true);
    try {
      await (mode === "signIn" ? signIn(form) : signUp(form));
      router.push("/dashboard");
    } catch (error) {
      // The backend's message is already written for a reader and reveals
      // nothing -- an unknown address and a wrong password answer alike.
      setErrors({
        form:
          error instanceof RequestError
            ? error.message
            : "Something went wrong. Try again.",
      });
    } finally {
      setIsSubmitting(false);
    }
  }, [form, mode, router, signIn, signUp]);

  return { form, errors, isSubmitting, handleChange, handleSubmit };
}
