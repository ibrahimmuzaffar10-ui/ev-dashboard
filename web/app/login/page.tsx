"use client";
import { useActionState } from "react";
import { login } from "./actions";

export default function LoginPage() {
  const [state, action, pending] = useActionState(login, undefined);
  return (
    <main className="flex min-h-dvh items-center justify-center bg-[var(--bg)] px-4">
      <form action={action} className="card w-full max-w-sm space-y-4 p-6">
        <div><h1 className="font-serif text-[28px] font-semibold">Emanant HQ</h1><p className="text-sm text-[var(--muted)]">Sign in with your dashboard account</p></div>
        <label className="block text-sm">
          Email
          <input name="email" type="email" autoComplete="username" required
                 className="mt-1 w-full rounded-xl border border-[var(--line)] bg-[var(--bg)] px-3 py-3 text-base" />
        </label>
        <label className="block text-sm">
          Password
          <input name="password" type="password" autoComplete="current-password" required
                 className="mt-1 w-full rounded-xl border border-[var(--line)] bg-[var(--bg)] px-3 py-3 text-base" />
        </label>
        {state?.error && <p role="alert" className="text-sm text-[var(--red)]">{state.error}</p>}
        <button disabled={pending} className="btn btn-primary w-full py-3 text-base">
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
