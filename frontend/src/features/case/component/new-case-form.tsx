"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { useNewCaseForm } from "../hooks/useNewCaseForm";

/** Organism: uses `useNewCaseForm`, so it owns submitting and errors. */
export function NewCaseForm({ onCreated }: { onCreated?: () => void }) {
  const { form, errors, isCreating, handleChange, handleSubmit } =
    useNewCaseForm(onCreated);

  return (
    <form
      className="flex flex-col gap-4 rounded-md border border-line bg-surface-card p-6"
      onSubmit={(event) => {
        event.preventDefault();
        void handleSubmit();
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="case-title">
          Title <span className="text-danger">*</span>
        </Label>
        <Input
          id="case-title"
          value={form.title}
          onChange={(event) => handleChange("title", event.target.value)}
          placeholder="Sharma v. Skyline Developers"
          className={cn(errors.title && "border-danger")}
        />
        {errors.title && <p className="text-sm text-danger">{errors.title}</p>}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="case-matter">Matter type</Label>
          <Input
            id="case-matter"
            value={form.matter_type ?? ""}
            onChange={(event) => handleChange("matter_type", event.target.value)}
            placeholder="Consumer / RERA"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="case-state">State</Label>
          <Input
            id="case-state"
            value={form.state ?? ""}
            onChange={(event) => handleChange("state", event.target.value)}
            placeholder="Maharashtra"
          />
          {/* Worth the field: RERA rules, rent control and stamp duty are
              state-made, so without this every thread in the matter stops
              to ask before it researches. */}
          <p className="text-xs text-ink-muted">
            Recorded once here, so threads don&apos;t stop to ask.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="case-court">Court</Label>
        <Input
          id="case-court"
          value={form.court ?? ""}
          onChange={(event) => handleChange("court", event.target.value)}
          placeholder="Bombay High Court"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="case-description">Context</Label>
        <Textarea
          id="case-description"
          rows={3}
          value={form.description ?? ""}
          onChange={(event) => handleChange("description", event.target.value)}
          placeholder="What the matter is about, in a sentence or two."
          className="resize-none"
        />
        {/* Said plainly, because it changes what the user writes here. */}
        <p className="text-xs text-ink-muted">
          This seeds every research thread attached to the case — it is
          context for the agents, not a private note.
        </p>
      </div>

      {errors.form && <p className="text-sm text-danger">{errors.form}</p>}

      <Button type="submit" className="self-start" disabled={isCreating}>
        {isCreating ? "Creating…" : "Create case"}
      </Button>
    </form>
  );
}
