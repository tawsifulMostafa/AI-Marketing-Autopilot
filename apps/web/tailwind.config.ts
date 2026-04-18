import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17130d",
        parchment: "#f6efe1",
        ember: "#f2643a",
        moss: "#66784f",
        tide: "#264f59",
        brass: "#d6a84f"
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        body: ["var(--font-body)", "Verdana", "sans-serif"]
      },
      boxShadow: {
        card: "0 24px 80px rgba(23, 19, 13, 0.13)"
      }
    }
  },
  plugins: []
};

export default config;
