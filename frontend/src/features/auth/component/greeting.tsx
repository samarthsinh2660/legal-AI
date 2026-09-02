"use client";

import { useAuth } from "../hooks/useAuth";

function timeOfDay(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

/**
 * Organism: reads the session.
 *
 * Falls back to "Counsel" for an account made before names existed. The
 * address is never used here -- greeting someone by their email reads as a
 * mail merge, and splitting a name out of one guesses wrong as often as
 * right.
 */
export function Greeting() {
  const { user } = useAuth();
  // First word only: "Good morning, Samarth" and not the full legal name.
  const first = user?.name?.trim().split(/\s+/)[0];

  return (
    <div className="mb-6">
      <h1 className="text-title">
        {timeOfDay(new Date().getHours())}, {first || "Counsel"}
      </h1>
      <p className="mt-1.5 text-lg text-ink-variant">
        {user ? "What would you like to research?" : null}
      </p>
    </div>
  );
}
