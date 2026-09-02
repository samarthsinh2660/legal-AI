/**
 * Plain async functions over `apiClient`. No hooks, no state, no React.
 *
 * Every response is Zod-parsed: if the backend changes shape, it fails
 * here with a clear error rather than as `undefined` three components
 * later.
 */

import { apiClient } from "@/lib/api";
import type { Credentials } from "@/types/auth";
import { ProfileSchema, RegisteredSchema, SessionSchema } from "../types";

export async function login(credentials: Credentials) {
  const data = await apiClient.post<unknown>("/auth/login", credentials);
  return SessionSchema.parse(data);
}

export async function register(credentials: Credentials) {
  const data = await apiClient.post<unknown>("/auth/register", credentials);
  return RegisteredSchema.parse(data);
}

/**
 * Ends the session on the client. The backend keeps no denylist, so the
 * token stays valid until it expires -- see docs/API.md §9. Discarding it
 * locally is the whole of the effect, which is why this cannot fail in a
 * way the caller needs to handle.
 */
export async function profile() {
  const data = await apiClient.get<unknown>("/auth/profile");
  return ProfileSchema.parse(data);
}

/** The name is the only editable field -- see `controller.rename`. */
export async function rename(name: string) {
  const data = await apiClient.patch<unknown>("/auth/profile", { name });
  return ProfileSchema.parse(data);
}

/** Requires the current password: the address is the sign-in handle, so a
 *  borrowed token must not be able to move it. */
export async function changeEmail(email: string, password: string) {
  const data = await apiClient.patch<unknown>("/auth/profile/email", {
    email,
    password,
  });
  return ProfileSchema.parse(data);
}

export async function logout() {
  await apiClient.post("/auth/logout").catch(() => {});
}
