"use client";
import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { version } from "@/app/(app)/live-actions";

// Keeps the open screen current: every 10 s while visible (and right away when you come back to the app)
export function Live() {
  const router = useRouter();
  const last = useRef<string | null>(null);
  useEffect(() => {
    let busy = false;
    const tick = async () => {
      if (document.hidden || busy || document.activeElement?.matches("input, textarea, select")) return;
      busy = true;
      try {
        const v = await version();
        if (last.current !== null && v !== last.current) router.refresh();
        last.current = v;
      } catch { /* offline: try again next tick */ } finally { busy = false; }
    };
    tick();
    const id = setInterval(tick, 10000);
    const onShow = () => { if (!document.hidden) tick(); };
    document.addEventListener("visibilitychange", onShow);
    return () => { clearInterval(id); document.removeEventListener("visibilitychange", onShow); };
  }, [router]);
  return null;
}
