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
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import { RequestError } from "@/lib/api";
import { TOKEN_KEY } from "@/types/constant";
import type { Credentials } from "@/types/auth";
import * as authService from "../services";
import type { User } from "../types";

type AuthContextValue = {
  user: User | null;
  /** True until the stored token has been checked. Guards render on it --
   *  routing on `!user` before this settles bounces a signed-in user to
   *  the login screen on every refresh. */
  isLoading: boolean;
  signIn: (credentials: Credentials) => Promise<void>;
  signUp: (credentials: Credentials) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const queryClient = useQueryClient();
  const router = useRouter();

  const clear = useCallback(() => {
    window.localStorage.removeItem(TOKEN_KEY);
    setUser(null);
    // Everything cached was fetched as the previous user.
    queryClient.clear();
  }, [queryClient]);

  // On mount, ask the server who the stored token belongs to. Decoding it
  // here instead would trust a value the user can edit, and would still
  // miss a token whose account was deleted.
  //
  // Every setState is in a callback, never in the effect body: a
  // synchronous one cascades a second render before paint, and React
  // Compiler's lint rejects it. `cancelled` covers unmount and StrictMode's
  // double-invoke in development.
  useEffect(() => {
    let cancelled = false;
    const token = window.localStorage.getItem(TOKEN_KEY);

    // No token is a settled answer, not a request worth making.
    const identify = token ? authService.me() : Promise.resolve(null);

    identify
      .then((identity) => {
        if (!cancelled) setUser(identity);
      })
      .catch((error) => {
        // A 401 means the token is spent: drop it. Anything else (server
        // down, offline) must not sign the user out -- their token may be
        // perfectly good.
        if (!cancelled && error instanceof RequestError && error.status === 401) {
          clear();
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [clear]);

  const signIn = useCallback(
    async (credentials: Credentials) => {
      const session = await authService.login(credentials);
      window.localStorage.setItem(TOKEN_KEY, session.access_token);
      // Read the identity back rather than assuming it from the form, so
      // `user.email` is the stored, lower-cased one.
      setUser(await authService.me());
    },
    [],
  );

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
    () => ({ user, isLoading, signIn, signUp, signOut }),
    [user, isLoading, signIn, signUp, signOut],
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
