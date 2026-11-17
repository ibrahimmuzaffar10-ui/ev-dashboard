"use client";
import { useActionState } from "react";
import { login } from "./actions";

export default function LoginPage() {
  const [state, action, pending] = useActionState(login, undefined);
  return (
    <main className="min-h-dvh flex items-center justify-center px-4 bg-[var(--bg)]">
      <form action={action} className="w-full max-w-sm space-y-4 rounded-2xl bg-[var(--panel)] p-6 shadow-sm">
        <h1 className="text-xl font-semibold">Emanant HQ</h1>
        <label className="block text-sm">
          Email
          <input name="email" type="email" autoComplete="username" required
                 className="mt-1 w-full rounded-lg border border-[var(--line)] bg-transparent px-3 py-3 text-base" />
        </label>
        <label className="block text-sm">
          Password
          <input name="password" type="password" autoComplete="current-password" required
                 className="mt-1 w-full rounded-lg border border-[var(--line)] bg-transparent px-3 py-3 text-base" />
        </label>
        {state?.error && <p role="alert" className="text-sm text-[var(--red)]">{state.error}</p>}
        <button disabled={pending} className="w-full rounded-lg bg-[var(--ink)] py-3 text-base font-medium text-[var(--bg)] disabled:opacity-60">
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
