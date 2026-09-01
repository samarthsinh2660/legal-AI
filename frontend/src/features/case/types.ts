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
  description?: string;
};

export const TITLE_MAX_LENGTH = 300;
export const DESCRIPTION_MAX_LENGTH = 2000;
