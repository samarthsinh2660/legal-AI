"use client";

/** The profile screen's own data and edit state. Only that screen uses it. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { RequestError } from "@/lib/api";
import * as authService from "../services";
import { NAME_MAX_LENGTH } from "../types";
import { useAuth } from "./useAuth";

export function useProfile() {
  const { setName, setEmail } = useAuth();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, error: loadError } = useQuery({
    queryKey: ["profile"],
    queryFn: authService.profile,
    // `created_at` never changes and the name changes here; nothing else
    // writes it, so there is nothing to poll for.
    staleTime: 5 * 60 * 1000,
  });

  const { mutateAsync, isPending } = useMutation({
    mutationFn: authService.rename,
    onSuccess: (updated) => {
      queryClient.setQueryData(["profile"], updated);
      // The sidebar reads the session, not this query.
      setName(updated.name ?? "");
    },
  });

  // Null means "not editing"; the stored name is shown instead.
  const editing = draft !== null;

  // The address is edited behind its own confirmation, because moving it
  // takes the account with it -- see `controller.change_email`.
  const [emailDraft, setEmailDraft] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);

  const emailMutation = useMutation({
    mutationFn: ({ email, secret }: { email: string; secret: string }) =>
      authService.changeEmail(email, secret),
    onSuccess: (updated) => {
      queryClient.setQueryData(["profile"], updated);
      setEmail(updated.email);
    },
  });

  const saveEmail = useCallback(async () => {
    const next = (emailDraft ?? "").trim();
    if (!next.includes("@")) {
      setEmailError("A valid email is required.");
      return;
    }
    if (!password) {
      setEmailError("Your current password is required.");
      return;
    }
    try {
      await emailMutation.mutateAsync({ email: next, secret: password });
      setEmailDraft(null);
      setPassword("");
      setEmailError(null);
    } catch (caught) {
      setEmailError(
        caught instanceof RequestError
          ? caught.message
          : "Could not change the address. Try again.",
      );
    }
  }, [emailDraft, password, emailMutation]);

  const save = useCallback(async () => {
    const name = (draft ?? "").trim();
    if (!name) {
      setError("A name is required.");
      return;
    }
    if (name.length > NAME_MAX_LENGTH) {
      setError(`At most ${NAME_MAX_LENGTH} characters.`);
      return;
    }
    try {
      await mutateAsync(name);
      setDraft(null);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof RequestError
          ? caught.message
          : "Could not save. Try again.",
      );
    }
  }, [draft, mutateAsync]);

  return {
    profile: data,
    isLoading,
    loadError,
    editing,
    draft: draft ?? "",
    error,
    isSaving: isPending,
    startEditing: () => {
      setDraft(data?.name ?? "");
      setError(null);
    },
    cancel: () => {
      setDraft(null);
      setError(null);
    },
    setDraft,
    save,

    editingEmail: emailDraft !== null,
    emailDraft: emailDraft ?? "",
    setEmailDraft,
    password,
    setPassword,
    emailError,
    isSavingEmail: emailMutation.isPending,
    startEditingEmail: () => {
      setEmailDraft(data?.email ?? "");
      setPassword("");
      setEmailError(null);
    },
    cancelEmail: () => {
      setEmailDraft(null);
      setPassword("");
      setEmailError(null);
    },
    saveEmail,
  };
}
