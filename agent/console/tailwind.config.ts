import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";
import { agentPrismTailwindColors } from "./src/components/agent-prism/theme";

const v = (n: string) => `hsl(var(--${n}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["Pretendard Variable", "Pretendard", "system-ui", "sans-serif"] },
      colors: {
        ...agentPrismTailwindColors,
        border: v("border"), input: v("input"), ring: v("ring"), background: v("background"), foreground: v("foreground"),
        primary: { DEFAULT: v("primary"), foreground: v("primary-foreground") },
        secondary: { DEFAULT: v("secondary"), foreground: v("secondary-foreground") },
        destructive: { DEFAULT: v("destructive"), foreground: v("destructive-foreground") },
        muted: { DEFAULT: v("muted"), foreground: v("muted-foreground") },
        accent: { DEFAULT: v("accent"), foreground: v("accent-foreground") },
        popover: { DEFAULT: v("popover"), foreground: v("popover-foreground") },
        card: { DEFAULT: v("card"), foreground: v("card-foreground") },
        run: v("run"), wait: v("wait"), pass: v("pass"), fail: v("fail"), seal: v("seal"),
        chart: { 1: v("chart-1"), 2: v("chart-2"), 3: v("chart-3"), 4: v("chart-4"), 5: v("chart-5") },
      },
      borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)" },
    },
  },
  plugins: [animate],
} satisfies Config;
