/**
 * Type declarations for the untyped `vscode-icons-svg` package (v2.0.0).
 *
 * The package ships a single `get` function that maps a filename to the
 * raw.githubusercontent.com URL of the matching vscode-icons SVG
 * (falling back to `default_file.svg`). It always returns a string.
 */
declare module 'vscode-icons-svg' {
  export function get(filename?: string): string
}
