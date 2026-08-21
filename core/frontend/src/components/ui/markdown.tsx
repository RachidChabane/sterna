import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import rehypeKatex from 'rehype-katex'
import { CodeBlock } from './CodeBlock'
import { ExecutableCodeBlock } from '@/components/models/ExecutableCodeBlock'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { TooltipPortal } from '@/components/ui/tooltip'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useState, memo } from 'react'
import 'katex/dist/katex.min.css'

interface MarkdownProps {
  children: string
  className?: string
  webSources?: Array<{
    url: string
    title?: string
  }>
}

/**
 * Detects if text contains RTL (Right-to-Left) characters
 * Supports: Arabic, Hebrew, Persian, Urdu, and other RTL scripts
 */
const hasRTLChars = (text: string): boolean => {
  // Unicode ranges for RTL scripts:
  // \u0590-\u05FF: Hebrew
  // \u0600-\u06FF: Arabic
  // \u0700-\u074F: Syriac
  // \u0750-\u077F: Arabic Supplement
  // \u08A0-\u08FF: Arabic Extended-A
  // \uFB50-\uFDFF: Arabic Presentation Forms-A
  // \uFE70-\uFEFF: Arabic Presentation Forms-B
  const rtlRange = /[\u0590-\u05FF\u0600-\u06FF\u0700-\u074F\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/
  return rtlRange.test(text)
}

/**
 * Pre-processes text to wrap standalone LaTeX commands with math delimiters
 * This allows models to output LaTeX like \boxed{9.21} without explicit $ delimiters
 */
const preprocessLaTeX = (text: string): string => {
  // Common LaTeX commands that should be wrapped in math mode
  // Pattern matches: \command{...} or \command[...]{...} not already inside $ or $$
  const latexCommandPattern = /(?<!\$)\\(?:boxed|frac|sqrt|text|mathbf|mathit|mathrm|operatorname|binom|sum|int|prod|lim|displaystyle|tfrac|dfrac|cfrac)\{[^}]+\}(?!\$)/g

  // Wrap matched LaTeX commands with inline math delimiters
  let processed = text.replace(latexCommandPattern, (match) => `$${match}$`)

  // Also handle standalone Greek letters and common symbols
  const greekPattern = /(?<!\$)\\(?:alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|lambda|mu|nu|xi|pi|rho|sigma|tau|upsilon|phi|chi|psi|omega|Alpha|Beta|Gamma|Delta|Epsilon|Zeta|Eta|Theta|Iota|Kappa|Lambda|Mu|Nu|Xi|Pi|Rho|Sigma|Tau|Upsilon|Phi|Chi|Psi|Omega)(?!\$)/g
  processed = processed.replace(greekPattern, (match) => `$${match}$`)

  return processed
}

/**
 * Pre-processes markdown to remove parentheses around links
 * Transforms: "text ([link](url))" -> "text [link](url)"
 */
const preprocessMarkdownLinks = (text: string): string => {
  // Remove parentheses that wrap markdown links: ([text](url)) -> [text](url)
  return text.replace(/\(\[([^\]]+)\]\(([^)]+)\)\)/g, '[$1]($2)')
}

/**
 * Pre-processes markdown to mark citation links (links that appear after a period)
 * These will be rendered as badges, while all other links are underlined
 */
const preprocessCitationLinks = (text: string): string => {
  // Pattern: period followed by optional whitespace, then a markdown link
  // Mark these as citations by adding __CITE__ prefix to link text
  return text.replace(/\.\s*\[([^\]]+)\]\(([^)]+)\)/g, '.[__CITE__$1]($2)')
}

/**
 * Component to display grouped consecutive source links with navigation
 */
const SourceBadgeGroup = ({
  urls,
  webSources
}: {
  urls: string[]
  webSources?: Array<{ url: string; title?: string }>
}) => {
  const [currentIndex, setCurrentIndex] = useState(0)

  const currentUrl = urls[currentIndex]

  try {
    const url = new URL(currentUrl)
    const hostname = url.hostname
    const faviconUrl = `https://www.google.com/s2/favicons?domain=${hostname}&sz=32`

    // Extract domain name without TLD
    const domainParts = hostname.replace(/^www\./, '').split('.')
    const domainName = domainParts.length > 1 ? domainParts[0] : hostname

    // Find matching source
    const matchingSource = webSources?.find(source => source.url === currentUrl)

    const goToPrevious = () => {
      setCurrentIndex((prev) => (prev - 1 + urls.length) % urls.length)
    }

    const goToNext = () => {
      setCurrentIndex((prev) => (prev + 1) % urls.length)
    }

    return (
      <TooltipProvider >
        <Tooltip>
          <TooltipTrigger asChild>
            <a
              href={currentUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block no-underline"
            >
              <Badge
                variant="outline"
                className="px-1.5 py-0.5 text-[10px] cursor-pointer border-border/60 bg-background/50 hover:bg-background/80 transition-colors"
              >
                {domainName}
                {urls.length > 1 && <span className="ml-1 text-[9px] opacity-70">+{urls.length - 1}</span>}
              </Badge>
            </a>
          </TooltipTrigger>
          <TooltipPortal>
            <TooltipContent
              side="bottom"
              align="start"
              avoidCollisions={true}
              collisionPadding={16}
              sideOffset={4}
              className="p-0 bg-slate-900 border-brand-500/30 shadow-lg max-w-xs"
            >
              <div className="relative">
              <div className="p-3 flex items-center gap-3">
                <div className="flex-shrink-0 h-8 w-8 rounded-md border-2 border-brand-500/20 bg-slate-800 flex items-center justify-center overflow-hidden shadow-sm">
                  <img
                    src={faviconUrl}
                    alt={hostname}
                    className="h-5 w-5"
                    onError={(e) => {
                      const target = e.currentTarget
                      target.style.display = 'none'
                      const parent = target.parentElement
                      if (parent) {
                        parent.innerHTML = hostname.charAt(0).toUpperCase()
                        parent.className = 'flex-shrink-0 h-8 w-8 rounded-md bg-slate-800 border-2 border-brand-500/20 flex items-center justify-center text-sm font-semibold text-brand-400'
                      }
                    }}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm text-white">
                    {matchingSource?.title || domainName}
                  </div>
                </div>
              </div>

              {urls.length > 1 && (
                <div className="flex items-center justify-between px-3 pb-2 border-t border-brand-500/20 pt-2">
                  <button
                    onClick={(e) => {
                      e.preventDefault()
                      goToPrevious()
                    }}
                    className="p-1 hover:bg-slate-800 rounded transition-colors"
                    disabled={urls.length === 1}
                  >
                    <ChevronLeft className="h-4 w-4 text-slate-400" />
                  </button>

                  <div className="flex gap-1">
                    {urls.map((_, idx) => (
                      <div
                        key={idx}
                        className={cn(
                          "h-1.5 rounded-full transition-all",
                          idx === currentIndex
                            ? "w-4 bg-brand-500"
                            : "w-1.5 bg-slate-600"
                        )}
                      />
                    ))}
                  </div>

                  <button
                    onClick={(e) => {
                      e.preventDefault()
                      goToNext()
                    }}
                    className="p-1 hover:bg-slate-800 rounded transition-colors"
                    disabled={urls.length === 1}
                  >
                    <ChevronRight className="h-4 w-4 text-slate-400" />
                  </button>
                </div>
              )}
            </div>
            </TooltipContent>
          </TooltipPortal>
        </Tooltip>
      </TooltipProvider>
    )
  } catch (e) {
    return null
  }
}

// Memoize to prevent expensive re-parsing when parent re-renders
// Only re-parse if children (message content) or webSources actually change
export const Markdown = memo(function Markdown({ children, className, webSources }: MarkdownProps) {
  // Pre-process LaTeX commands, markdown links, and citation links
  let processedContent = preprocessLaTeX(children)
  processedContent = preprocessMarkdownLinks(processedContent)
  processedContent = preprocessCitationLinks(processedContent)

  // Detect and group consecutive links
  const linkGroups = new Map<string, string[]>()
  let groupId = 0

  // Pattern to detect consecutive links: ](url1)[text](url2)
  // Replace groups with a marker
  processedContent = processedContent.replace(
    /(\[([^\]]+)\]\(([^)]+)\))(\[([^\]]+)\]\(([^)]+)\))+/g,
    (match) => {
      // Extract all URLs from this group
      const urlPattern = /\[([^\]]+)\]\(([^)]+)\)/g
      const urls: string[] = []
      let urlMatch

      while ((urlMatch = urlPattern.exec(match)) !== null) {
        const url = urlMatch[2]
        // Only include http/https links
        if (url.startsWith('http://') || url.startsWith('https://')) {
          urls.push(url)
        }
      }

      if (urls.length > 1) {
        const currentGroupId = `LINK_GROUP_${groupId++}`
        linkGroups.set(currentGroupId, urls)
        // Replace with a single marker link
        return `[${currentGroupId}](${currentGroupId})`
      }

      return match
    }
  )

  // Auto-detect text direction for RTL languages
  const isRTL = hasRTLChars(processedContent)

  return (
    <div
      dir={isRTL ? 'rtl' : 'ltr'}
      className={cn(
        // Base prose styles with dark mode support
        'prose prose-base dark:prose-invert max-w-none break-words',
        // Link styling - subtle, blends with text
        'prose-a:text-foreground/90',
        'prose-a:underline prose-a:decoration-foreground/30 prose-a:underline-offset-2',
        'hover:prose-a:decoration-foreground/60',
        // Code styling - Enhanced contrast for both light and dark modes
        'prose-code:bg-slate-200 prose-code:text-slate-800 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded',
        'prose-code:border prose-code:border-slate-300',
        'dark:prose-code:bg-slate-800 dark:prose-code:text-slate-100 dark:prose-code:border-slate-700',
        'prose-code:font-medium',
        'prose-code:before:content-none prose-code:after:content-none',
        // Neutralize prose-pre styles (CodeBlock handles its own container)
        'prose-pre:p-0 prose-pre:m-0 prose-pre:bg-transparent prose-pre:border-0',
        // Text color adjustments for theme - use foreground for better accessibility
        'prose-p:text-foreground',
        'prose-li:text-foreground',
        'prose-headings:text-foreground',
        'prose-strong:text-foreground',
        className
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeRaw, rehypeSanitize, rehypeKatex]}
        components={{
          a({ node, href, children, ...props }) {
            // Check if this is a link group marker
            if (href?.startsWith('LINK_GROUP_')) {
              const urls = linkGroups.get(href)
              if (urls && urls.length > 0) {
                return <SourceBadgeGroup urls={urls} webSources={webSources} />
              }
              return null
            }

            // Check if it's an external link (http/https)
            const isExternal = href?.startsWith('http://') || href?.startsWith('https://')

            if (isExternal && href) {
              try {
                const url = new URL(href)
                const hostname = url.hostname
                const linkText = String(children)

                // Check if this is a citation link (marked with __CITE__ prefix)
                const isCitation = linkText.startsWith('__CITE__')
                const displayText = isCitation ? linkText.replace('__CITE__', '') : linkText

                if (isCitation) {
                  // Render as source badge (citation after a period)
                  const faviconUrl = `https://www.google.com/s2/favicons?domain=${hostname}&sz=32`

                  // Extract domain name without TLD (.com, .org, etc.)
                  const domainParts = hostname.replace(/^www\./, '').split('.')
                  const domainName = domainParts.length > 1 ? domainParts[0] : hostname

                  // Find matching source from webSources
                  const matchingSource = webSources?.find(source => source.url === href)

                  return (
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-block no-underline"
                          >
                            <Badge
                              variant="outline"
                              className="px-1.5 py-0.5 text-[10px] cursor-pointer border-border/60 bg-background/50 hover:bg-background/80 transition-colors"
                            >
                              {domainName}
                            </Badge>
                          </a>
                        </TooltipTrigger>
                        <TooltipPortal>
                          <TooltipContent
                            side="bottom"
                            align="start"
                            avoidCollisions={true}
                            collisionPadding={16}
                            sideOffset={4}
                            className="p-0 bg-slate-900 border-brand-500/30 shadow-lg max-w-xs"
                          >
                            <div className="p-3 flex items-center gap-3">
                              <div className="flex-shrink-0 h-8 w-8 rounded-md border-2 border-brand-500/20 bg-slate-800 flex items-center justify-center overflow-hidden shadow-sm">
                                <img
                                  src={faviconUrl}
                                  alt={hostname}
                                  className="h-5 w-5"
                                  onError={(e) => {
                                    // Fallback to first letter if favicon fails
                                    const target = e.currentTarget
                                    target.style.display = 'none'
                                    const parent = target.parentElement
                                    if (parent) {
                                      parent.innerHTML = hostname.charAt(0).toUpperCase()
                                      parent.className = 'flex-shrink-0 h-8 w-8 rounded-md bg-slate-800 border-2 border-brand-500/20 flex items-center justify-center text-sm font-semibold text-brand-400'
                                    }
                                  }}
                                />
                              </div>
                              <div className="font-semibold text-sm text-white">
                                {matchingSource?.title || displayText || domainName}
                              </div>
                            </div>
                          </TooltipContent>
                        </TooltipPortal>
                      </Tooltip>
                    </TooltipProvider>
                  )
                } else {
                  // Render as normal underlined link (default for all non-citation links)
                  return (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-foreground/90 underline decoration-foreground/30 underline-offset-2 hover:decoration-foreground/60 transition-all"
                      {...props}
                    >
                      {children}
                    </a>
                  )
                }
              } catch (e) {
                // If URL parsing fails, render normal link
                return <a href={href} {...props}>{children}</a>
              }
            }

            // For non-external links, render normally
            return <a href={href} {...props}>{children}</a>
          },
          img({ node, ...props }) {
            // Preserve HTML height/width attributes via inline styles
            const style: React.CSSProperties = {}
            if (props.height) {
              style.height = typeof props.height === 'number' ? `${props.height}px` : props.height
            }
            if (props.width) {
              style.width = typeof props.width === 'number' ? `${props.width}px` : props.width
            }
            return <img {...props} style={{ ...props.style, ...style }} />
          },
          code({ node, className, children, ...props }) {
            const codeString = String(children).replace(/\n$/, '')

            // react-markdown v9+ no longer passes an `inline` prop to the
            // code renderer. Detect inline code heuristically: no
            // language-* class and single-line content.
            const isInlineCode =
              !className?.includes('language-') &&
              !codeString.includes('\n')

            // Clean up backticks when we force inline rendering
            let cleanedCode = codeString
            if (isInlineCode) {
              // Remove surrounding backticks that weren't removed by ReactMarkdown
              cleanedCode = codeString.replace(/^`+|`+$/g, '')
            }

            // For inline code (single backticks), return simple <code> tag
            // Let prose-code styles handle the appearance
            if (isInlineCode) {
              return <code {...props}>{cleanedCode}</code>
            }

            // For block code (triple backticks), check if it's executable
            const match = /language-(\w+)/.exec(className || '')
            const language = match ? match[1] : ''

            // Check if language is executable (python, javascript, bash)
            const executableLanguages = ['python', 'py', 'python3', 'javascript', 'js', 'node', 'bash', 'sh', 'shell']
            const isExecutable = language && executableLanguages.includes(language.toLowerCase())

            // Use ExecutableCodeBlock for executable languages, CodeBlock for others
            if (isExecutable) {
              return (
                <ExecutableCodeBlock
                  code={codeString}
                  language={language}
                  className={className}
                />
              )
            }

            return (
              <CodeBlock
                inline={false}
                language={language}
                className={className}
              >
                {codeString}
              </CodeBlock>
            )
          },
        }}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  )
})
