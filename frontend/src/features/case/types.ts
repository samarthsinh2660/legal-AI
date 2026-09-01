import { z } from "zod";

export const CaseSchema = z.object({
  case_id: z.string(),
  title: z.string(),
  court: z.string().nullable(),
  state: z.string().nullable(),
  case_number: z.string().nullable(),
  parties: z.array(z.string()),
  matter_type: z.string().nullable(),
  status: z.string().nullable(),
  description: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type Case = z.infer<typeof CaseSchema>;

/** What the New Case modal collects (design/UX_FLOWS.md "Creating a case").
 *  `description` is not a notes field -- it seeds the context every agent
 *  in the thread starts from, which is why the form labels it that way. */
export type NewCase = {
  title: string;
  matter_type?: string;
  court?: string;
  /** Not optional in spirit: RERA rules, rent control and stamp duty are
   *  state-made, so a thread whose state is unknown stops and asks before
   *  it researches. Recording it on the case answers that question once
   *  for every thread in the matter. */
  state?: string;
  description?: string;
};

export const TITLE_MAX_LENGTH = 300;
export const DESCRIPTION_MAX_LENGTH = 2000;

/** A file uploaded to a matter. `GET /cases/{id}/documents` returns the id
 *  and the filename only -- the extracted text stays server-side. */
export const CaseFileSchema = z.object({
  document_id: z.string(),
  filename: z.string(),
});

export type CaseFile = z.infer<typeof CaseFileSchema>;

/** What `POST /cases/{id}/documents` answers with. `characters` is the
 *  extracted text length, which is the only proof the file was readable. */
export const UploadedSchema = z.object({
  document_id: z.string(),
  filename: z.string(),
  characters: z.number(),
});

/** The API's own limits (`docs/API.md` §4.2). Checked here too so an
 *  oversized file fails instantly rather than after a 25MB upload. */
export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
export const ACCEPTED_TYPES = ".pdf,.docx,.txt,.md";
