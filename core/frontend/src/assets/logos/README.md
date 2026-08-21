# Logos and Icons

This folder contains all the SVG assets for the Sterna application.

## Sterna Logos

### `sterna-logo.svg`
Default logo using `currentColor` - adapts to the surrounding text color.
Used in contexts where the logo should inherit the text color.

### `sterna-logo-gradient.svg`
Logo with colored gradients (indigo → violet → pink).
Used in contexts where the logo should appear in color with the brand's hues.

### `sterna-logo-simple.svg`
Simplified version with 2 curves instead of 3.
Used for small sizes (icons, favicons, etc.).

## Third-Party Icons

### `google-icon.svg`
Official Google icon with brand colors.
Used for the Google OAuth sign-in button.

## Usage

These SVG files are imported into React components via Vite:

```tsx
import Logo from '@/assets/logos/sterna-logo.svg?react'

function MyComponent() {
  return <Logo width={32} height={32} className="text-indigo-600" />
}
```

## Design

The Sterna logo represents three flowing, upward curves that evoke:
- The elegant flight of the tern (a seabird)
- Progress and excellence in AI quality
- Fluidity and agility

Design inspired by modern tech logos (Figma, Linear, Stripe).
