"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { PageLoader } from "@/components/molecules/loading";
import { useAuth } from "../hooks/useAuth";

/**
 * Sends a signed-in visitor to the dashboard instead of showing them the
 * login form.
 *
 * Their token is valid and the session is live; asking for the password
 * again implies it is not, and signing in a second time changes nothing.
 */
export function RedirectIfSignedIn({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && user) router.replace("/dashboard");
  }, [isLoading, user, router]);

  if (isLoading) return <PageLoader />;
  if (user) return null;
  return <>{children}</>;
}
