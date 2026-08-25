/**
 * VideoPlayer Component
 *
 * A reusable video player component that handles:
 * - Direct download URL playback for inline storage
 * - Presigned URL fetching for R2-stored videos
 * - Loading states and error handling
 * - Play/Pause, Volume, Fullscreen controls
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Play,
  Pause,
  Volume2,
  VolumeX,
  Maximize,
  Minimize,
  Loader2,
  AlertCircle,
  RefreshCw,
  Film,
  Download,
  Repeat,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { assetsAPI } from '@/api/assets'

export interface VideoPlayerProps {
  /** Asset ID for the video */
  assetId: string
  /** Optional poster image URL */
  poster?: string
  /** Whether to autoplay (muted by default) */
  autoPlay?: boolean
  /** Whether to loop the video */
  loop?: boolean
  /** Whether to show controls */
  controls?: boolean
  /** Custom class name */
  className?: string
  /** Alt text for accessibility */
  alt?: string
  /** Callback when video ends */
  onEnded?: () => void
  /** Callback when video starts playing */
  onPlay?: () => void
  /** Callback on error */
  onError?: (error: string) => void
}

export function VideoPlayer({
  assetId,
  poster,
  autoPlay = false,
  loop = false,
  controls = true,
  className,
  alt,
  onEnded,
  onPlay,
  onError,
}: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const [videoUrl, setVideoUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isMuted, setIsMuted] = useState(autoPlay) // Muted by default for autoplay
  const [isLooping, setIsLooping] = useState(loop)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [showControls, setShowControls] = useState(true)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)

  // Hide controls after inactivity
  const controlsTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  // Fetch video URL (try presigned first, fallback to direct download)
  useEffect(() => {
    let mounted = true

    async function fetchVideoUrl() {
      setLoading(true)
      setError(null)

      try {
        // Try to get presigned URL first (better for large videos)
        const presigned = await assetsAPI.getPresignedUrl(assetId)
        if (!mounted) return

        if (presigned?.presigned_url) {
          setVideoUrl(presigned.presigned_url)
        } else {
          // Fallback to direct download URL
          setVideoUrl(assetsAPI.getDownloadUrl(assetId))
        }
      } catch (err) {
        if (!mounted) return
        console.error('[VideoPlayer] Failed to get video URL:', err)
        // Fallback to direct download URL on error
        setVideoUrl(assetsAPI.getDownloadUrl(assetId))
      } finally {
        if (mounted) {
          setLoading(false)
        }
      }
    }

    fetchVideoUrl()
    return () => { mounted = false }
  }, [assetId])

  // Handle video events
  const handleLoadedMetadata = useCallback(() => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration)
    }
    setLoading(false)
  }, [])

  const handleTimeUpdate = useCallback(() => {
    if (videoRef.current && duration > 0) {
      setProgress((videoRef.current.currentTime / duration) * 100)
    }
  }, [duration])

  const handleVideoError = useCallback(() => {
    const errorMsg = 'Failed to load video'
    setError(errorMsg)
    setLoading(false)
    onError?.(errorMsg)
  }, [onError])

  const handleEnded = useCallback(() => {
    setIsPlaying(false)
    onEnded?.()
  }, [onEnded])

  const handlePlay = useCallback(() => {
    setIsPlaying(true)
    onPlay?.()
  }, [onPlay])

  const handlePause = useCallback(() => {
    setIsPlaying(false)
  }, [])

  // Control handlers
  const togglePlay = useCallback(() => {
    if (!videoRef.current) return

    if (isPlaying) {
      videoRef.current.pause()
    } else {
      videoRef.current.play()
    }
  }, [isPlaying])

  const toggleMute = useCallback(() => {
    if (!videoRef.current) return
    videoRef.current.muted = !isMuted
    setIsMuted(!isMuted)
  }, [isMuted])

  const toggleLoop = useCallback(() => {
    if (!videoRef.current) return
    videoRef.current.loop = !isLooping
    setIsLooping(!isLooping)
  }, [isLooping])

  const toggleFullscreen = useCallback(async () => {
    if (!containerRef.current) return

    try {
      if (!isFullscreen) {
        await containerRef.current.requestFullscreen()
        setIsFullscreen(true)
      } else {
        await document.exitFullscreen()
        setIsFullscreen(false)
      }
    } catch (err) {
      console.error('[VideoPlayer] Fullscreen error:', err)
    }
  }, [isFullscreen])

  const handleSeek = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!videoRef.current) return

    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const percentage = x / rect.width
    videoRef.current.currentTime = percentage * duration
    setProgress(percentage * 100)
  }, [duration])

  const handleRetry = useCallback(() => {
    setError(null)
    setLoading(true)
    if (videoRef.current) {
      videoRef.current.load()
    }
  }, [])

  // Show/hide controls on mouse movement
  const handleMouseMove = useCallback(() => {
    setShowControls(true)
    if (controlsTimeoutRef.current) {
      clearTimeout(controlsTimeoutRef.current)
    }
    if (isPlaying) {
      controlsTimeoutRef.current = setTimeout(() => {
        setShowControls(false)
      }, 3000)
    }
  }, [isPlaying])

  // Listen for fullscreen change
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement)
    }
    document.addEventListener('fullscreenchange', handleFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange)
  }, [])

  // Format time as MM:SS
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const currentTime = videoRef.current?.currentTime || 0

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative group bg-black rounded-lg overflow-hidden",
        className
      )}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => isPlaying && setShowControls(false)}
    >
      {/* Loading state */}
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-muted/20">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-muted/20 gap-3">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm text-destructive">{error}</p>
          <button
            onClick={handleRetry}
            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-muted hover:bg-muted/80 rounded-md transition-colors"
          >
            <RefreshCw className="h-4 w-4" />
            Retry
          </button>
        </div>
      )}

      {/* Video element */}
      {videoUrl && !error && (
        <video
          ref={videoRef}
          src={videoUrl}
          poster={poster}
          autoPlay={autoPlay}
          loop={isLooping}
          muted={isMuted}
          playsInline
          onClick={togglePlay}
          onLoadedMetadata={handleLoadedMetadata}
          onTimeUpdate={handleTimeUpdate}
          onError={handleVideoError}
          onEnded={handleEnded}
          onPlay={handlePlay}
          onPause={handlePause}
          className="w-full h-full object-contain cursor-pointer"
          aria-label={alt}
        />
      )}

      {/* Custom controls overlay */}
      {controls && videoUrl && !error && !loading && (
        <div
          className={cn(
            "absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent",
            "transition-opacity duration-300 p-3 pt-10",
            showControls ? "opacity-100" : "opacity-0 pointer-events-none"
          )}
        >
          {/* Progress bar - hidden when looping */}
          {!isLooping && (
            <div
              className="w-full h-1.5 bg-white/30 rounded-full cursor-pointer mb-3 group/progress"
              onClick={handleSeek}
            >
              <div
                className="h-full bg-accent-brand rounded-full relative transition-all"
                style={{ width: `${progress}%` }}
              >
                <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full opacity-0 group-hover/progress:opacity-100 transition-opacity" />
              </div>
            </div>
          )}

          {/* Controls row */}
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              {/* Play/Pause */}
              <button
                onClick={togglePlay}
                className="p-1.5 hover:bg-white/20 rounded-full transition-colors"
                aria-label={isPlaying ? 'Pause' : 'Play'}
              >
                {isPlaying ? (
                  <Pause className="h-5 w-5 text-white" />
                ) : (
                  <Play className="h-5 w-5 text-white" />
                )}
              </button>

              {/* Volume */}
              <button
                onClick={toggleMute}
                className="p-1.5 hover:bg-white/20 rounded-full transition-colors"
                aria-label={isMuted ? 'Unmute' : 'Mute'}
              >
                {isMuted ? (
                  <VolumeX className="h-5 w-5 text-white" />
                ) : (
                  <Volume2 className="h-5 w-5 text-white" />
                )}
              </button>

              {/* Loop toggle */}
              <button
                onClick={toggleLoop}
                className={cn(
                  "p-1.5 rounded-full transition-colors",
                  isLooping ? "bg-accent-brand/30 hover:bg-accent-brand/40" : "hover:bg-white/20"
                )}
                aria-label={isLooping ? 'Disable loop' : 'Enable loop'}
              >
                <Repeat className={cn("h-5 w-5", isLooping ? "text-accent-brand" : "text-white")} />
              </button>

              {/* Time display - hidden when looping */}
              {!isLooping && (
                <span className="text-sm text-white/80 font-mono">
                  {formatTime(currentTime)} / {formatTime(duration)}
                </span>
              )}
            </div>

            <div className="flex items-center gap-1">
              {/* Download */}
              <a
                href={videoUrl || '#'}
                download={`video-${assetId}.mp4`}
                onClick={(e) => e.stopPropagation()}
                className="p-1.5 hover:bg-white/20 rounded-full transition-colors"
                aria-label="Download video"
              >
                <Download className="h-5 w-5 text-white" />
              </a>

              {/* Fullscreen */}
              <button
                onClick={toggleFullscreen}
                className="p-1.5 hover:bg-white/20 rounded-full transition-colors"
                aria-label={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
              >
                {isFullscreen ? (
                  <Minimize className="h-5 w-5 text-white" />
                ) : (
                  <Maximize className="h-5 w-5 text-white" />
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Play button overlay when paused */}
      {!loading && !error && !isPlaying && showControls && (
        <button
          onClick={togglePlay}
          className="absolute inset-0 flex items-center justify-center bg-black/20 hover:bg-black/30 transition-colors"
          aria-label="Play video"
        >
          <div className="w-16 h-16 rounded-full bg-white/90 flex items-center justify-center shadow-lg">
            <Play className="h-8 w-8 text-black ml-1" />
          </div>
        </button>
      )}
    </div>
  )
}

// ============================================================================
// VideoThumbnail Component - Lightweight thumbnail using video's first frame
// ============================================================================

export interface VideoThumbnailProps {
  /** Asset ID for the video */
  assetId: string
  /** Custom class name */
  className?: string
  /** Alt text for accessibility */
  alt?: string
}

/**
 * Lightweight video thumbnail that shows the first frame of a video.
 * Uses preload="metadata" to minimize bandwidth usage.
 */
export function VideoThumbnail({
  assetId,
  className,
  alt = 'Video thumbnail',
}: VideoThumbnailProps) {
  const [videoUrl, setVideoUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  // Fetch video URL
  useEffect(() => {
    let mounted = true

    async function fetchVideoUrl() {
      try {
        // Try presigned URL first for better compatibility
        const presigned = await assetsAPI.getPresignedUrl(assetId)
        if (!mounted) return

        if (presigned?.presigned_url) {
          setVideoUrl(presigned.presigned_url)
        } else {
          setVideoUrl(assetsAPI.getDownloadUrl(assetId))
        }
      } catch (err) {
        if (!mounted) return
        setVideoUrl(assetsAPI.getDownloadUrl(assetId))
      }
    }

    fetchVideoUrl()
    return () => { mounted = false }
  }, [assetId])

  return (
    <div className={cn("relative w-full h-full bg-black/20", className)}>
      {videoUrl && !error ? (
        <video
          src={videoUrl}
          preload="metadata"
          muted
          playsInline
          className="w-full h-full object-cover"
          aria-label={alt}
          onLoadedData={() => setLoading(false)}
          onError={() => {
            setError(true)
            setLoading(false)
          }}
        />
      ) : null}

      {/* Loading/error fallback */}
      {(loading || error || !videoUrl) && (
        <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-br from-purple-500/10 to-black/30">
          <Film className="h-10 w-10 text-muted-foreground/50" />
        </div>
      )}
    </div>
  )
}
