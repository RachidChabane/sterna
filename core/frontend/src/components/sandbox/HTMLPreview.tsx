/**
 * HTMLPreview Component
 *
 * Renders HTML with automatic resolution of linked CSS and JS files.
 * Converts <link> and <script src> tags to inline styles/scripts.
 */

import { useState, useEffect } from 'react'
import { fsAPI } from '@/api/fs'
import { Loader2 } from 'lucide-react'

interface HTMLPreviewProps {
  htmlContent: string
  currentFilePath: string
  userId?: string
  projectId?: string
}

export function HTMLPreview({ htmlContent, currentFilePath, userId, projectId }: HTMLPreviewProps) {
  const [processedHtml, setProcessedHtml] = useState<string>(htmlContent)
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    const processHTML = async () => {
      if (!userId || !projectId) {
        setProcessedHtml(htmlContent)
        return
      }

      setIsLoading(true)
      let html = htmlContent

      try {
        // Get the directory of the current HTML file
        const currentDir = currentFilePath.substring(0, currentFilePath.lastIndexOf('/'))

        // Extract all <link rel="stylesheet"> tags
        const linkRegex = /<link[^>]+rel=["']stylesheet["'][^>]*>/gi
        const linkMatches = html.match(linkRegex) || []

        for (const linkTag of linkMatches) {
          // Extract href attribute
          const hrefMatch = linkTag.match(/href=["']([^"']+)["']/i)
          if (!hrefMatch) continue

          const href = hrefMatch[1]

          // Skip external URLs
          if (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('//')) {
            continue
          }

          // Resolve relative path
          const cssPath = resolvePath(currentDir, href)

          try {
            // Read the CSS file
            const result = await fsAPI.readFile({
              user_id: userId,
              conversation_id: projectId,
              chat_id: projectId,
              path: cssPath,
            })

            if (result.success && result.content) {
              // Replace <link> tag with inline <style>
              const styleTag = `<style data-resolved-from="${href}">\n${result.content}\n</style>`
              html = html.replace(linkTag, styleTag)
            }
          } catch (error) {
            console.warn(`Failed to load CSS file: ${cssPath}`, error)
          }
        }

        // Extract all <script src="..."> tags (excluding external scripts)
        const scriptRegex = /<script[^>]+src=["']([^"']+)["'][^>]*><\/script>/gi
        let scriptMatch

        while ((scriptMatch = scriptRegex.exec(htmlContent)) !== null) {
          const fullTag = scriptMatch[0]
          const src = scriptMatch[1]

          // Skip external URLs
          if (src.startsWith('http://') || src.startsWith('https://') || src.startsWith('//')) {
            continue
          }

          // Resolve relative path
          const jsPath = resolvePath(currentDir, src)

          try {
            // Read the JS file
            const result = await fsAPI.readFile({
              user_id: userId,
              conversation_id: projectId,
              chat_id: projectId,
              path: jsPath,
            })

            if (result.success && result.content) {
              // Replace <script src="..."> with inline <script>
              const inlineScriptTag = `<script data-resolved-from="${src}">\n${result.content}\n</script>`
              html = html.replace(fullTag, inlineScriptTag)
            }
          } catch (error) {
            console.warn(`Failed to load JS file: ${jsPath}`, error)
          }
        }

        setProcessedHtml(html)
      } catch (error) {
        console.error('Error processing HTML:', error)
        setProcessedHtml(htmlContent)
      } finally {
        setIsLoading(false)
      }
    }

    processHTML()
  }, [htmlContent, currentFilePath, userId, projectId])

  if (isLoading) {
    return (
      <div className="h-full w-full bg-white flex items-center justify-center">
        <div className="flex items-center gap-2 text-slate-600">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="text-sm">Loading resources...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full w-full bg-white">
      <iframe
        srcDoc={processedHtml}
        title="HTML Preview"
        sandbox="allow-scripts allow-same-origin"
        className="w-full h-full border-0"
      />
    </div>
  )
}

/**
 * Resolve a relative path from a base directory
 */
function resolvePath(baseDir: string, relativePath: string): string {
  // Handle absolute paths
  if (relativePath.startsWith('/')) {
    return relativePath
  }

  // Split paths into segments
  const baseParts = baseDir ? baseDir.split('/').filter(Boolean) : []
  const relativeParts = relativePath.split('/').filter(Boolean)

  // Process .. and .
  const resultParts = [...baseParts]

  for (const part of relativeParts) {
    if (part === '..') {
      resultParts.pop()
    } else if (part !== '.') {
      resultParts.push(part)
    }
  }

  return '/' + resultParts.join('/')
}
