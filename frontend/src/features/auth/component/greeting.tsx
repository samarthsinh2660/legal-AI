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
 * "Counsel" rather than a name: the API stores an email and nothing else,
 * and splitting a name out of an address guesses wrong as often as right.
 */
export function Greeting() {
  const { user } = useAuth();

  return (
    <div className="mb-6">
      <h1 className="text-title">
        {timeOfDay(new Date().getHours())}, Counsel
      </h1>
      <p className="mt-1.5 text-lg text-ink-variant">
        {user ? "What would you like to research?" : null}
      </p>
    </div>
  );
}
