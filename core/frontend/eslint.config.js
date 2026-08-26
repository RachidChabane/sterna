import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

const NO_BARE_FETCH_MESSAGE =
  'Use the central axios client (src/api/client.ts) for JSON requests, or fetchStream from src/api/transport.ts for SSE streams and binary/blob responses. Do not call fetch() directly.'

export default defineConfig([
  globalIgnores(['dist', 'src/api/generated']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs['recommended-latest'],
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // Every occurrence of the `any` escape hatch defeats the type checker
      // at that point in the program; the codebase carries zero of them, so
      // this rule is a hard error rather than the recommended-config warn.
      '@typescript-eslint/no-explicit-any': 'error',
      // no-restricted-globals (not no-restricted-syntax) for the bare
      // `fetch` identifier: it's scope-aware, so a local binding named
      // `fetch` (e.g. a destructured store action) does not trigger it —
      // only an actual reference to the global does.
      'no-restricted-globals': ['error', { name: 'fetch', message: NO_BARE_FETCH_MESSAGE }],
      'no-restricted-syntax': [
        'error',
        {
          selector:
            "CallExpression[callee.type='MemberExpression'][callee.object.name='window'][callee.property.name='fetch']",
          message: NO_BARE_FETCH_MESSAGE,
        },
        {
          selector:
            "CallExpression[callee.type='MemberExpression'][callee.object.name='globalThis'][callee.property.name='fetch']",
          message: NO_BARE_FETCH_MESSAGE,
        },
      ],
    },
  },
  {
    // The one module allowed to call the global fetch() directly: the
    // shared stream transport every SSE/blob call site is routed through.
    files: ['src/api/transport.ts'],
    rules: {
      'no-restricted-globals': 'off',
      'no-restricted-syntax': 'off',
    },
  },
])
