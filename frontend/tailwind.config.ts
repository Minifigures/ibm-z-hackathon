import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        ink: {
          900: "#0a0e14",
          800: "#0f141c",
          700: "#161c26",
          600: "#1f2632",
          500: "#2a3340",
        },
        accent: {
          DEFAULT: "#7cf2c8",
          muted: "#3b8c70",
        },
      },
    },
  },
  plugins: [],
};
export default config;
