import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        tribunal: {
          rider: "#2563eb",
          driver: "#dc2626",
          judge: "#7c3aed",
          synthetic: "#f59e0b",
          escalation: "#ef4444",
          verified: "#16a34a",
          unverified: "#ca8a04",
          disputed: "#ea580c",
          unverifiable: "#6b7280",
        },
      },
    },
  },
  plugins: [],
};

export default config;
