/**
 * CodeBlock Component
 *
 * Modern code block with syntax highlighting and copy functionality.
 * Inspired by ChatGPT, Claude, and GitHub's minimalist flat design aesthetic.
 * Features hover-activated copy button, dark background in both themes, and subtle ring glow on hover.
 * Theme is configurable via global settings.
 */

import { useState, type HTMLAttributes, type CSSProperties } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { Check, Copy } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { useSettingsStore } from '@/store/settingsStore'
import { getCodeTheme } from '@/constants/codeThemes'

interface CodeBlockProps {
  children: string
  language?: string
  inline?: boolean
  className?: string
}

export function CodeBlock({ children, language, inline = false, className }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)
  const { isDark } = useTheme()
  const codeThemeId = useSettingsStore((state) => state.codeTheme)
  const codeTheme = getCodeTheme(codeThemeId)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(children)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Custom Pre component to force transparent backgrounds
  const CustomPre = ({ children, ...props }: HTMLAttributes<HTMLPreElement>) => (
    <pre {...props} style={{ ...props.style, margin: 0, padding: 0, background: 'transparent' }}>
      {children}
    </pre>
  )

  // Inline code (e.g., `variable`)
  if (inline) {
    return (
      <code
        className={cn(
          'px-1.5 py-0.5 rounded bg-secondary text-foreground font-mono text-sm',
          className
        )}
      >
        {children}
      </code>
    )
  }

  // Extract language from className if not provided (format: language-xxx)
  const lang = language || className?.replace(/language-/, '') || 'text'

  // Block code with syntax highlighting - Modern flat design
  return (
    <div className={cn(
      "group relative my-4 rounded-xl overflow-hidden transition-all duration-200",
      isDark
        ? "bg-[#0d1117] border border-slate-800 hover:border-slate-700 hover:ring-1 hover:ring-slate-700/50"
        : "bg-[#1e1e1e] border border-slate-700 hover:border-slate-600 hover:ring-1 hover:ring-slate-600/50"
    )}>
      {/* Header with language badge and copy button - Unified design */}
      <div className="flex items-center justify-between bg-transparent px-4 py-3">
        {/* Language badge - Consistent in both modes */}
        <span className="text-xs font-mono text-slate-400">
          {lang}
        </span>

        {/* Copy button - Appears on hover */}
        <button
          onClick={handleCopy}
          className={cn(
            'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium',
            'transition-all duration-200',
            'opacity-0 group-hover:opacity-100',
            'hover:bg-slate-700/50',
            'focus:outline-none focus:ring-2 focus:ring-accent-brand/50',
            copied
              ? 'text-accent-brand opacity-100'
              : 'text-slate-400 hover:text-slate-200'
          )}
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5" />
              <span>Copied!</span>
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" />
            </>
          )}
        </button>
      </div>

      {/* Code content with syntax highlighting */}
      <div
        className="overflow-x-auto px-4 pb-4 bg-transparent"
        style={{
          // Force all nested elements to have transparent background
          '--code-bg': 'transparent',
        } as CSSProperties}
      >
        <style>{`
          .codeblock-content * {
            background-color: transparent !important;
            border: none !important;
          }
        `}</style>
        <div className="codeblock-content">
          <SyntaxHighlighter
          language={lang}
          style={codeTheme.style}
          showLineNumbers={false}
          wrapLines={false}
          wrapLongLines={true}
          PreTag={CustomPre}
          lineProps={{
            style: {
              backgroundColor: 'transparent',
              display: 'block',
            },
          }}
          customStyle={{
            margin: 0,
            padding: 0,
            background: 'transparent',
            fontSize: '0.875rem',
            lineHeight: '1.7',
            letterSpacing: '0.01em',
            border: 'none',
            outline: 'none',
            color: codeTheme.textColor,
          }}
          codeTagProps={{
            style: {
              fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'SF Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace",
              fontWeight: '400',
              letterSpacing: '0.01em',
              WebkitFontSmoothing: 'antialiased',
              MozOsxFontSmoothing: 'grayscale',
              textRendering: 'optimizeLegibility',
              backgroundColor: 'transparent',
              color: codeTheme.textColor,
            },
          }}
        >
          {children.trim()}
        </SyntaxHighlighter>
        </div>
      </div>
    </div>
  )
}
