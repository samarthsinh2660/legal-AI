"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Page } from "@/types/common";
import {
  attachThread,
  createCase,
  deleteCase,
  fetchCase,
  fetchCaseFiles,
  fetchCases,
  uploadCaseFile,
} from "../services";
import type { Case, CaseFile, NewCase } from "../types";

export const caseKeys = {
  all: ["cases"] as const,
  page: (limit: number, offset: number) =>
    [...caseKeys.all, { limit, offset }] as const,
};

export function useCases(limit = 20, offset = 0) {
  const { data, error, isLoading } = useQuery({
    queryKey: caseKeys.page(limit, offset),
    queryFn: () => fetchCases(limit, offset),
    staleTime: 60_000,
  });

  return {
    cases: data?.items ?? [],
    total: data?.total ?? 0,
    error,
    isLoading,
  };
}

export function useCreateCase() {
  const queryClient = useQueryClient();

  const { mutateAsync, isPending } = useMutation({
    mutationFn: (payload: NewCase) => createCase(payload),
    onSuccess: (created) => {
      // Prepend rather than refetch: the list is newest-first and this is
      // the newest.
      queryClient.setQueriesData<Page<Case>>(
        { queryKey: caseKeys.all },
        (old) =>
          old
            ? { ...old, items: [created, ...old.items], total: old.total + 1 }
            : old,
      );
    },
  });

  return { caseCreate: mutateAsync, isCreating: isPending };
}

export function useCase(caseId: string) {
  const { data: item, error, isLoading } = useQuery({
    queryKey: [...caseKeys.all, caseId],
    queryFn: () => fetchCase(caseId),
    enabled: Boolean(caseId),
  });
  return { item, error, isLoading };
}

export function useCaseFiles(caseId: string) {
  const { data, error, isLoading } = useQuery({
    queryKey: [...caseKeys.all, caseId, "documents"],
    queryFn: () => fetchCaseFiles(caseId),
    enabled: Boolean(caseId),
  });
  return { files: data ?? [], error, isLoading };
}

export function useUploadCaseFile(caseId: string) {
  const queryClient = useQueryClient();

  const { mutateAsync, isPending } = useMutation({
    mutationFn: (file: File) => uploadCaseFile(caseId, file),
    onSuccess: (uploaded) => {
      queryClient.setQueryData<CaseFile[]>(
        [...caseKeys.all, caseId, "documents"],
        (old = []) => [
          ...old,
          { document_id: uploaded.document_id, filename: uploaded.filename },
        ],
      );
    },
  });

  return { fileUpload: mutateAsync, isUploading: isPending };
}

export function useDeleteCase() {
  const queryClient = useQueryClient();

  const { mutateAsync, isPending } = useMutation({
    mutationFn: (caseId: string) => deleteCase(caseId),
    onSuccess: (_result, caseId) => {
      queryClient.setQueriesData<Page<Case>>(
        { queryKey: caseKeys.all },
        (old) =>
          old
            ? {
                ...old,
                items: old.items.filter((item) => item.case_id !== caseId),
                total: Math.max(0, old.total - 1),
              }
            : old,
      );
    },
  });

  return { caseDelete: mutateAsync, isDeleting: isPending };
}

export function useAttachThread(caseId: string) {
  const queryClient = useQueryClient();

  const { mutateAsync, isPending } = useMutation({
    mutationFn: (threadId: string) => attachThread(caseId, threadId),
    onSuccess: () => {
      // The thread's own row now carries a case_id, and the case's thread
      // list has grown -- neither is cheap to patch by hand, so refetch.
      queryClient.invalidateQueries({ queryKey: ["threads"] });
    },
  });

  return { threadAttach: mutateAsync, isAttaching: isPending };
}
