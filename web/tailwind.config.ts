import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Dark theme colors inspired by Obsidian/BetterStack
        background: {
          DEFAULT: "#0D0D0D",
          secondary: "#1A1A1A",
          tertiary: "#262626",
        },
        surface: {
          DEFAULT: "#2D2D2D",
          hover: "#333333",
          active: "#404040",
        },
        primary: {
          DEFAULT: "#8B5CF6",
          hover: "#7C3AED",
          light: "#A78BFA",
        },
        accent: {
          blue: "#6366F1",
          purple: "#8B5CF6",
          cyan: "#06B6D4",
        },
        text: {
          primary: "#F5F5F5",
          secondary: "#E5E5E5",
          muted: "#A1A1A1",
          disabled: "#737373",
        },
        border: {
          DEFAULT: "#333333",
          light: "#404040",
          focus: "#8B5CF6",
        },
        success: "#10B981",
        warning: "#F59E0B",
        error: "#EF4444",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "monospace"],
      },
      borderRadius: {
        lg: "12px",
        md: "8px",
        sm: "6px",
      },
      boxShadow: {
        glow: "0 0 20px rgba(139, 92, 246, 0.3)",
        "glow-sm": "0 0 10px rgba(139, 92, 246, 0.2)",
      },
      animation: {
        "fade-in": "fadeIn 0.2s ease-in-out",
        "slide-up": "slideUp 0.3s ease-out",
        "pulse-glow": "pulseGlow 2s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { transform: "translateY(10px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        pulseGlow: {
          "0%, 100%": { boxShadow: "0 0 10px rgba(139, 92, 246, 0.2)" },
          "50%": { boxShadow: "0 0 20px rgba(139, 92, 246, 0.4)" },
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
