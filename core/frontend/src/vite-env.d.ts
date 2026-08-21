/// <reference types="vite/client" />
/// <reference types="vite-plugin-svgr/client" />

// Injected at build time via `define` in vite.config.ts / vitest.config.ts
declare const __APP_VERSION__: string

declare module '*?raw' {
  const content: string
  export default content
}
