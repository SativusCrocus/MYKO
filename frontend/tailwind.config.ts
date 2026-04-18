import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          bg: "#000000",
          fg: "#FFFFFF",
          muted: "rgba(255,255,255,0.5)",
          glass: "rgba(255,255,255,0.03)",
          border: "rgba(255,255,255,0.08)",
        },
        accent: {
          vault: "#00F0FF",
          nostr: "#A855F7",
          ln: "#F59E0B",
          goose: "#3B82F6",
          ok: "#22C55E",
          err: "#EF4444",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      borderRadius: {
        glass: "16px",
      },
      backdropBlur: {
        glass: "20px",
      },
    },
  },
  plugins: [],
};

export default config;
