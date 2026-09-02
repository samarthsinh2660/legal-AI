"use client";

/**
 * The session, in React Context rather than TanStack Query.
 *
 * Query owns *server data*; the session is neither -- it is the token, and
 * every query in the app depends on it. Keeping it in context means a
 * logout can clear the token and the query cache in one place, so a
 * signed-out user cannot see the previous user's cached threads.
 */

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import type { Credentials } from "@/types/auth";
import * as authService from "../services";
import * as session from "../session";
import type { User } from "../types";

type AuthContextValue = {
  user: User | null;
  /** True for the first client render only. localStorage is unreadable
   *  during the server render, so the first paint cannot know whether
   *  anyone is signed in -- and routing on `!user` before this settles
   *  bounces a signed-in user to the login screen on every refresh. */
  isLoading: boolean;
  signIn: (credentials: Credentials) => Promise<void>;
  signUp: (credentials: Credentials) => Promise<void>;
  signOut: () => Promise<void>;
  /** Patches the stored session after a profile edit, so the sidebar
   *  updates immediately rather than at the next sign-in. */
  setName: (name: string) => void;
  setEmail: (email: string) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const router = useRouter();

  // localStorage is an external store, so it is read through the hook made
  // for one. No request: `/auth/login` already returned the identity, and
  // the token carries its own expiry, so restoring a session is entirely
  // local. Asking the server cost a round trip on every page load to learn
  // what was already on disk.
  //
  // What this gives up is revocation: an account deleted server-side still
  // renders as signed in until its token expires. With no denylist behind
  // it (docs/API.md §9) the old `/auth/me` check could not detect a revoked
  // token either, so nothing real is lost.
  const user = useSyncExternalStore(
    session.subscribe,
    session.read,
    session.serverSnapshot,
  );
  const hydrated = useSyncExternalStore(
    session.subscribe,
    () => true,
    () => false,
  );

  const clear = useCallback(() => {
    session.clear();
    // Everything cached was fetched as the previous user.
    queryClient.clear();
  }, [queryClient]);

  const signIn = useCallback(
    async (credentials: Credentials) => {
      // One call. The identity comes back with the token, and it is the
      // stored, lower-cased email rather than whatever the form held.
      const { access_token, user_id, email, name } = await authService.login(
        credentials,
      );
      session.save(access_token, { user_id, email, name: name ?? null });
    },
    [],
  );

  const setName = useCallback((name: string) => {
    session.rename(name);
  }, []);

  // The token still works -- it carries a user id, not an address -- so
  // only the stored identity needs replacing.
  const setEmail = useCallback((email: string) => {
    session.setEmail(email);
  }, []);

  const signUp = useCallback(
    async (credentials: Credentials) => {
      await authService.register(credentials);
      await signIn(credentials);
    },
    [signIn],
  );

  const signOut = useCallback(async () => {
    await authService.logout();
    clear();
    router.push("/login");
  }, [clear, router]);

  const value = useMemo(
    () => ({
      user, isLoading: !hydrated, signIn, signUp, signOut, setName, setEmail,
    }),
    [user, hydrated, signIn, signUp, signOut, setName, setEmail],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    // Louder than a default value: a component rendering outside the
    // provider would otherwise look signed out and silently redirect.
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return context;
}
