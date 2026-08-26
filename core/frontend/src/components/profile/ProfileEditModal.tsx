import { useState, useEffect, useRef } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuthStore } from '@/store/authStore'
import { useToast } from '@/hooks/use-toast'
import { api } from '@/api/client'
import { getApiErrorMessage } from '@/utils/errorMessages'
import { Camera, Loader2 } from 'lucide-react'

// Character limits
const MAX_NAME_LENGTH = 50

// Sanitize input to prevent XSS - strips HTML tags and dangerous characters
function sanitizeInput(input: string): string {
  return input
    .replace(/<[^>]*>/g, '') // Remove HTML tags
    .replace(/[<>'"&]/g, '') // Remove potentially dangerous characters
    .trim()
}

interface ProfileEditModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

// Allowed avatar file types
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
const MAX_FILE_SIZE = 5 * 1024 * 1024 // 5MB

export function ProfileEditModal({ open, onOpenChange }: ProfileEditModalProps) {
  const { user, fetchProfile } = useAuthStore()
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false)
  const [avatarError, setAvatarError] = useState(false)
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Form state
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')

  // Initialize form when modal opens
  useEffect(() => {
    if (open && user) {
      setFirstName(user.first_name || '')
      setLastName(user.last_name || '')
      setAvatarError(false)
      setAvatarPreview(null)
    }
  }, [open, user])

  // Get initials for avatar fallback
  const getInitials = () => {
    if (!user) return '?'
    const first = user.first_name?.charAt(0) || ''
    const last = user.last_name?.charAt(0) || ''
    if (first || last) return `${first}${last}`.toUpperCase()
    return user.email?.charAt(0).toUpperCase() || '?'
  }

  const handleAvatarClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Validate file type
    if (!ALLOWED_TYPES.includes(file.type)) {
      toast({
        title: 'Invalid file type',
        description: 'Please select a JPEG, PNG, GIF, or WebP image.',
        variant: 'destructive',
      })
      return
    }

    // Validate file size
    if (file.size > MAX_FILE_SIZE) {
      toast({
        title: 'File too large',
        description: 'Please select an image under 5MB.',
        variant: 'destructive',
      })
      return
    }

    // Show preview immediately
    const previewUrl = URL.createObjectURL(file)
    setAvatarPreview(previewUrl)
    setAvatarError(false)

    // Upload the file
    setIsUploadingAvatar(true)
    try {
      const formData = new FormData()
      formData.append('file', file)

      await api.post('/auth/profile/avatar/', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

      // Refresh profile to get the new avatar URL
      await fetchProfile()

      toast({
        title: 'Avatar updated',
        description: 'Your profile picture has been updated.',
      })
    } catch (error) {
      console.error('Failed to upload avatar:', error)
      // Revert preview on error
      setAvatarPreview(null)
      toast({
        title: 'Upload failed',
        description: getApiErrorMessage(error, 'Failed to upload avatar. Please try again.'),
        variant: 'destructive',
      })
    } finally {
      setIsUploadingAvatar(false)
      // Clean up preview URL
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl)
      }
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleSave = async () => {
    if (!user) return

    // Sanitize inputs
    const sanitizedFirstName = sanitizeInput(firstName)
    const sanitizedLastName = sanitizeInput(lastName)

    // Validate
    if (sanitizedFirstName.length > MAX_NAME_LENGTH || sanitizedLastName.length > MAX_NAME_LENGTH) {
      toast({
        title: 'Invalid input',
        description: `Names must be ${MAX_NAME_LENGTH} characters or less.`,
        variant: 'destructive',
      })
      return
    }

    setIsLoading(true)
    try {
      await api.patch('/auth/profile/', {
        first_name: sanitizedFirstName,
        last_name: sanitizedLastName,
      })

      // Refresh profile from server to ensure store has latest data
      await fetchProfile()

      toast({
        title: 'Profile updated',
        description: 'Your profile has been updated successfully.',
      })

      onOpenChange(false)
    } catch (error) {
      console.error('Failed to update profile:', error)
      toast({
        title: 'Update failed',
        description: getApiErrorMessage(error, 'Failed to update profile. Please try again.'),
        variant: 'destructive',
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleCancel = () => {
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px] p-0 gap-0 overflow-hidden">
        <DialogHeader className="p-6 pb-4">
          <DialogTitle className="text-lg font-semibold">Edit Profile</DialogTitle>
        </DialogHeader>

        <div className="px-6 pb-6 space-y-6">
          {/* Avatar Section */}
          <div className="flex justify-center">
            <div className="relative">
              {(avatarPreview || (user?.avatar_url && !avatarError)) ? (
                <img
                  src={avatarPreview || user?.avatar_url || undefined}
                  alt="Profile"
                  className="h-24 w-24 rounded-full object-cover ring-4 ring-muted"
                  crossOrigin="anonymous"
                  onError={() => {
                    if (!avatarPreview) setAvatarError(true)
                  }}
                />
              ) : (
                <div className="h-24 w-24 rounded-full bg-muted flex items-center justify-center ring-4 ring-background">
                  <span className="text-2xl font-semibold text-muted-foreground">
                    {getInitials()}
                  </span>
                </div>
              )}
              {/* Upload overlay when uploading */}
              {isUploadingAvatar && (
                <div className="absolute inset-0 h-24 w-24 rounded-full bg-black/50 flex items-center justify-center">
                  <Loader2 className="h-6 w-6 text-white animate-spin" />
                </div>
              )}
              {/* Camera icon overlay */}
              <button
                type="button"
                onClick={handleAvatarClick}
                disabled={isUploadingAvatar}
                className="absolute bottom-0 right-0 h-8 w-8 rounded-full bg-background border border-border flex items-center justify-center shadow-sm hover:bg-muted transition-colors disabled:opacity-50"
              >
                <Camera className="h-4 w-4 text-muted-foreground" />
              </button>
              {/* Hidden file input */}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/gif,image/webp"
                onChange={handleFileChange}
                className="hidden"
              />
            </div>
          </div>

          {/* Form Fields - 2 column grid */}
          <div className="grid grid-cols-2 gap-4">
            {/* First Name */}
            <div className="space-y-2">
              <Label htmlFor="firstName" className="text-xs text-muted-foreground">
                First name
              </Label>
              <Input
                id="firstName"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                placeholder="First name"
                className="bg-muted/50 border-border"
                maxLength={MAX_NAME_LENGTH}
                autoComplete="given-name"
              />
            </div>

            {/* Last Name */}
            <div className="space-y-2">
              <Label htmlFor="lastName" className="text-xs text-muted-foreground">
                Last name
              </Label>
              <Input
                id="lastName"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                placeholder="Last name"
                className="bg-muted/50 border-border"
                maxLength={MAX_NAME_LENGTH}
                autoComplete="family-name"
              />
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex justify-center gap-3 pt-2">
            <Button
              variant="outline"
              onClick={handleCancel}
              disabled={isLoading}
              className="min-w-[100px]"
            >
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={isLoading}
              className="min-w-[100px] bg-accent-brand hover:bg-accent-brand/90"
            >
              {isLoading ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
