"use client";
import { useActionState } from "react";
import { addLead } from "../actions";
import { SERVICE } from "@/components/ui";

const input = "mt-1 w-full rounded-xl border border-[var(--line)] bg-[var(--bg)] px-3 py-2.5 text-[15px] text-[var(--ink)]";

export function NewLeadForm() {
  const [state, action, pending] = useActionState(addLead, undefined);
  return (
    <form action={action} className="card mt-4 space-y-3 p-4">
      <label className="block text-sm text-[var(--muted)]">Client name *<input name="client" required autoComplete="off" className={input} /></label>
      <div className="grid grid-cols-2 gap-3">
        <label className="block text-sm text-[var(--muted)]">Came from
          <select name="channel" className={input} defaultValue="Instagram">
            {["Instagram", "Email", "Website form", "Phone / text", "Referral", "Vendor", "Other"].map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label className="block text-sm text-[var(--muted)]">Service
          <select name="service" className={input} defaultValue="wedding">
            {Object.entries(SERVICE).map(([k, l]) => <option key={k} value={k}>{l}</option>)}<option value="unknown">Not sure yet</option>
          </select>
        </label>
      </div>
      <label className="block text-sm text-[var(--muted)]">Event date<input name="event" type="date" className={input} /></label>
      <label className="block text-sm text-[var(--muted)]">Their email (so replies are recognized)<input name="email" type="email" autoComplete="off" className={input} /></label>
      <label className="block text-sm text-[var(--muted)]">Notes<textarea name="notes" rows={3} className={input} placeholder="What they asked for, hours, location…" /></label>
      {state?.error && <p role="alert" className="text-sm text-[var(--red)]">{state.error}</p>}
      <button disabled={pending} className="btn btn-primary w-full">{pending ? "Adding…" : "Add lead"}</button>
    </form>
  );
}
