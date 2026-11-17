import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

// Emanant HQ monogram: ivory "E" on emerald
export default function Icon() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#1f5c47", color: "#f6f3ec",
                    fontSize: 180 * 0.62, fontFamily: "Georgia, serif", fontWeight: 600, letterSpacing: -2 }}>E</div>
    ),
    size,
  );
}
