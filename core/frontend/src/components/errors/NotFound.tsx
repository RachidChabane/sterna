import { Link } from '@tanstack/react-router'
import { FileQuestion, Home, ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function NotFound() {
  const handleGoBack = () => {
    window.history.back()
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-muted/30 via-background to-muted/10" />

      {/* Content */}
      <div className="relative container mx-auto px-4 py-24">
        <div className="text-center max-w-2xl mx-auto">
          {/* Icon */}
          <div className="flex justify-center mb-8">
            <div className="relative">
              <div className="absolute inset-0 bg-accent-brand/20 blur-3xl rounded-full" />
              <FileQuestion className="h-32 w-32 text-accent-brand relative animate-pulse-slow" strokeWidth={1.5} />
            </div>
          </div>

          {/* 404 Text */}
          <h1 className="text-8xl font-bold text-foreground mb-4">
            <span className="bg-gradient-to-r from-brand-600 to-brand-500 dark:from-brand-400 dark:to-brand-500 bg-clip-text text-transparent">
              404
            </span>
          </h1>

          {/* Title */}
          <h2 className="text-3xl font-bold text-foreground mb-4">
            Page Not Found
          </h2>

          {/* Description */}
          <p className="text-xl text-muted-foreground mb-10 max-w-md mx-auto">
            The page you're looking for doesn't exist or has been moved.
          </p>

          {/* Action Buttons */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link to="/voice-rooms">
              <Button
                size="lg"
                className="bg-accent-brand hover:bg-accent-brand/90 text-white shadow-glow-brand w-full sm:w-auto"
              >
                <Home className="h-5 w-5 mr-2" />
                Back to Home
              </Button>
            </Link>

            <Button
              size="lg"
              variant="outline"
              onClick={handleGoBack}
              className="w-full sm:w-auto"
            >
              <ArrowLeft className="h-5 w-5 mr-2" />
              Go Back
            </Button>
          </div>

          {/* Helpful Links */}
          <div className="mt-12 pt-8 border-t border-border">
            <p className="text-sm text-muted-foreground mb-4">
              You might want to visit:
            </p>
            <div className="flex flex-wrap justify-center gap-4">
              <Link
                to="/voice-rooms"
                className="text-sm text-accent-brand hover:underline hover:text-accent-brand/80 transition-colors"
              >
                Home
              </Link>
              <Link
                to="/models"
                className="text-sm text-accent-brand hover:underline hover:text-accent-brand/80 transition-colors"
              >
                Model Catalog
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
