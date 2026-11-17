// Emanant HQ service worker: shows push notifications sent by the Mac (Phase 16). No caching of pages or data.
self.addEventListener("push", (event) => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; } catch { d = { title: "Emanant HQ", body: event.data ? event.data.text() : "" }; }
  event.waitUntil(self.registration.showNotification(d.title || "Emanant HQ", {
    body: d.body || "", tag: d.tag || undefined, icon: "/icon", badge: "/icon", data: { url: d.url || "/inbox" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || "/inbox", self.location.origin).href;
  event.waitUntil((async () => {
    const wins = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const w of wins) { if ("focus" in w) { await w.navigate(url).catch(() => {}); return w.focus(); } }
    return clients.openWindow(url);
  })());
});
