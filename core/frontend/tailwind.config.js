/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      typography: {
        DEFAULT: {
          css: {
            img: {
              // Allow HTML height/width attributes to work
              height: null,
              width: null,
            },
          },
        },
      },
      fontFamily: {
        sans: [
          '"Hanken Grotesk Variable"',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          '"Noto Sans"',
          'Arial',
          'Tahoma',
          '"Helvetica Neue"',
          'sans-serif',
          '"Apple Color Emoji"',
          '"Segoe UI Emoji"',
          '"Noto Color Emoji"'
        ],
        // Characterful display grotesk for marketing/auth headings
        display: [
          '"Bricolage Grotesque Variable"',
          '"Hanken Grotesk Variable"',
          'system-ui',
          'sans-serif'
        ]
      },
      colors: {
        // Static cobalt-ink brand ramp (mirrors --accent-brand hue).
        // Raw shade utilities (bg-brand-500/10 etc.) resolve here.
        brand: {
          50: "#eef1fd",
          100: "#dce3fb",
          200: "#b9c6f7",
          300: "#91a5f1",
          400: "#6480ea",
          500: "#3d5ce4",
          600: "#1d3ee0",
          700: "#1731b4",
          800: "#132789",
          900: "#0f1e63",
          950: "#091238",
        },
        // Signal yellow — stamps, highlighter marks. Use sparingly.
        highlight: {
          DEFAULT: "hsl(var(--highlight))",
          foreground: "hsl(var(--highlight-foreground))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
          brand: "hsl(var(--accent-brand))",
          "brand-foreground": "hsl(var(--accent-brand-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 1px)",
        sm: "calc(var(--radius) - 2px)",
      },
      // Hard offset shadows — flat, engineered, no blur. The identity's
      // replacement for glow/elevation effects.
      boxShadow: {
        hard: "4px 4px 0 0 hsl(var(--shadow-ink))",
        "hard-sm": "2px 2px 0 0 hsl(var(--shadow-ink))",
        "hard-lg": "6px 6px 0 0 hsl(var(--shadow-ink))",
      },
      transitionTimingFunction: {
        bounce: "cubic-bezier(0.34, 1.56, 0.64, 1)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        "collapsible-down": {
          from: { height: "0", opacity: "0" },
          to: { height: "var(--radix-collapsible-content-height)", opacity: "1" },
        },
        "collapsible-up": {
          from: { height: "var(--radix-collapsible-content-height)", opacity: "1" },
          to: { height: "0", opacity: "0" },
        },
        "dropdown-in": {
          from: {
            opacity: "0",
            transform: "scale(0.95) translateY(-4px)",
          },
          to: {
            opacity: "1",
            transform: "scale(1) translateY(0)",
          },
        },
        "sparkle": {
          "0%, 100%": {
            opacity: "1",
            transform: "scale(1) rotate(0deg)",
          },
          "25%": {
            opacity: "0.7",
            transform: "scale(1.1) rotate(5deg)",
          },
          "50%": {
            opacity: "1",
            transform: "scale(1) rotate(0deg)",
          },
          "75%": {
            opacity: "0.8",
            transform: "scale(1.05) rotate(-5deg)",
          },
        },
        "ping-slow": {
          "0%": {
            transform: "scale(1)",
            opacity: "0.8",
          },
          "50%": {
            transform: "scale(1.15)",
            opacity: "0.4",
          },
          "100%": {
            transform: "scale(1)",
            opacity: "0.8",
          },
        },
        "orb-float": {
          "0%, 100%": {
            transform: "translateY(0)",
          },
          "50%": {
            transform: "translateY(-8px)",
          },
        },
        "float": {
          "0%, 100%": {
            transform: "translateY(0) scale(1)",
            opacity: "0.6",
          },
          "50%": {
            transform: "translateY(-12px) scale(1.2)",
            opacity: "1",
          },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "collapsible-down": "collapsible-down 0.3s ease-out",
        "collapsible-up": "collapsible-up 0.3s ease-out",
        "radial-glow": "softGlow 3s ease-in-out infinite",
        "message-in": "messageSlideIn 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94) both",
        "dropdown-in": "dropdown-in 0.15s ease-out",
        "sparkle": "sparkle 2s ease-in-out infinite",
        "ping-slow": "ping-slow 2s ease-in-out infinite",
        "orb-float": "orb-float 3s ease-in-out infinite",
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
    require('tailwindcss-animate'),
  ],
}