import { apiClient } from "@/lib/api";
import { paged, type Page } from "@/types/common";
import { CaseSchema, type Case, type NewCase } from "../types";

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
