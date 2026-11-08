/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Neutral, restrained financial-terminal palette
        ink: {
          950: "#0a0e14",
          900: "#0f141c",
          850: "#131a24",
          800: "#1a2230",
          700: "#242f40",
          600: "#33405a",
        },
        accent: {
          DEFAULT: "#38bdf8",
          dim: "#0ea5e9",
        },
        pos: "#34d399",
        neg: "#f87171",
        warn: "#fbbf24",
        muted: "#8b98ab",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
