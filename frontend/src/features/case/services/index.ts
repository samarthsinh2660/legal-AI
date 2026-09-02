import { z } from "zod";

import { apiClient } from "@/lib/api";
import { paged, type Page } from "@/types/common";
import {
  CaseFileSchema,
  CaseSchema,
  UploadedSchema,
  type Case,
  type CaseFile,
  type NewCase,
} from "../types";

export async function fetchCases(
  limit: number,
  offset: number,
): Promise<Page<Case>> {
  const data = await apiClient.get<unknown>(
    `/cases?limit=${limit}&offset=${offset}`,
  );
  return paged(CaseSchema).parse(data);
}

export async function createCase(payload: NewCase): Promise<Case> {
  const data = await apiClient.post<unknown>("/cases", payload);
  return CaseSchema.parse(data);
}

export async function fetchCase(caseId: string): Promise<Case> {
  const data = await apiClient.get<unknown>(`/cases/${caseId}`);
  return CaseSchema.parse(data);
}

export async function updateCase(
  caseId: string,
  changes: Partial<NewCase>,
): Promise<Case> {
  const data = await apiClient.patch<unknown>(`/cases/${caseId}`, changes);
  return CaseSchema.parse(data);
}

export async function deleteCase(caseId: string): Promise<void> {
  await apiClient.delete(`/cases/${caseId}`);
}

export async function fetchCaseFiles(caseId: string): Promise<CaseFile[]> {
  const data = await apiClient.get<unknown>(`/cases/${caseId}/documents`);
  return z.array(CaseFileSchema).parse(data);
}

export async function uploadCaseFile(caseId: string, file: File) {
  const data = await apiClient.upload<unknown>(
    `/cases/${caseId}/documents`,
    file,
  );
  return UploadedSchema.parse(data);
}

/** Design Flow A's "Save to case". From here on that thread's questions
 *  are seeded with the matter's parties, documents and findings. */
export async function attachThread(
  caseId: string,
  threadId: string,
): Promise<void> {
  await apiClient.post(`/cases/${caseId}/threads`, { thread_id: threadId });
}
