"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { PageLoader } from "@/components/molecules/loading";
import { useAuth } from "../hooks/useAuth";

/**
 * The gate on every authenticated route.
 *
 * Client-side because the token lives in localStorage, which no server
 * component can read. That means the check is a convenience, not a
 * security boundary -- the API refuses an unauthenticated request on its
 * own, and that is what actually protects the data.
 *
 * Rendering the loader while `isLoading` matters: routing on `!user`
 * alone would bounce a signed-in user to /login on every refresh, before
 * the stored token has been checked.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) router.replace("/login");
  }, [isLoading, user, router]);

  if (isLoading) return <PageLoader />;
  if (!user) return null;
  return <>{children}</>;
}
