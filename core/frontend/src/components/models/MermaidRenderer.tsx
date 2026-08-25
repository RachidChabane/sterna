/**
 * MermaidRenderer - Renders mermaid diagrams in a sandboxed iframe
 *
 * Uses mermaid.js CDN loaded inside a sandboxed iframe for security.
 * Communicates via postMessage to send diagram code and receive errors.
 */

import React, { useRef, useEffect, useState, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { Loader2, AlertCircle, RefreshCw, ZoomIn, ZoomOut, Maximize } from 'lucide-react'

interface MermaidRendererProps {
  code: string
  className?: string
  onError?: (error: string) => void
  onLoad?: () => void
}

const generateMermaidHTML = () => `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, sans-serif;
      background: white;
      overflow: hidden;
    }
    #viewport {
      overflow: hidden;
      cursor: grab;
      width: 100%;
      height: 100vh;
    }
    #viewport.dragging { cursor: grabbing; }
    #diagram {
      transform-origin: 0 0;
      display: inline-block;
      padding: 16px;
    }
    .mermaid-error {
      color: #ef4444;
      padding: 16px;
      background: #fef2f2;
      border-radius: 8px;
      border: 1px solid #fecaca;
      font-size: 13px;
    }
    .mermaid-error pre {
      margin: 8px 0 0;
      font-size: 12px;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }
  </style>
  <script>
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme: 'default',
    });

    var scale = 1, panX = 0, panY = 0;
    var dragging = false, dragStartX = 0, dragStartY = 0, panStartX = 0, panStartY = 0;
    var MIN_SCALE = 0.25, MAX_SCALE = 5, ZOOM_FACTOR = 0.1;

    function applyTransform() {
      var diagram = document.getElementById('diagram');
      if (diagram) diagram.style.transform = 'translate(' + panX + 'px, ' + panY + 'px) scale(' + scale + ')';
    }

    function resetTransform() {
      scale = 1; panX = 0; panY = 0;
      applyTransform();
    }

    function zoomAtPoint(newScale, clientX, clientY) {
      var viewport = document.getElementById('viewport');
      var rect = viewport.getBoundingClientRect();
      var x = clientX - rect.left;
      var y = clientY - rect.top;
      var ratio = newScale / scale;
      panX = x - ratio * (x - panX);
      panY = y - ratio * (y - panY);
      scale = newScale;
      applyTransform();
    }

    window.addEventListener('message', async function(event) {
      if (!event.data) return;
      if (event.data.type === 'render') {
        resetTransform();
        await renderDiagram(event.data.code);
      }
      if (event.data.type === 'zoom') {
        var center = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
        if (event.data.action === 'in') {
          var ns = Math.min(scale * (1 + ZOOM_FACTOR * 3), MAX_SCALE);
          zoomAtPoint(ns, center.x, center.y);
        } else if (event.data.action === 'out') {
          var ns = Math.max(scale / (1 + ZOOM_FACTOR * 3), MIN_SCALE);
          zoomAtPoint(ns, center.x, center.y);
        } else if (event.data.action === 'reset') {
          resetTransform();
        }
      }
    });

    document.addEventListener('DOMContentLoaded', function() {
      var viewport = document.getElementById('viewport');

      viewport.addEventListener('wheel', function(e) {
        e.preventDefault();
        var direction = e.deltaY < 0 ? 1 : -1;
        var newScale = direction > 0
          ? Math.min(scale * (1 + ZOOM_FACTOR), MAX_SCALE)
          : Math.max(scale / (1 + ZOOM_FACTOR), MIN_SCALE);
        zoomAtPoint(newScale, e.clientX, e.clientY);
      }, { passive: false });

      viewport.addEventListener('mousedown', function(e) {
        if (e.button !== 0) return;
        dragging = true;
        dragStartX = e.clientX; dragStartY = e.clientY;
        panStartX = panX; panStartY = panY;
        viewport.classList.add('dragging');
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
          document.getElementById('viewport').classList.remove('dragging');
        }
      });
    });

    async function renderDiagram(code) {
      var container = document.getElementById('diagram');
      try {
        var result = await mermaid.render('mermaid-svg', code);
        container.innerHTML = result.svg;
        window.parent.postMessage({ type: 'rendered', success: true }, '*');
      } catch (error) {
        var msg = error.message || String(error);
        container.innerHTML = '<div class="mermaid-error"><strong>Diagram Error</strong><pre>' +
          msg.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</pre></div>';
        window.parent.postMessage({ type: 'rendered', success: false, error: msg }, '*');
      }
    }

    window.parent.postMessage({ type: 'ready' }, '*');
  </script>
</head>
<body>
  <div id="viewport">
    <div id="diagram">
      <div style="color: #6b7280; padding: 16px;">Loading diagram...</div>
    </div>
  </div>
</body>
</html>
`

export const MermaidRenderer: React.FC<MermaidRendererProps> = ({
  code,
  className,
  onError,
  onLoad,
}) => {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'rendered' | 'error'>('loading')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.source !== iframeRef.current?.contentWindow) return

      switch (event.data?.type) {
        case 'ready':
          setStatus('ready')
          iframeRef.current?.contentWindow?.postMessage(
            { type: 'render', code },
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
  }, [code, onError, onLoad])

  // Re-render when code changes
  useEffect(() => {
    if (status === 'rendered' || status === 'error') {
      iframeRef.current?.contentWindow?.postMessage(
        { type: 'render', code },
        '*'
      )
    }
  }, [code, status])

  const handleRetry = useCallback(() => {
    setStatus('loading')
    setError(null)
    if (iframeRef.current) {
      iframeRef.current.srcdoc = generateMermaidHTML()
    }
  }, [])

  return (
    <div className={cn(
      'relative overflow-hidden bg-white rounded-lg border flex flex-col',
      className
    )}>
      {status === 'loading' && (
        <div className="absolute inset-0 flex items-center justify-center bg-white z-10">
          <div className="flex flex-col items-center gap-2">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Loading diagram...</span>
          </div>
        </div>
      )}

      {status === 'error' && error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-white z-10 p-4">
          <AlertCircle className="w-8 h-8 text-destructive mb-2" />
          <p className="text-sm text-destructive font-medium mb-1">Diagram Error</p>
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
        </div>
      )}

      <iframe
        ref={iframeRef}
        srcDoc={generateMermaidHTML()}
        sandbox="allow-scripts"
        className="w-full flex-1 min-h-[200px] bg-white"
        style={{ border: 'none' }}
        title="Mermaid Diagram"
      />

      {status === 'rendered' && (
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
