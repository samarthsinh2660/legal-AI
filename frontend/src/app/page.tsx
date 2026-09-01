"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";
import { Wordmark } from "@/components/molecules/wordmark";
import { useAuth } from "@/features/auth/hooks/useAuth";

export default function HomePage() {
  const { user, isLoading, signOut } = useAuth();
  const router = useRouter();

  // Waiting on isLoading matters: routing on `!user` alone bounces a
  // signed-in user to /login on every refresh, before the token is checked.
  useEffect(() => {
    if (!isLoading && !user) router.replace("/login");
  }, [isLoading, user, router]);

  if (isLoading || !user) return null;

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-6">
      <Wordmark />
      <p className="text-sm text-ink-muted">Signed in as {user.email}</p>
      <Button variant="outline" onClick={() => void signOut()}>
        Sign out
      </Button>
    </main>
  );
}
