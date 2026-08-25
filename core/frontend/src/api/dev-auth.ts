/**
 * Development authentication bypass
 * This file provides mock authentication for development purposes
 * IMPORTANT: Remove or disable this in production!
 */

import type { LoginResponse, User } from './types'

const DEV_MODE = import.meta.env.DEV
const ENABLE_DEV_AUTH = import.meta.env.VITE_ENABLE_DEV_AUTH === 'true'

// Mock user for development
const mockUser: User = {
  id: '1',
  email: 'dev@example.com',
  first_name: 'Dev',
  last_name: 'User',
  is_active: true,
  is_verified: true,
  date_joined: new Date().toISOString(),
  avatar_url: null
}

// Mock tokens for development
const mockTokens = {
  access: 'dev-access-token-' + Date.now(),
  refresh: 'dev-refresh-token-' + Date.now()
}

/**
 * Check if we should use dev authentication
 */
export function useDevAuth() {
  return DEV_MODE && ENABLE_DEV_AUTH
}

/**
 * Mock login function for development
 */
export async function devLogin(email: string, password: string): Promise<LoginResponse> {
  // Simulate network delay
  await new Promise(resolve => setTimeout(resolve, 500))

  // Accept any credentials in dev mode
  if (email && password) {
    const isUnverified = email.toLowerCase() === 'unverified@example.com'
    return {
      access: mockTokens.access,
      refresh: mockTokens.refresh,
      user: {
        ...mockUser,
        email,
        is_verified: !isUnverified,
      }
    }
  }

  throw new Error('Invalid credentials')
}

/**
 * Mock registration function for development
 */
export async function devRegister(email: string, password: string, firstName: string, lastName: string) {
  // Simulate network delay
  await new Promise(resolve => setTimeout(resolve, 500))

  // Accept any valid input in dev mode
  if (email && password && firstName && lastName) {
    return {
      message: 'Registration successful',
      user: {
        ...mockUser,
        email: email,
        first_name: firstName,
        last_name: lastName,
        is_verified: false
      }
    }
  }

  throw new Error('All fields are required')
}