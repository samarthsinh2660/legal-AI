"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { useLoginForm } from "../hooks/useLoginForm";
import { NAME_MAX_LENGTH } from "../types";

/** Organism: it uses a hook, so it owns the submitting and error states.
 *  Both screens are the same two fields, so they are one component. */
export function LoginForm({ mode }: { mode: "signIn" | "signUp" }) {
  const { form, errors, isSubmitting, handleChange, handleSubmit } =
    useLoginForm(mode);
  const isSignUp = mode === "signUp";

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        void handleSubmit();
      }}
    >
      {isSignUp && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            autoComplete="name"
            maxLength={NAME_MAX_LENGTH}
            value={form.name ?? ""}
            onChange={(event) => handleChange("name", event.target.value)}
            className={cn(errors.name && "border-danger")}
          />
          {errors.name && <p className="text-sm text-danger">{errors.name}</p>}
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={form.email}
          onChange={(event) => handleChange("email", event.target.value)}
          className={cn(errors.email && "border-danger")}
        />
        {errors.email && <p className="text-sm text-danger">{errors.email}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete={isSignUp ? "new-password" : "current-password"}
          value={form.password}
          onChange={(event) => handleChange("password", event.target.value)}
          className={cn(errors.password && "border-danger")}
        />
        {errors.password && (
          <p className="text-sm text-danger">{errors.password}</p>
        )}
      </div>

      {errors.form && (
        <p className="rounded bg-danger-bg px-3 py-2 text-sm text-danger">
          {errors.form}
        </p>
      )}

      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "…" : isSignUp ? "Create account" : "Sign in"}
      </Button>

      <p className="text-center text-sm text-ink-muted">
        {isSignUp ? "Already have an account? " : "No account yet? "}
        <Link
          href={isSignUp ? "/login" : "/register"}
          className="text-primary hover:text-primary-hover"
        >
          {isSignUp ? "Sign in" : "Create one"}
        </Link>
      </p>
    </form>
  );
}
