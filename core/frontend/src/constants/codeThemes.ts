/**
 * Centralized Code Syntax Highlighting Themes
 *
 * This file contains all available code themes for syntax highlighting.
 * Used by CodeBlock, SyntaxHighlighter, and MarkdownTextarea components.
 */

import { darcula } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { coldarkDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { nightOwl } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { dracula } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { materialDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { nord } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { synthwave84 } from 'react-syntax-highlighter/dist/esm/styles/prism'

/**
 * Available code theme IDs
 */
export type CodeThemeId =
  | 'darcula'
  | 'oneDark'
  | 'vscDarkPlus'
  | 'coldarkDark'
  | 'nightOwl'
  | 'dracula'
  | 'materialDark'
  | 'nord'
  | 'synthwave84'

/**
 * Code theme definition
 */
export interface CodeTheme {
  id: CodeThemeId
  name: string
  description: string
  style: { [key: string]: React.CSSProperties }
  /** Token colors for Prism.js manual highlighting (used by MarkdownTextarea) */
  tokenColors: Record<string, string>
  /** Background color for the code block container */
  background: string
  /** Default text color */
  textColor: string
}

/**
 * Token color mappings for each theme
 * These are used by MarkdownTextarea for Prism.js manual highlighting
 */
const DARCULA_COLORS: Record<string, string> = {
  keyword: '#CC7832',
  'class-name': '#A9B7C6',
  function: '#FFC66D',
  string: '#6A8759',
  'template-string': '#6A8759',
  number: '#6897BB',
  boolean: '#CC7832',
  operator: '#A9B7C6',
  punctuation: '#A9B7C6',
  comment: '#808080',
  'block-comment': '#808080',
  'doc-comment': '#629755',
  property: '#9876AA',
  tag: '#E8BF6A',
  'attr-name': '#BAB529',
  'attr-value': '#6A8759',
  builtin: '#8888C6',
  variable: '#A9B7C6',
  constant: '#9876AA',
  regex: '#646695',
  important: '#CC7832',
  italic: '#A9B7C6',
  namespace: '#A9B7C6',
}

const ONE_DARK_COLORS: Record<string, string> = {
  keyword: '#C678DD',
  'class-name': '#E5C07B',
  function: '#61AFEF',
  string: '#98C379',
  'template-string': '#98C379',
  number: '#D19A66',
  boolean: '#D19A66',
  operator: '#56B6C2',
  punctuation: '#ABB2BF',
  comment: '#5C6370',
  'block-comment': '#5C6370',
  'doc-comment': '#5C6370',
  property: '#E06C75',
  tag: '#E06C75',
  'attr-name': '#D19A66',
  'attr-value': '#98C379',
  builtin: '#E5C07B',
  variable: '#E06C75',
  constant: '#D19A66',
  regex: '#98C379',
  important: '#C678DD',
  italic: '#ABB2BF',
  namespace: '#E5C07B',
}

const VSC_DARK_PLUS_COLORS: Record<string, string> = {
  keyword: '#569CD6',
  'class-name': '#4EC9B0',
  function: '#DCDCAA',
  string: '#CE9178',
  'template-string': '#CE9178',
  number: '#B5CEA8',
  boolean: '#569CD6',
  operator: '#D4D4D4',
  punctuation: '#D4D4D4',
  comment: '#6A9955',
  'block-comment': '#6A9955',
  'doc-comment': '#6A9955',
  property: '#9CDCFE',
  tag: '#569CD6',
  'attr-name': '#9CDCFE',
  'attr-value': '#CE9178',
  builtin: '#4EC9B0',
  variable: '#9CDCFE',
  constant: '#4FC1FF',
  regex: '#D16969',
  important: '#569CD6',
  italic: '#D4D4D4',
  namespace: '#4EC9B0',
}

const COLDARK_DARK_COLORS: Record<string, string> = {
  keyword: '#E06C75',
  'class-name': '#F0C674',
  function: '#8FBCBB',
  string: '#8FBCBB',
  'template-string': '#8FBCBB',
  number: '#F0C674',
  boolean: '#E06C75',
  operator: '#E5E9F0',
  punctuation: '#E5E9F0',
  comment: '#999999',
  'block-comment': '#999999',
  'doc-comment': '#999999',
  property: '#E5E9F0',
  tag: '#E06C75',
  'attr-name': '#F0C674',
  'attr-value': '#8FBCBB',
  builtin: '#F0C674',
  variable: '#E5E9F0',
  constant: '#F0C674',
  regex: '#8FBCBB',
  important: '#E06C75',
  italic: '#E5E9F0',
  namespace: '#F0C674',
}

const NIGHT_OWL_COLORS: Record<string, string> = {
  keyword: '#C792EA',
  'class-name': '#FFCB6B',
  function: '#82AAFF',
  string: '#ECC48D',
  'template-string': '#ECC48D',
  number: '#F78C6C',
  boolean: '#FF5874',
  operator: '#7FDBCA',
  punctuation: '#D6DEEB',
  comment: '#637777',
  'block-comment': '#637777',
  'doc-comment': '#637777',
  property: '#7FDBCA',
  tag: '#CAECE6',
  'attr-name': '#7FDBCA',
  'attr-value': '#ECC48D',
  builtin: '#ADDB67',
  variable: '#D6DEEB',
  constant: '#82AAFF',
  regex: '#ECC48D',
  important: '#C792EA',
  italic: '#D6DEEB',
  namespace: '#FFCB6B',
}

const DRACULA_COLORS: Record<string, string> = {
  keyword: '#FF79C6',
  'class-name': '#8BE9FD',
  function: '#50FA7B',
  string: '#F1FA8C',
  'template-string': '#F1FA8C',
  number: '#BD93F9',
  boolean: '#BD93F9',
  operator: '#FF79C6',
  punctuation: '#F8F8F2',
  comment: '#6272A4',
  'block-comment': '#6272A4',
  'doc-comment': '#6272A4',
  property: '#66D9EF',
  tag: '#FF79C6',
  'attr-name': '#50FA7B',
  'attr-value': '#F1FA8C',
  builtin: '#8BE9FD',
  variable: '#F8F8F2',
  constant: '#BD93F9',
  regex: '#F1FA8C',
  important: '#FF79C6',
  italic: '#F8F8F2',
  namespace: '#8BE9FD',
}

const MATERIAL_DARK_COLORS: Record<string, string> = {
  keyword: '#C792EA',
  'class-name': '#FFCB6B',
  function: '#82AAFF',
  string: '#C3E88D',
  'template-string': '#C3E88D',
  number: '#F78C6C',
  boolean: '#FF5370',
  operator: '#89DDFF',
  punctuation: '#BABED8',
  comment: '#546E7A',
  'block-comment': '#546E7A',
  'doc-comment': '#546E7A',
  property: '#FFCB6B',
  tag: '#F07178',
  'attr-name': '#FFCB6B',
  'attr-value': '#C3E88D',
  builtin: '#82AAFF',
  variable: '#BABED8',
  constant: '#F78C6C',
  regex: '#C3E88D',
  important: '#C792EA',
  italic: '#BABED8',
  namespace: '#FFCB6B',
}

const NORD_COLORS: Record<string, string> = {
  keyword: '#81A1C1',
  'class-name': '#8FBCBB',
  function: '#88C0D0',
  string: '#A3BE8C',
  'template-string': '#A3BE8C',
  number: '#B48EAD',
  boolean: '#81A1C1',
  operator: '#81A1C1',
  punctuation: '#ECEFF4',
  comment: '#616E88',
  'block-comment': '#616E88',
  'doc-comment': '#616E88',
  property: '#D8DEE9',
  tag: '#81A1C1',
  'attr-name': '#8FBCBB',
  'attr-value': '#A3BE8C',
  builtin: '#8FBCBB',
  variable: '#D8DEE9',
  constant: '#EBCB8B',
  regex: '#EBCB8B',
  important: '#81A1C1',
  italic: '#D8DEE9',
  namespace: '#8FBCBB',
}

const SYNTHWAVE_84_COLORS: Record<string, string> = {
  keyword: '#FEDE5D',
  'class-name': '#FF7EDB',
  function: '#36F9F6',
  string: '#FF8B39',
  'template-string': '#FF8B39',
  number: '#F97E72',
  boolean: '#FF7EDB',
  operator: '#36F9F6',
  punctuation: '#FFFFFF',
  comment: '#848BBD',
  'block-comment': '#848BBD',
  'doc-comment': '#848BBD',
  property: '#72F1B8',
  tag: '#FF7EDB',
  'attr-name': '#72F1B8',
  'attr-value': '#FF8B39',
  builtin: '#FE4450',
  variable: '#FFFFFF',
  constant: '#F97E72',
  regex: '#FF8B39',
  important: '#FEDE5D',
  italic: '#FFFFFF',
  namespace: '#FF7EDB',
}

/**
 * All available code themes
 */
export const CODE_THEMES: CodeTheme[] = [
  {
    id: 'darcula',
    name: 'Darcula',
    description: 'IntelliJ IDEA inspired dark theme',
    style: darcula,
    tokenColors: DARCULA_COLORS,
    background: '#2B2B2B',
    textColor: '#A9B7C6',
  },
  {
    id: 'oneDark',
    name: 'One Dark',
    description: 'Atom editor inspired theme',
    style: oneDark,
    tokenColors: ONE_DARK_COLORS,
    background: '#282C34',
    textColor: '#ABB2BF',
  },
  {
    id: 'vscDarkPlus',
    name: 'VS Code Dark+',
    description: 'Visual Studio Code default dark theme',
    style: vscDarkPlus,
    tokenColors: VSC_DARK_PLUS_COLORS,
    background: '#1E1E1E',
    textColor: '#D4D4D4',
  },
  {
    id: 'coldarkDark',
    name: 'Coldark Dark',
    description: 'Cool-toned accessible dark theme',
    style: coldarkDark,
    tokenColors: COLDARK_DARK_COLORS,
    background: '#111B27',
    textColor: '#E3E9F2',
  },
  {
    id: 'nightOwl',
    name: 'Night Owl',
    description: 'Designed for night owls and low-light',
    style: nightOwl,
    tokenColors: NIGHT_OWL_COLORS,
    background: '#011627',
    textColor: '#D6DEEB',
  },
  {
    id: 'dracula',
    name: 'Dracula',
    description: 'Popular vampire-inspired theme',
    style: dracula,
    tokenColors: DRACULA_COLORS,
    background: '#282A36',
    textColor: '#F8F8F2',
  },
  {
    id: 'materialDark',
    name: 'Material Dark',
    description: 'Google Material Design inspired',
    style: materialDark,
    tokenColors: MATERIAL_DARK_COLORS,
    background: '#212121',
    textColor: '#EEFFFF',
  },
  {
    id: 'nord',
    name: 'Nord',
    description: 'Arctic, north-bluish color palette',
    style: nord,
    tokenColors: NORD_COLORS,
    background: '#2E3440',
    textColor: '#D8DEE9',
  },
  {
    id: 'synthwave84',
    name: 'Synthwave 84',
    description: 'Retro 80s neon aesthetic',
    style: synthwave84,
    tokenColors: SYNTHWAVE_84_COLORS,
    background: '#262335',
    textColor: '#FFFFFF',
  },
]

/**
 * Default code theme ID
 */
export const DEFAULT_CODE_THEME: CodeThemeId = 'vscDarkPlus'

/**
 * Get a code theme by ID
 */
export function getCodeTheme(themeId: CodeThemeId): CodeTheme {
  return CODE_THEMES.find((t) => t.id === themeId) || CODE_THEMES[0]
}

/**
 * Generate Monaco Editor theme data from a CodeTheme.
 * Maps Prism token colors → Monaco token rules + editor chrome colors.
 */
export function getMonacoThemeData(themeId: CodeThemeId): {
  base: 'vs-dark'
  inherit: boolean
  rules: Array<{ token: string; foreground: string; fontStyle?: string }>
  colors: Record<string, string>
} {
  const theme = getCodeTheme(themeId)
  const tc = theme.tokenColors
  const strip = (hex: string) => hex.replace('#', '')

  const rules = [
    { token: 'comment', foreground: strip(tc.comment), fontStyle: 'italic' },
    { token: 'keyword', foreground: strip(tc.keyword) },
    { token: 'string', foreground: strip(tc.string) },
    { token: 'number', foreground: strip(tc.number) },
    { token: 'regexp', foreground: strip(tc.regex) },
    { token: 'operator', foreground: strip(tc.operator) },
    { token: 'namespace', foreground: strip(tc.namespace) },
    { token: 'type', foreground: strip(tc['class-name']) },
    { token: 'struct', foreground: strip(tc['class-name']) },
    { token: 'class', foreground: strip(tc.function) },
    { token: 'interface', foreground: strip(tc.namespace) },
    { token: 'parameter', foreground: strip(tc.variable) },
    { token: 'variable', foreground: strip(tc.variable) },
    { token: 'function', foreground: strip(tc.function) },
    { token: 'member', foreground: strip(tc.function) },
    { token: 'annotation', foreground: strip(tc['attr-name']) },
    { token: 'decorator', foreground: strip(tc['attr-name']) },
    { token: 'tag', foreground: strip(tc.tag) },
    { token: 'tag.html', foreground: strip(tc.tag) },
    { token: 'tag.xml', foreground: strip(tc.tag) },
    { token: 'metatag', foreground: strip(tc.keyword) },
    { token: 'delimiter.html', foreground: strip(tc.punctuation) },
    { token: 'attribute.name', foreground: strip(tc['attr-name']) },
    { token: 'attribute.name.html', foreground: strip(tc['attr-name']) },
    { token: 'attribute.value', foreground: strip(tc['attr-value']) },
    { token: 'attribute.value.html', foreground: strip(tc['attr-value']) },
    { token: 'string.html', foreground: strip(tc.string) },
    { token: 'tag.css', foreground: strip(tc.function) },
    { token: 'attribute.name.css', foreground: strip(tc.property) },
    { token: 'attribute.value.css', foreground: strip(tc.string) },
    { token: 'property.css', foreground: strip(tc.property) },
    { token: 'keyword.css', foreground: strip(tc.keyword) },
    { token: 'string.css', foreground: strip(tc.string) },
    { token: 'number.css', foreground: strip(tc.number) },
    { token: 'unit.css', foreground: strip(tc.number) },
    { token: 'identifier', foreground: strip(tc.variable) },
    { token: 'delimiter', foreground: strip(tc.punctuation) },
    { token: 'string.key.json', foreground: strip(tc.property) },
    { token: 'string.value.json', foreground: strip(tc.string) },
  ]

  // Derive editor chrome colors from the theme's background
  const bg = theme.background
  const fg = theme.textColor

  return {
    base: 'vs-dark',
    inherit: true,
    rules,
    colors: {
      'editor.background': bg,
      'editor.foreground': fg,
      'editor.lineHighlightBackground': lighten(bg, 8),
      'editor.selectionBackground': '#214283',
      'editor.inactiveSelectionBackground': '#3a3d41',
      'editorCursor.foreground': fg,
      'editorLineNumber.foreground': fade(fg, 0.4),
      'editorLineNumber.activeForeground': fade(fg, 0.7),
      'editor.selectionHighlightBackground': '#add6ff26',
      'editor.wordHighlightBackground': '#575757',
      'editorIndentGuide.background': lighten(bg, 12),
      'editorIndentGuide.activeBackground': lighten(bg, 24),
      'editorBracketMatch.background': '#0064001a',
      'editorBracketMatch.border': '#888888',
    },
  }
}

/** Lighten a hex color by a fixed amount (0–255 per channel). */
function lighten(hex: string, amount: number): string {
  const h = hex.replace('#', '')
  const r = Math.min(255, parseInt(h.slice(0, 2), 16) + amount)
  const g = Math.min(255, parseInt(h.slice(2, 4), 16) + amount)
  const b = Math.min(255, parseInt(h.slice(4, 6), 16) + amount)
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
}

/** Return hex color with alpha (0–1). */
function fade(hex: string, alpha: number): string {
  const a = Math.round(alpha * 255).toString(16).padStart(2, '0')
  return `${hex}${a}`
}

/**
 * Sample code for theme preview
 */
export const THEME_PREVIEW_CODE = `function greet(name: string) {
  const message = \`Hello, \${name}!\`;
  console.log(message);
  return true;
}`
