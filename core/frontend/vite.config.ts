import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import svgr from 'vite-plugin-svgr'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

// versions.json lives one level up (core/) and is absent when only the
// frontend directory is copied into a build context (docker image build).
let versions: { frontend?: string } = {}
try {
  versions = JSON.parse(
    readFileSync(new URL('../versions.json', import.meta.url), 'utf-8'),
  )
} catch {
  versions = { frontend: process.env.APP_VERSION ?? '0.0.0' }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  define: {
    __APP_VERSION__: JSON.stringify(versions.frontend ?? '0.0.0'),
  },
  // Strip console.* and debugger statements from production bundles
  // only — dev keeps full console output for debugging.
  esbuild: mode === 'production' ? { drop: ['console', 'debugger'] } : {},
  plugins: [
    svgr(), // Must be before react() to transform SVG imports
    TanStackRouterVite({
      routesDirectory: './src/routes',
      generatedRouteTree: './src/routeTree.gen.ts',
      routeFileIgnorePattern: '(\\.test\\.|__tests__)',
      // Split each route's component (and pending/error/notFound components)
      // into its own lazy-loaded chunk instead of bundling every page into
      // the entry chunk. Paired with `defaultPreload: 'intent'` in App.tsx,
      // route chunks are fetched on hover/touch so navigation stays instant.
      autoCodeSplitting: true,
    }),
    react()
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',  // Allow external connections for Docker
    port: 5173,
    watch: {
      // Ignore generated files to prevent loops
      ignored: ['**/routeTree.gen.ts', '**/node_modules/**'],
    },
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8080',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  // Optimize deps to prevent unnecessary rebuilds
  optimizeDeps: {
    include: ['pdfjs-dist'],
  },
  build: {
    // Disable source maps in production to prevent exposing source code
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          pdfjs: ['pdfjs-dist'],
        },
      },
    },
  },
}))
