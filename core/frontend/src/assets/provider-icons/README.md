# Provider brand icons

Static SVG marks for AI model providers (OpenAI, Anthropic, Google, ...), used to
identify which provider/model a chat message, model picker entry, or voice-room
agent belongs to.

## Origin and license

These files are extracted from **[`@lobehub/icons-static-svg`](https://github.com/lobehub/lobe-icons)**
(npm, version 1.94.0), a plain-SVG sibling package of `@lobehub/icons` maintained by
LobeHub. That package is MIT licensed:

```
The MIT License (MIT)

Copyright (c) 2023 LobeHub
```

They are vendored here as static files (title elements stripped; otherwise
byte-identical path data) instead of depending on the npm package, to avoid pulling
in that package's much larger transitive dependency graph (`@lobehub/ui`, antd,
framer-motion, `@splinetool/runtime`, `@giscus/react`, ...) for the ~37 icons this
app actually renders. See `src/lib/provider-icons.tsx` for the React wrapper.

This MIT attribution should also be carried into the project's
`THIRD_PARTY_NOTICES.md` when one is generated for a release.

## Trademark note

Provider/brand marks (OpenAI, Anthropic, Google, Meta, ...) are trademarks of
their respective owners. Rendering them here to identify which model/provider a
message or agent belongs to is nominative use; no endorsement is implied.

## Layout

- `mono/<slug>.svg` — single-color marks (`fill="currentColor"`), for providers
  with no distinct brand color in the source set (e.g. OpenAI, Anthropic, Grok).
  Rendered by `lib/provider-icons.tsx` with an adaptive `color` override so
  they stay visible in both light and dark themes.
- `color/<slug>.svg` — native multi-color brand marks, rendered as-is.

## Usage

Imported as React components via `vite-plugin-svgr`, same convention as
`src/assets/logos/`:

```tsx
import OpenAIIcon from '@/assets/provider-icons/mono/openai.svg?react'
import ClaudeIcon from '@/assets/provider-icons/color/claude.svg?react'
```
