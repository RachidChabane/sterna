import React from 'react'
import LogoDefault from '@/assets/logos/sterna-logo.svg?react'
import LogoGradient from '@/assets/logos/sterna-logo-gradient.svg?react'

interface SternaLogoProps {
  className?: string
  size?: number
  variant?: 'default' | 'gradient'
}

export function SternaLogo({ className = '', size = 32, variant = 'default' }: SternaLogoProps) {
  const Logo = variant === 'gradient' ? LogoGradient : LogoDefault

  return (
    <Logo
      width={size}
      height={size}
      className={className}
      aria-label="Sterna Logo"
    />
  )
}
