import type { MetadataRoute } from "next";

// Home Screen app (needed for notifications on iPhone, iOS 16.4+)
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Emanant HQ", short_name: "Emanant HQ", description: "Leads, bookings and payments for Emanant Visuals",
    start_url: "/", scope: "/", display: "standalone", background_color: "#f6f3ec", theme_color: "#1f5c47",
    icons: [{ src: "/icon", sizes: "512x512", type: "image/png", purpose: "any" }, { src: "/apple-icon", sizes: "180x180", type: "image/png" }],
  };
}
