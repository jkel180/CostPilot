"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Alert, Button, Field, Input } from "@/components/ui";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";

export default function SignupPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const email = String(form.get("email"));
    const password = String(form.get("password"));
    if (password !== String(form.get("confirm"))) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    const { data, error } = await getSupabaseBrowserClient().auth.signUp({
      email,
      password,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback?next=/select-organization` },
    });
    setBusy(false);
    if (error) return setError(error.message);
    if (data.session) {
      // Email confirmation disabled in Supabase: continue straight to organization setup.
      router.replace("/select-organization");
      router.refresh();
    } else {
      setSentTo(email);
    }
  }

  if (sentTo) {
    return (
      <div className="space-y-3">
        <h1 className="text-lg font-semibold">Check your inbox</h1>
        <p className="text-sm text-muted">
          We sent a confirmation link to <span className="font-medium text-foreground">{sentTo}</span>. Open it to
          activate your account and set up your organization.
        </p>
        <Link href="/login" className="inline-block text-sm text-accent hover:underline">
          Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Create your account</h1>
        <p className="mt-1 text-sm text-muted">You will register your organization in the next step.</p>
      </div>
      {error && <Alert>{error}</Alert>}
      <Field label="Work email">
        <Input name="email" type="email" autoComplete="email" required />
      </Field>
      <Field label="Password" hint="At least 8 characters.">
        <Input name="password" type="password" autoComplete="new-password" minLength={8} required />
      </Field>
      <Field label="Confirm password">
        <Input name="confirm" type="password" autoComplete="new-password" minLength={8} required />
      </Field>
      <Button type="submit" className="w-full" disabled={busy}>
        {busy ? "Creating account…" : "Create account"}
      </Button>
      <p className="text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </form>
  );
}
