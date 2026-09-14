import type { Config } from "tailwindcss";

/** Palette and elevation modelled on the Stripe dashboard: a light canvas,
 *  white surfaces hairlined in #e3e8ee, indigo accent, and very soft shadows. */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "rgb(var(--canvas) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        body: "rgb(var(--body) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        subtle: "rgb(var(--subtle) / <alpha-value>)",
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          hover: "rgb(var(--accent-hover) / <alpha-value>)",
          soft: "rgb(var(--accent-soft) / <alpha-value>)",
        },
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Ubuntu",
          "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 0 0 1px rgba(50,50,93,0.02), 0 2px 5px -1px rgba(50,50,93,0.08), 0 1px 3px -1px rgba(0,0,0,0.05)",
        raised:
          "0 0 0 1px rgba(50,50,93,0.03), 0 6px 14px -4px rgba(50,50,93,0.12), 0 2px 5px -2px rgba(0,0,0,0.06)",
        btn: "0 1px 1px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.07)",
      },
      letterSpacing: {
        label: "0.04em",
      },
    },
  },
  plugins: [],
};

export default config;
