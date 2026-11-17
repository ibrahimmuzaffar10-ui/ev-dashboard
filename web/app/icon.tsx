import { ImageResponse } from "next/og";

export const size = { width: 512, height: 512 };
export const contentType = "image/png";

// Emanant HQ monogram: ivory "E" on emerald
export default function Icon() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#1f5c47", color: "#f6f3ec",
                    fontSize: 512 * 0.62, fontFamily: "Georgia, serif", fontWeight: 600, letterSpacing: -2 }}>E</div>
    ),
    size,
  );
}
