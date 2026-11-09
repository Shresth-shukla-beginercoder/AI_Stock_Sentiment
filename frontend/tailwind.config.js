/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // NEXTBELL Design Tokens
        ink: "#0a0f1c",
        navy: "#111827",
        chrome: {
          light: "#f8fafc",
          dark: "#1e293b",
          DEFAULT: "#1e293b",
        },
        muted: {
          light: "#64748b",
          dark: "#94a3b8",
          DEFAULT: "#94a3b8",
        },
        "glow-blue": {
          light: "#3b82f6",
          dark: "#60a5fa",
          DEFAULT: "#3b82f6",
        },
        "bell-amber": {
          light: "#f59e0b",
          dark: "#fbbf24",
          DEFAULT: "#f59e0b",
        },
        // Semantic colors
        success: "#10b981",
        warning: "#f59e0b",
        danger: "#ef4444",
        // Legacy bg structure (maintaining compatibility)
        bg: {
          primary: "#0a0f1c",
          secondary: "#111827",
          tertiary: "#1e293b",
          accent: "rgba(59, 130, 246, 0.05)",
        },
        accent: {
          primary: "#3b82f6",
          secondary: "#60a5fa",
          tertiary: "#1e40af",
          glow: "#60a5fa",
          DEFAULT: "#3b82f6",
        },
        pos: "#10b981",
        neg: "#ef4444",
        warn: "#f59e0b",
        text: {
          primary: "#f8fafc",
          secondary: "#cbd5e1",
          tertiary: "#94a3b8",
          muted: "#64748b",
        },
      },
      fontFamily: {
        display: ["Big Shoulders Display", "system-ui", "sans-serif"],
        sans: ["Instrument Sans", "system-ui", "ui-sans-serif", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
      letterSpacing: {
        tighter: "-0.02em",
        tight: "-0.01em",
        wide: "0.02em",
        wider: "0.05em",
      },
      animation: {
        "fade-in": "fadeIn 0.6s cubic-bezier(0.16, 1, 0.3, 1)",
        "fade-in-up": "fadeInUp 0.8s cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-in": "slideIn 0.6s cubic-bezier(0.16, 1, 0.3, 1)",
        "scale-in": "scaleIn 0.6s cubic-bezier(0.16, 1, 0.3, 1)",
        "pulse-glow": "pulseGlow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "scan": "scan 2s linear infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        fadeInUp: {
          "0%": { opacity: "0", transform: "translateY(24px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideIn: {
          "0%": { opacity: "0", transform: "translateX(-24px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.95)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        pulseGlow: {
          "0%, 100%": { opacity: "1", boxShadow: "0 0 20px rgba(16, 185, 129, 0.3)" },
          "50%": { opacity: "0.8", boxShadow: "0 0 40px rgba(16, 185, 129, 0.5)" },
        },
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
      },
      backdropBlur: {
        xs: "2px",
      },
      boxShadow: {
        glow: "0 0 20px rgba(16, 185, 129, 0.2)",
        "glow-lg": "0 0 40px rgba(16, 185, 129, 0.3)",
        card: "0 1px 3px rgba(0, 0, 0, 0.5)",
        "card-hover": "0 4px 12px rgba(0, 0, 0, 0.6)",
      },
    },
  },
  plugins: [],
};
