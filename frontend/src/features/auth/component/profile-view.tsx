"use client";

import { Pencil } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/molecules/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageLoader } from "@/components/molecules/loading";
import { useProfile } from "../hooks/useProfile";
import { NAME_MAX_LENGTH } from "../types";

/** One read-only fact. */
function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 border-b border-line px-6 py-4 last:border-b-0 sm:flex-row sm:items-center sm:gap-6">
      <span className="caps w-32 shrink-0 text-ink-muted">{label}</span>
      <span className="mono min-w-0 break-all text-sm text-ink">{value}</span>
    </div>
  );
}

/**
 * Organism: uses `useProfile`, so it owns loading, error and edit state.
 *
 * The name saves on its own; the address is behind a password
 * confirmation, because moving it takes the account with it -- it is the
 * sign-in handle, and there is no mail path here to recover a typo. The
 * screen says so before the field is touched.
 *
 * Password change is absent rather than half-built.
 */
export function ProfileView() {
  const {
    profile, isLoading, loadError, editing, draft, error, isSaving,
    startEditing, cancel, setDraft, save,
    editingEmail, emailDraft, setEmailDraft, password, setPassword,
    emailError, isSavingEmail, startEditingEmail, cancelEmail, saveEmail,
  } = useProfile();

  if (isLoading) return <PageLoader />;
  if (loadError || !profile) {
    return <EmptyState message="Could not load your profile. Refresh to try again." />;
  }

  const joined = profile.created_at
    ? new Date(profile.created_at).toLocaleDateString("en-IN", {
        day: "numeric", month: "long", year: "numeric",
      })
    : "—";

  return (
    <Card className="gap-0 overflow-hidden p-0">
      <div className="flex flex-col gap-1 border-b border-line px-6 py-4 sm:flex-row sm:items-center sm:gap-6">
        <span className="caps w-32 shrink-0 text-ink-muted">Name</span>

        {editing ? (
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <Label htmlFor="name" className="sr-only">Name</Label>
              <Input
                id="name"
                autoFocus
                value={draft}
                maxLength={NAME_MAX_LENGTH}
                disabled={isSaving}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void save();
                  if (event.key === "Escape") cancel();
                }}
                className="max-w-xs"
              />
              <Button onClick={() => void save()} disabled={isSaving}>
                {isSaving ? "Saving…" : "Save"}
              </Button>
              <Button variant="outline" onClick={cancel} disabled={isSaving}>
                Cancel
              </Button>
            </div>
            {error && <p className="text-sm text-danger">{error}</p>}
          </div>
        ) : (
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <span className="min-w-0 truncate text-sm font-medium text-ink">
              {/* An account made before names existed has none. The address
                  stands in; a name guessed from it would be a fabrication
                  in the one place a reader trusts. */}
              {profile.name || (
                <span className="text-ink-muted">Not set</span>
              )}
            </span>
            <button
              type="button"
              onClick={startEditing}
              aria-label="Edit name"
              className="flex size-8 shrink-0 items-center justify-center rounded text-ink-muted transition-colors duration-[120ms] ease-out hover:bg-surface-sunken hover:text-ink"
            >
              <Pencil className="size-4" />
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1 border-b border-line px-6 py-4 sm:flex-row sm:items-start sm:gap-6">
        <span className="caps w-32 shrink-0 pt-2 text-ink-muted">Email</span>

        {editingEmail ? (
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <Label htmlFor="new-email" className="sr-only">New email</Label>
            <Input
              id="new-email"
              type="email"
              autoFocus
              autoComplete="email"
              value={emailDraft}
              disabled={isSavingEmail}
              onChange={(event) => setEmailDraft(event.target.value)}
              className="max-w-sm"
            />
            <Label htmlFor="confirm-password" className="text-xs text-ink-muted">
              Confirm with your current password
            </Label>
            <Input
              id="confirm-password"
              type="password"
              autoComplete="current-password"
              value={password}
              disabled={isSavingEmail}
              onChange={(event) => setPassword(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void saveEmail();
                if (event.key === "Escape") cancelEmail();
              }}
              className="max-w-sm"
            />
            {/* Said before they commit, not after: there is no mail path in
                this system, so a typo here locks them out of signing in. */}
            <p className="max-w-sm text-xs text-warn">
              This becomes the address you sign in with, straight away. There
              is no confirmation email — check it is right.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void saveEmail()} disabled={isSavingEmail}>
                {isSavingEmail ? "Saving…" : "Change email"}
              </Button>
              <Button variant="outline" onClick={cancelEmail} disabled={isSavingEmail}>
                Cancel
              </Button>
            </div>
            {emailError && <p className="text-sm text-danger">{emailError}</p>}
          </div>
        ) : (
          <div className="flex min-w-0 flex-1 items-center gap-3 pt-1.5">
            <span className="mono min-w-0 break-all text-sm text-ink">
              {profile.email}
            </span>
            <button
              type="button"
              onClick={startEditingEmail}
              aria-label="Edit email"
              className="flex size-8 shrink-0 items-center justify-center rounded text-ink-muted transition-colors duration-[120ms] ease-out hover:bg-surface-sunken hover:text-ink"
            >
              <Pencil className="size-4" />
            </button>
          </div>
        )}
      </div>

      <Row label="Joined" value={joined} />
      <Row label="User ID" value={profile.user_id} />

      <p className="border-t border-line px-6 py-4 text-xs text-ink-muted">
        Changing your password is not built yet.
      </p>
    </Card>
  );
}
