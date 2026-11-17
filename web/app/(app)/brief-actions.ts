"use server";
import { oldApi } from "@/lib/bridge";

export async function ackBrief(id: string) {
  try { await oldApi("/api/brief-ack", { id }); return true; } catch { return false; }
}
