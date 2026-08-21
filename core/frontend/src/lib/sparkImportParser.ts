/**
 * Spark Import Parser
 *
 * Parses ES import statements from spark code (parent-side) to build
 * browser-native import maps for esm.sh CDN resolution.
 *
 * Handles:
 * - Named imports: import { X, Y } from 'package'
 * - Default imports: import X from 'package'
 * - Namespace imports: import * as X from 'package'
 * - Mixed: import X, { Y } from 'package'
 * - Side-effect imports: import 'package'
 * - Scoped packages: @scope/package
 *
 * Filters out:
 * - Relative paths (./foo, ../bar)
 * - URLs (https://...)
 * - CSS imports (import 'antd/dist/style.css')
 *
 * Strips:
 * - Dynamic import() calls (replaced with warning comment)
 */

// Pinned versions for core packages
const PINNED_VERSIONS: Record<string, string> = {
  'react': 'react@18',
  'react-dom': 'react-dom@18',
  'react-dom/client': 'react-dom@18/client',
  'recharts': 'recharts@2',
  'lucide-react': 'lucide-react',
}

// Packages that are part of react-dom (subpath imports)
const REACT_DOM_SUBPATHS = ['react-dom/client', 'react-dom/server']

export interface ParsedImports {
  /** Map from bare specifier to esm.sh URL */
  importMap: Record<string, string>
  /** Package names found in imports */
  packages: string[]
  /** Code with dynamic imports stripped */
  cleanedCode: string
}

/**
 * Extract the npm package name from a bare specifier.
 * Handles scoped packages: '@tanstack/react-query' → '@tanstack/react-query'
 * Handles subpaths: 'recharts/es6/chart' → 'recharts'
 * Handles react-dom subpaths specially to preserve them in import map.
 */
function extractPackageName(specifier: string): string {
  // Check for react-dom subpaths first
  for (const subpath of REACT_DOM_SUBPATHS) {
    if (specifier === subpath || specifier.startsWith(subpath + '/')) {
      return subpath
    }
  }

  if (specifier.startsWith('@')) {
    // Scoped: @scope/name or @scope/name/subpath
    const parts = specifier.split('/')
    return parts.length >= 2 ? `${parts[0]}/${parts[1]}` : specifier
  }
  // Unscoped: name or name/subpath
  return specifier.split('/')[0]
}

/**
 * Check if a specifier is a CSS import that should be filtered out.
 */
function isCssImport(specifier: string): boolean {
  return /\.css$/i.test(specifier)
}

/**
 * Check if a specifier is a relative path or URL (not a bare specifier).
 */
function isRelativeOrUrl(specifier: string): boolean {
  return specifier.startsWith('.') || specifier.startsWith('/') || specifier.includes('://')
}

/**
 * Build the esm.sh URL for a package specifier.
 * Core packages get pinned versions. All packages get ?external=react,react-dom.
 */
function buildEsmUrl(specifier: string): string {
  const pkg = extractPackageName(specifier)
  const pinned = PINNED_VERSIONS[specifier] || PINNED_VERSIONS[pkg]

  if (pinned) {
    // Core packages: use pinned version
    const isReactItself = pkg === 'react' || pkg === 'react-dom'
    return isReactItself
      ? `https://esm.sh/${pinned}`
      : `https://esm.sh/${pinned}?external=react,react-dom`
  }

  // External packages: use latest with react externalized
  return `https://esm.sh/${specifier}?external=react,react-dom`
}

// Regex to match ES import statements
// Matches: import { X } from 'pkg', import X from 'pkg', import * as X from 'pkg',
//          import X, { Y } from 'pkg', import 'pkg'
const IMPORT_REGEX = /import\s+(?:(?:\{[^}]*\}|[\w$]+(?:\s*,\s*\{[^}]*\})?|\*\s+as\s+[\w$]+)\s+from\s+)?['"]([^'"]+)['"]\s*;?/g

// Regex to match dynamic import() calls
const DYNAMIC_IMPORT_REGEX = /(?:await\s+)?import\s*\(\s*['"]([^'"]+)['"]\s*\)/g

/**
 * Parse import statements from spark code and build an import map.
 *
 * This runs on the parent side (not in iframe) to determine which
 * packages need to be in the import map before the iframe loads.
 */
export function parseImports(code: string): ParsedImports {
  const importMap: Record<string, string> = {}
  const packages = new Set<string>()

  // Always include react and react-dom (needed for JSX transpilation output)
  importMap['react'] = buildEsmUrl('react')
  importMap['react-dom'] = buildEsmUrl('react-dom')
  importMap['react-dom/client'] = buildEsmUrl('react-dom/client')

  // Parse static imports
  let match: RegExpExecArray | null
  const importRegex = new RegExp(IMPORT_REGEX.source, IMPORT_REGEX.flags)
  while ((match = importRegex.exec(code)) !== null) {
    const specifier = match[1]

    // Skip relative paths, URLs, and CSS imports
    if (isRelativeOrUrl(specifier) || isCssImport(specifier)) {
      continue
    }

    const pkg = extractPackageName(specifier)
    packages.add(pkg)

    // Add the exact specifier to import map (handles subpath imports)
    if (!importMap[specifier]) {
      importMap[specifier] = buildEsmUrl(specifier)
    }

    // Also add the base package if different from specifier
    if (pkg !== specifier && !importMap[pkg]) {
      importMap[pkg] = buildEsmUrl(pkg)
    }
  }

  // Strip dynamic import() calls
  let cleanedCode = code.replace(DYNAMIC_IMPORT_REGEX, '(/* dynamic import() not supported in sparks */ undefined)')

  // Strip CSS-only side-effect imports: import 'something.css';
  cleanedCode = cleanedCode.replace(
    /import\s+['"][^'"]*\.css['"]\s*;?\n?/g,
    '/* CSS imports not supported in sparks — use Tailwind CSS */\n'
  )

  return { importMap, packages: Array.from(packages), cleanedCode }
}

/**
 * Build import map JSON string for embedding in HTML.
 */
export function buildImportMapJSON(importMap: Record<string, string>): string {
  return JSON.stringify({ imports: importMap }, null, 2)
}

/**
 * Compute a hash of the import map for memoization.
 * When the hash doesn't change, the iframe doesn't need to reload.
 */
export function importMapHash(importMap: Record<string, string>): string {
  // Sort keys for deterministic hash
  const keys = Object.keys(importMap).sort()
  return keys.join(',')
}
