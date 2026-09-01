import { z } from "zod";

export const UserSchema = z.object({
  user_id: z.string(),
  email: z.string(),
});
export type User = z.infer<typeof UserSchema>;

export const SessionSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
});
export type Session = z.infer<typeof SessionSchema>;

export const RegisteredSchema = z.object({
  user_id: z.string(),
});

/** The backend's floor (`api/accounts/schemas.py`). Checked here too, so a
 *  short password is a field error rather than a round trip and a 400. */
export const PASSWORD_MIN_LENGTH = 12;
