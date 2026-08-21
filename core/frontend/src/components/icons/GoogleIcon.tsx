import React from 'react'
import GoogleSvg from '@/assets/logos/google-icon.svg?react'

interface GoogleIconProps {
  className?: string
}

export function GoogleIcon({ className = 'h-5 w-5' }: GoogleIconProps) {
  return (
    <GoogleSvg
      className={className}
      aria-label="Google Icon"
    />
  )
}