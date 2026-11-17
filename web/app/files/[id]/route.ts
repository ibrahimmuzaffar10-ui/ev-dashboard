// A lead's contract file (draft / signed / questionnaire), read with the signed-in user's own session (RLS),
// straight from the database. PDFs open in the phone's viewer; Word files download.
import { supabaseServer } from "@/lib/supabase/server";

export async function GET(_req: Request, ctx: RouteContext<"/files/[id]">) {
  const { id } = await ctx.params;
  if (!/^\d+$/.test(id)) return new Response("not found", { status: 404 });
  const sb = await supabaseServer();
  const { data: { user } } = await sb.auth.getUser();
  if (!user) return new Response("sign in required", { status: 401 });
  const doc = await sb.from("documents").select("original_path, storage_key").eq("document_id", Number(id)).maybeSingle();
  if (!doc.data?.storage_key) return new Response("not found", { status: 404 });
  const f = await sb.from("files").select("content_type, data").eq("file_key", doc.data.storage_key).maybeSingle();
  if (!f.data?.data) return new Response("not found", { status: 404 });
  const hex = String(f.data.data);                                   // bytea arrives as "\\x…" hex
  const bytes = Buffer.from(hex.startsWith("\\x") ? hex.slice(2) : hex, "hex");
  const name = String(doc.data.original_path || "file").split("/").pop() || "file";
  const pdf = name.toLowerCase().endsWith(".pdf");
  return new Response(bytes, { headers: {
    "Content-Type": f.data.content_type || (pdf ? "application/pdf" : "application/octet-stream"),
    "Content-Disposition": `${pdf ? "inline" : "attachment"}; filename*=UTF-8''${encodeURIComponent(name)}`,
    "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
  } });
}
