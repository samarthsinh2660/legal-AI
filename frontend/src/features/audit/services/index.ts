import { apiClient } from "@/lib/api";
import { paged, type Page } from "@/types/common";
import { AuditEventSchema, type AuditEvent } from "../types";

export async function fetchTrail(
  limit: number,
  offset: number,
): Promise<Page<AuditEvent>> {
  const data = await apiClient.get<unknown>(
    `/audit?limit=${limit}&offset=${offset}`,
  );
  return paged(AuditEventSchema).parse(data);
}
