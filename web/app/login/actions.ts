"use server";
import { redirect } from "next/navigation";
import { supabaseServer } from "@/lib/supabase/server";

export type LoginState = { error?: string } | undefined;

export async function login(_: LoginState, form: FormData): Promise<LoginState> {
  const email = String(form.get("email") || "").trim();
  const password = String(form.get("password") || "");
  if (!email || !password) return { error: "Enter your email and password." };
  const supabase = await supabaseServer();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) return { error: "Wrong email or password." };
  // Only the allowlisted accounts may use Emanant HQ: Row Level Security returns no rows to anyone else
  const { count } = await supabase.from("leads").select("lead_id", { count: "exact", head: true });
  if (!count) {
    await supabase.auth.signOut();
    return { error: "This account is not allowed to use Emanant HQ." };
  }
  redirect("/");
}

export async function logout() {
  const supabase = await supabaseServer();
  await supabase.auth.signOut();
  redirect("/login");
}
