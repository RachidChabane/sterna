/**
 * SparkRenderer - Sandboxed iframe renderer for React components
 *
 * Renders user/AI-generated React code in a secure sandboxed iframe.
 * Uses postMessage for communication between parent and iframe.
 *
 * Architecture:
 * - Import maps + esm.sh CDN resolve bare ES import specifiers at runtime
 * - All code executes as ES modules via <script type="module">
 * - Import map is immutable after first module script; iframe reloads only when imports change
 *
 * Security measures:
 * - Iframe sandbox without allow-same-origin
 * - Code size limit (100KB)
 * - Execution timeout (10s for module loading)
 * - Origin-validated postMessage communication
 */

import React, { useRef, useEffect, useState, useCallback, useMemo, Suspense, lazy } from 'react'
import { cn } from '@/lib/utils'
import { Loader2, AlertCircle, RefreshCw, ZoomIn, ZoomOut, Maximize } from 'lucide-react'
import { MarkdownRenderer } from './MarkdownRenderer'
import { MermaidRenderer } from './MermaidRenderer'

// DocumentDownloader statically imports pdfjs-dist and xlsx (~1MB combined)
// for its pdf/xlsx preview branches, but only csv/ics/pdf/docx/xlsx sparks
// ever render it. Split into its own chunk instead of shipping those parser
// libraries with every spark render.
const DocumentDownloader = lazy(() =>
  import('./DocumentDownloader').then((module) => ({
    default: module.DocumentDownloader,
  })),
)
import { parseImports, buildImportMapJSON, importMapHash } from '@/lib/sparkImportParser'

// Security constants
const MAX_CODE_SIZE = 100_000 // 100KB max code size

/** Asset data passed to spark code via window.__SPARK_ASSETS__ (canonical type from the sparks API) */
import type { SparkAsset } from '@/api/sparks'
export type { SparkAsset }

interface SparkRendererProps {
  code: string
  className?: string
  /** Compact mode for thumbnails - scales down the content */
  compact?: boolean
  /** Assets (images/videos) available to the spark via window.__SPARK_ASSETS__ */
  assets?: SparkAsset[]
  /** Framework type - determines which renderer to use */
  framework?: string
  /** Spark title - for document downloaders */
  title?: string
  /** Download URL for downloadable types */
  downloadUrl?: string | null
  /** Hide DocumentDownloader header (used in fullscreen dialog) */
  hideHeader?: boolean
  onError?: (error: string) => void
  onLoad?: () => void
}

// Generate the sandboxed HTML document with import map and ES module execution
// Security: iframe sandbox="allow-scripts" (without allow-same-origin) provides isolation
const generateSandboxHTML = (importMapJSON: string) => `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <!-- 1. Import map (MUST be before any type="module" scripts) -->
  <script type="importmap">${importMapJSON}</script>

  <!-- 2. Babel standalone (UMD, for JSX transpilation only) -->
  <script src="https://unpkg.com/@babel/standalone@7/babel.min.js"></script>

  <!-- 3. Tailwind CSS -->
  <script src="https://cdn.tailwindcss.com"></script>

  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: white;
    }
    #root { min-height: 100px; }
    .spark-error {
      color: #ef4444;
      padding: 16px;
      background: #fef2f2;
      border-radius: 8px;
      border: 1px solid #fecaca;
    }
    .spark-error pre {
      margin: 8px 0 0;
      font-size: 12px;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .spark-loading {
      display: flex;
      align-items: center;
      gap: 8px;
      color: #6b7280;
      padding: 16px;
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    .spark-spinner {
      width: 20px;
      height: 20px;
      border: 2px solid #e5e7eb;
      border-top-color: #3b82f6;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
  </style>

  <!-- 4. Bootstrap module: just signal ready (Babel is UMD, already available) -->
  <script type="module">
    window.__SPARK_LIBS_READY__ = true;
    window.parent.postMessage({ type: 'ready' }, '*');
  </script>

  <!-- 5. Classic script: message handler, renderComponent, zoom/pan -->
  <script>
    // Security: Code size limit (100KB)
    var MAX_CODE_SIZE = 100000;

    // Assets storage - available to spark code as window.__SPARK_ASSETS__
    window.__SPARK_ASSETS__ = {};

    // Zoom/pan support for SVG sparks
    window.__ZOOM_PAN_ENABLED__ = false;
    window.__ZOOM_PAN_SETUP__ = false;

    function setupZoomPan() {
      if (window.__ZOOM_PAN_SETUP__) return;
      window.__ZOOM_PAN_SETUP__ = true;

      var root = document.getElementById('root');
      if (!root) return;

      var scale = 1, panX = 0, panY = 0;
      var dragging = false, dragStartX = 0, dragStartY = 0, panStartX = 0, panStartY = 0;
      var MIN_SCALE = 0.25, MAX_SCALE = 5, ZOOM_FACTOR = 0.1;

      root.style.overflow = 'hidden';
      root.style.transformOrigin = '0 0';
      document.body.style.overflow = 'hidden';

      function applyTransform() {
        root.style.transform = 'translate(' + panX + 'px, ' + panY + 'px) scale(' + scale + ')';
      }

      window.__zoomPanReset__ = function() {
        scale = 1; panX = 0; panY = 0;
        applyTransform();
      };

      function zoomAtPoint(newScale, clientX, clientY) {
        var rect = root.getBoundingClientRect();
        var x = clientX - rect.left + root.scrollLeft;
        var y = clientY - rect.top + root.scrollTop;
        var ratio = newScale / scale;
        panX = x - ratio * (x - panX);
        panY = y - ratio * (y - panY);
        scale = newScale;
        applyTransform();
      }

      root.addEventListener('wheel', function(e) {
        e.preventDefault();
        var direction = e.deltaY < 0 ? 1 : -1;
        var newScale = direction > 0
          ? Math.min(scale * (1 + ZOOM_FACTOR), MAX_SCALE)
          : Math.max(scale / (1 + ZOOM_FACTOR), MIN_SCALE);
        zoomAtPoint(newScale, e.clientX, e.clientY);
      }, { passive: false });

      root.addEventListener('mousedown', function(e) {
        if (e.button !== 0) return;
        dragging = true;
        dragStartX = e.clientX; dragStartY = e.clientY;
        panStartX = panX; panStartY = panY;
        root.style.cursor = 'grabbing';
        e.preventDefault();
      });

      window.addEventListener('mousemove', function(e) {
        if (!dragging) return;
        panX = panStartX + (e.clientX - dragStartX);
        panY = panStartY + (e.clientY - dragStartY);
        applyTransform();
      });

      window.addEventListener('mouseup', function() {
        if (dragging) {
          dragging = false;
          root.style.cursor = '';
        }
      });

      window.__zoomPanZoom__ = function(action) {
        var center = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
        if (action === 'in') {
          var ns = Math.min(scale * (1 + ZOOM_FACTOR * 3), MAX_SCALE);
          zoomAtPoint(ns, center.x, center.y);
        } else if (action === 'out') {
          var ns = Math.max(scale / (1 + ZOOM_FACTOR * 3), MIN_SCALE);
          zoomAtPoint(ns, center.x, center.y);
        } else if (action === 'reset') {
          window.__zoomPanReset__();
        }
      };
    }

    // MutationObserver to detect when SVG content is rendered into #root
    var zoomPanObserver = new MutationObserver(function(mutations) {
      if (window.__ZOOM_PAN_ENABLED__ && document.getElementById('root').children.length > 0) {
        setupZoomPan();
        zoomPanObserver.disconnect();
      }
    });
    document.addEventListener('DOMContentLoaded', function() {
      var root = document.getElementById('root');
      if (root) zoomPanObserver.observe(root, { childList: true });
    });

    // Message handler for receiving code, assets, and zoom commands
    window.addEventListener('message', function(event) {
      if (!event.data) return;
      if (event.data.type === 'render') {
        // Enable zoom/pan if requested (for SVG sparks)
        if (event.data.enableZoomPan) {
          window.__ZOOM_PAN_ENABLED__ = true;
        }
        // Reset zoom/pan on re-render
        if (window.__zoomPanReset__) window.__zoomPanReset__();
        window.__ZOOM_PAN_SETUP__ = false;
        // Re-observe for new content
        var root = document.getElementById('root');
        if (root && window.__ZOOM_PAN_ENABLED__) {
          zoomPanObserver.observe(root, { childList: true });
        }
        // Set assets before rendering (keyed by asset ID for easy access)
        if (event.data.assets && Array.isArray(event.data.assets)) {
          window.__SPARK_ASSETS__ = {};
          event.data.assets.forEach(function(asset) {
            window.__SPARK_ASSETS__[asset.id] = {
              url: asset.url,
              type: asset.type,
              filename: asset.filename,
              width: asset.width,
              height: asset.height
            };
          });
        }
        renderComponent(event.data.code);
      }
      if (event.data.type === 'zoom' && window.__zoomPanZoom__) {
        window.__zoomPanZoom__(event.data.action);
      }
    });

    // Catch module load errors (failed esm.sh fetches, 404s)
    window.addEventListener('error', function(event) {
      if (event.filename && event.filename.indexOf('esm.sh') !== -1) {
        var pkg = event.filename.replace(/.*esm\\.sh\\//, '').replace(/[?#].*/, '');
        console.error('[Spark] Failed to load package: ' + pkg);
      }
    });
    window.addEventListener('unhandledrejection', function(event) {
      var msg = event.reason ? (event.reason.message || String(event.reason)) : 'Unknown error';
      if (msg.indexOf('esm.sh') !== -1 || msg.indexOf('Failed to fetch') !== -1) {
        var root = document.getElementById('root');
        if (root && !root.querySelector('.spark-error')) {
          root.innerHTML = '<div class="spark-error"><strong>Module Load Error</strong><pre>' +
            escapeHtml(msg) + '</pre></div>';
          window.parent.postMessage({ type: 'rendered', success: false, error: msg }, '*');
        }
      }
    });

    function renderComponent(code) {
      var root = document.getElementById('root');

      // Security: Validate code size
      if (code.length > MAX_CODE_SIZE) {
        root.innerHTML = '<div class="spark-error">' +
          '<strong>Code Too Large</strong>' +
          '<pre>Code exceeds maximum size limit of 100KB</pre>' +
          '</div>';
        window.parent.postMessage({
          type: 'rendered',
          success: false,
          error: 'Code exceeds maximum size limit of 100KB'
        }, '*');
        return;
      }

      // SVG: inject directly as HTML (not JSX)
      var trimmed = code.trim();
      if (trimmed.startsWith('<svg') || trimmed.startsWith('<?xml')) {
        try {
          root.innerHTML = '';
          root.style.padding = '0';
          document.body.style.padding = '0';
          root.innerHTML = code;
          var svgEl = root.querySelector('svg');
          if (svgEl) {
            if (!svgEl.getAttribute('width') && !svgEl.style.width) {
              svgEl.style.width = '100%';
              svgEl.style.height = 'auto';
            }
          }
          if (window.__ZOOM_PAN_ENABLED__) {
            setupZoomPan();
          }
          window.parent.postMessage({ type: 'rendered', success: true }, '*');
        } catch (error) {
          root.innerHTML = '<div class="spark-error"><strong>SVG Error</strong><pre>' + escapeHtml(error.message) + '</pre></div>';
          window.parent.postMessage({ type: 'rendered', success: false, error: error.message }, '*');
        }
        return;
      }

      // All code goes through the ES module path
      renderAsModule(code, root);
    }

    /**
     * ES module execution path.
     * Transpiles JSX with Babel, injects as <script type="module">.
     * Browser resolves imports via the import map → esm.sh CDN.
     */
    function renderAsModule(code, root) {
      // Two-tier timeout: 3s spinner, 10s hard timeout
      var spinnerTimer = null;
      var hardTimer = null;
      var rendered = false;

      function onRendered() {
        rendered = true;
        if (spinnerTimer) clearTimeout(spinnerTimer);
        if (hardTimer) clearTimeout(hardTimer);
      }

      // Listen for rendered message from the module script
      function moduleListener(event) {
        if (event.data && event.data.type === 'module-rendered') {
          onRendered();
          window.removeEventListener('message', moduleListener);
          if (event.data.success) {
            window.parent.postMessage({ type: 'rendered', success: true }, '*');
          } else {
            root.innerHTML = '<div class="spark-error"><strong>Render Error</strong><pre>' +
              escapeHtml(event.data.error) + '</pre></div>';
            window.parent.postMessage({ type: 'rendered', success: false, error: event.data.error }, '*');
          }
        }
      }
      window.addEventListener('message', moduleListener);

      spinnerTimer = setTimeout(function() {
        if (!rendered) {
          var loadingDiv = document.createElement('div');
          loadingDiv.className = 'spark-loading';
          loadingDiv.id = 'spark-module-loading';
          loadingDiv.innerHTML = '<div class="spark-spinner"></div><span>Loading packages...</span>';
          root.prepend(loadingDiv);
        }
      }, 3000);

      hardTimer = setTimeout(function() {
        if (!rendered) {
          onRendered();
          window.removeEventListener('message', moduleListener);
          root.innerHTML = '<div class="spark-error"><strong>Module Timeout</strong>' +
            '<pre>Module loading timed out (10s). The package may be too large or unavailable.</pre></div>';
          window.parent.postMessage({
            type: 'rendered',
            success: false,
            error: 'Module loading timed out (10s). Try a smaller or more common package.'
          }, '*');
        }
      }, 10000);

      try {
        // Transpile JSX → createElement, keeping imports intact (sourceType: 'module')
        var transpiledCode = Babel.transform(code, {
          presets: ['react'],
          filename: 'spark.tsx',
          sourceType: 'module'
        }).code;

        // Transform export default → window.__SPARK_COMPONENT__ assignment
        transpiledCode = transpiledCode
          .replace(/export\\s+default\\s+function\\s+(\\w+)/g, 'window.__SPARK_COMPONENT__ = function $1')
          .replace(/export\\s+default\\s+/g, 'window.__SPARK_COMPONENT__ = ');

        // Ensure React default import exists (needed for createElement after JSX transpilation)
        // Note: named imports like { useState } do NOT put React in scope,
        // so we only check for the default import (import React / import React,)
        if (!/import\\s+React[\\s,]/m.test(transpiledCode)) {
          transpiledCode = "import React from 'react';\\n" + transpiledCode;
        }

        // Append render bootstrap
        transpiledCode += "\\n" +
          "import { createRoot as __sparkCreateRoot } from 'react-dom/client';\\n" +
          "try {\\n" +
          "  var __sparkRoot = document.getElementById('root');\\n" +
          "  var __sparkLoading = document.getElementById('spark-module-loading');\\n" +
          "  if (__sparkLoading) __sparkLoading.remove();\\n" +
          "  __sparkRoot.innerHTML = '';\\n" +
          "  __sparkCreateRoot(__sparkRoot).render(React.createElement(window.__SPARK_COMPONENT__));\\n" +
          "  window.postMessage({ type: 'module-rendered', success: true }, '*');\\n" +
          "} catch (__sparkErr) {\\n" +
          "  console.error('Spark module render error:', __sparkErr);\\n" +
          "  window.postMessage({ type: 'module-rendered', success: false, error: __sparkErr.message }, '*');\\n" +
          "}\\n";

        // Remove old module script if exists (re-render case)
        var oldScript = document.getElementById('spark-module');
        if (oldScript) oldScript.remove();

        // Create and inject <script type="module">
        var moduleScript = document.createElement('script');
        moduleScript.type = 'module';
        moduleScript.id = 'spark-module';
        moduleScript.textContent = transpiledCode;
        document.body.appendChild(moduleScript);

      } catch (error) {
        onRendered();
        window.removeEventListener('message', moduleListener);
        console.error('Spark transpilation error:', error);
        root.innerHTML = '<div class="spark-error"><strong>Transpilation Error</strong><pre>' + escapeHtml(error.message) + '</pre></div>';
        window.parent.postMessage({ type: 'rendered', success: false, error: error.message }, '*');
      }
    }

    function escapeHtml(text) {
      var div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }
  </script>
</head>
<body>
  <div id="root">
    <div class="spark-loading">
      <div class="spark-spinner"></div>
      <span>Loading...</span>
    </div>
  </div>
</body>
</html>
`

export const SparkRenderer: React.FC<SparkRendererProps> = ({
  code,
  className,
  compact = false,
  assets = [],
  framework = 'react',
  title = '',
  downloadUrl,
  hideHeader = false,
  onError,
  onLoad,
}) => {
  // Dispatch to specialized renderers for non-iframe types
  if (framework === 'markdown') {
    return <MarkdownRenderer code={code} className={className} />
  }

  if (framework === 'mermaid') {
    return <MermaidRenderer code={code} className={className} onError={onError} onLoad={onLoad} />
  }

  if (framework === 'csv' || framework === 'ics' || framework === 'pdf' || framework === 'docx' || framework === 'xlsx') {
    return (
      <Suspense
        fallback={
          <div className={cn('flex items-center justify-center', compact ? 'h-full w-full' : 'p-8')}>
            <Loader2 className={cn('animate-spin text-muted-foreground', compact ? 'w-4 h-4' : 'w-6 h-6')} />
          </div>
        }
      >
        <DocumentDownloader
          framework={framework}
          title={title}
          code={code}
          downloadUrl={downloadUrl}
          hideHeader={hideHeader}
          compact={compact}
          className={className}
        />
      </Suspense>
    )
  }

  const isSvg = framework === 'svg'

  // Parse imports from code and build import map (parent-side)
  const parsedImports = useMemo(() => parseImports(code), [code])
  const importMap = useMemo(() => buildImportMapJSON(parsedImports.importMap), [parsedImports])
  const mapHash = useMemo(() => importMapHash(parsedImports.importMap), [parsedImports])

  // Only regenerate srcdoc when import set changes (not on every code edit)
  const srcdocRef = useRef(generateSandboxHTML(importMap))
  const prevHashRef = useRef(mapHash)
  if (mapHash !== prevHashRef.current) {
    srcdocRef.current = generateSandboxHTML(importMap)
    prevHashRef.current = mapHash
  }

  // For react/html/svg - use existing iframe sandbox
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'rendered' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)

  // Handle messages from iframe
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // Security: Only accept messages from our iframe
      if (event.source !== iframeRef.current?.contentWindow) return

      switch (event.data?.type) {
        case 'ready':
          setStatus('ready')
          // Security: Validate code size before sending
          if (code.length > MAX_CODE_SIZE) {
            setStatus('error')
            setError('Code exceeds maximum size limit of 100KB')
            onError?.('Code exceeds maximum size limit of 100KB')
            return
          }
          // Send cleaned code (dynamic imports stripped, CSS imports stripped)
          iframeRef.current?.contentWindow?.postMessage(
            { type: 'render', code: parsedImports.cleanedCode, assets, enableZoomPan: isSvg },
            '*'
          )
          break

        case 'rendered':
          if (event.data.success) {
            setStatus('rendered')
            setError(null)
            onLoad?.()
          } else {
            setStatus('error')
            setError(event.data.error)
            onError?.(event.data.error)
          }
          break
      }
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [code, parsedImports.cleanedCode, onError, onLoad])

  // Re-render when code or assets change (after initial load)
  useEffect(() => {
    if (status === 'rendered' || status === 'error') {
      // Security: Validate code size before sending
      if (code.length > MAX_CODE_SIZE) {
        setStatus('error')
        setError('Code exceeds maximum size limit of 100KB')
        onError?.('Code exceeds maximum size limit of 100KB')
        return
      }
      iframeRef.current?.contentWindow?.postMessage(
        { type: 'render', code: parsedImports.cleanedCode, assets, enableZoomPan: isSvg },
        '*'
      )
    }
  }, [code, parsedImports.cleanedCode, assets, status, onError])

  const handleRetry = useCallback(() => {
    setStatus('loading')
    setError(null)
    // Reload iframe with current import map
    if (iframeRef.current) {
      srcdocRef.current = generateSandboxHTML(importMap)
      iframeRef.current.srcdoc = srcdocRef.current
    }
  }, [importMap])

  return (
    <div className={cn(
      'relative overflow-hidden bg-white',
      !compact && 'rounded-lg border flex flex-col',
      compact && 'h-full w-full',
      className
    )}>
      {/* Loading overlay */}
      {status === 'loading' && (
        <div className="absolute inset-0 flex items-center justify-center bg-white z-10">
          <div className="flex flex-col items-center gap-2">
            <Loader2 className={cn("animate-spin text-muted-foreground", compact ? "w-4 h-4" : "w-6 h-6")} />
            {!compact && <span className="text-xs text-muted-foreground">Loading preview...</span>}
          </div>
        </div>
      )}

      {/* Error overlay */}
      {status === 'error' && error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-white z-10 p-4">
          <AlertCircle className={cn("text-destructive mb-2", compact ? "w-5 h-5" : "w-8 h-8")} />
          {!compact && (
            <>
              <p className="text-sm text-destructive font-medium mb-1">Render Error</p>
              <p className="text-xs text-muted-foreground text-center mb-3 max-w-xs line-clamp-3">
                {error}
              </p>
              <button
                onClick={handleRetry}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-secondary hover:bg-secondary/80 transition-colors"
              >
                <RefreshCw className="w-3 h-3" />
                Retry
              </button>
            </>
          )}
        </div>
      )}

      {/* Sandboxed iframe */}
      {compact ? (
        // Compact mode: Scale down a larger iframe to fit the container
        <div className="absolute inset-0 overflow-hidden">
          <iframe
            ref={iframeRef}
            srcDoc={srcdocRef.current}
            sandbox="allow-scripts"
            className="bg-white absolute top-0 left-0"
            style={{
              border: 'none',
              width: '200%',
              height: '200%',
              transform: 'scale(0.5)',
              transformOrigin: 'top left',
            }}
            title="Spark Preview"
          />
        </div>
      ) : (
        // Full mode: Normal iframe
        <iframe
          ref={iframeRef}
          srcDoc={srcdocRef.current}
          sandbox="allow-scripts"
          className="w-full flex-1 min-h-[200px] bg-white"
          style={{ border: 'none' }}
          title="Spark Preview"
        />
      )}

      {!compact && isSvg && status === 'rendered' && (
        <div className="absolute bottom-3 right-3 flex items-center gap-0.5 bg-black/50 backdrop-blur-sm rounded-lg p-0.5 z-20">
          <button
            onClick={() => iframeRef.current?.contentWindow?.postMessage({ type: 'zoom', action: 'out' }, '*')}
            className="p-1.5 hover:bg-white/20 rounded text-white/70 hover:text-white transition-colors"
            title="Zoom out"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => iframeRef.current?.contentWindow?.postMessage({ type: 'zoom', action: 'reset' }, '*')}
            className="p-1.5 hover:bg-white/20 rounded text-white/70 hover:text-white transition-colors"
            title="Reset zoom"
          >
            <Maximize className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => iframeRef.current?.contentWindow?.postMessage({ type: 'zoom', action: 'in' }, '*')}
            className="p-1.5 hover:bg-white/20 rounded text-white/70 hover:text-white transition-colors"
            title="Zoom in"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </div>
  )
}
