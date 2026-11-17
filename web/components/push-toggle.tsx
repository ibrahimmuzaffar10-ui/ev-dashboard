"use client";
import { useEffect, useState, useTransition } from "react";
import { removePush, savePush, testPush } from "@/app/(app)/push-actions";

function key(b64: string) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export function PushToggle({ vapid }: { vapid: string }) {
  const [state, setState] = useState<"loading" | "unsupported" | "homescreen" | "off" | "on" | "blocked">("loading");
  const [sub, setSub] = useState<PushSubscription | null>(null);
  const [msg, setMsg] = useState("");
  const [pending, start] = useTransition();
  useEffect(() => {
    (async () => {
      const ios = /iPhone|iPad/.test(navigator.userAgent);
      const standalone = window.matchMedia("(display-mode: standalone)").matches || (navigator as unknown as { standalone?: boolean }).standalone;
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) return setState(ios && !standalone ? "homescreen" : "unsupported");
      const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" });
      const s = await reg.pushManager.getSubscription();
      setSub(s);
      setState(Notification.permission === "denied" ? "blocked" : s ? "on" : "off");
    })().catch(() => setState("unsupported"));
  }, []);
  const turnOn = () => start(async () => {
    try {
      if ((await Notification.requestPermission()) !== "granted") { setState("blocked"); return; }
      const reg = await navigator.serviceWorker.ready;
      const s = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key(vapid) });
      const r = await savePush(JSON.parse(JSON.stringify(s)), navigator.userAgent.includes("iPhone") ? "iPhone" : navigator.platform || "browser");
      setMsg(r.msg); if (r.ok) { setSub(s); setState("on"); }
    } catch (e) { setMsg(e instanceof Error ? e.message : "Couldn't turn on"); }
  });
  const turnOff = () => start(async () => {
    if (sub) { await removePush(sub.endpoint); await sub.unsubscribe(); }
    setSub(null); setState("off"); setMsg("Notifications off on this device");
  });
  if (state === "loading") return null;
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="font-medium">🔔 Notifications</div>
          <div className="text-[13px] text-[var(--muted)]">
            {state === "on" ? "On for this device: new inquiries, replies, payments, signed contracts"
              : state === "homescreen" ? "Add Emanant HQ to your Home Screen first (Share → Add to Home Screen), then open it from there"
              : state === "blocked" ? "Blocked: allow them in Settings → Notifications → Emanant HQ"
              : state === "unsupported" ? "This browser can't receive notifications" : "Get a notification the moment something new comes in"}
          </div>
        </div>
        {state === "off" && <button className="btn btn-primary shrink-0" disabled={pending} onClick={turnOn}>{pending ? "…" : "Turn on"}</button>}
        {state === "on" && <button className="btn shrink-0" disabled={pending} onClick={turnOff}>Turn off</button>}
      </div>
      {state === "on" && <button className="btn mt-3 w-full" disabled={pending} onClick={() => start(async () => setMsg((await testPush()).msg))}>Send a test notification</button>}
      {msg && <p className="mt-2 text-[13px] text-[var(--muted)]">{msg}</p>}
    </div>
  );
}
