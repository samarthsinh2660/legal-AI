import { z } from "zod";

export const UserSchema = z.object({
  user_id: z.string(),
  email: z.string(),
  /** Null for the accounts made before names existed. Rendered as the
   *  address in that case -- never as a name guessed from it. */
  name: z.string().nullable().optional(),
});
export type User = z.infer<typeof UserSchema>;

/** `/auth/login`'s answer: the token and who it is for. The identity is
 *  part of it so signing in is one round trip and restoring a session on
 *  boot is none. */
export const SessionSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
  user_id: z.string(),
  email: z.string(),
  name: z.string().nullable().optional(),
});
export type Session = z.infer<typeof SessionSchema>;

export const RegisteredSchema = z.object({
  user_id: z.string(),
});

/** The backend's floor (`api/accounts/schemas.py`). Checked here too, so a
 *  short password is a field error rather than a round trip and a 400. */
export const PASSWORD_MIN_LENGTH = 12;

/** The backend's ceiling (`controller.NAME_MAX`). */
export const NAME_MAX_LENGTH = 80;

/** The whole profile, including when the account was made -- which no
 *  token carries, so it is fetched rather than read from the session. */
export const ProfileSchema = z.object({
  user_id: z.string(),
  email: z.string(),
  name: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
});
export type Profile = z.infer<typeof ProfileSchema>;
