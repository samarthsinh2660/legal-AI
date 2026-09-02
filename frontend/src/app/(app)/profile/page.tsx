import type { Metadata } from "next";

import { ProfileView } from "@/features/auth/component/profile-view";

export const metadata: Metadata = { title: "Profile · Pramāṇa AI" };

/** Composes only. Every state belongs to the organism. */
export default function ProfilePage() {
  return (
    <main className="mx-auto w-full max-w-3xl">
      <h1 className="text-heading font-semibold text-ink">Profile</h1>
      <p className="mt-1.5 mb-6 text-ink-variant">
        Your account details.
      </p>
      <ProfileView />
    </main>
  );
}
