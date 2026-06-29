import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // The "God View" accent — a calm cyan that reads on deep navy.
        accent: {
          DEFAULT: "#38bdf8", // sky-400
          muted: "#0ea5e9", // sky-500
        },
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(56,189,248,0.4), 0 0 18px rgba(56,189,248,0.35)",
      },
      keyframes: {
        pulseGlow: {
          "0%, 100%": { opacity: "0.45" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        pulseGlow: "pulseGlow 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
