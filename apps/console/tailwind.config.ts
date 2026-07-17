import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#07111f",
          900: "#0d1829",
          800: "#142238",
          700: "#20324d"
        }
      },
      boxShadow: {
        panel: "0 24px 80px rgba(7, 17, 31, 0.12)"
      }
    }
  },
  plugins: []
};

export default config;
