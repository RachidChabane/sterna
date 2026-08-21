import { useEffect, useRef, useState } from 'react'
import apiClient from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Download, Loader2 } from 'lucide-react'

type Status = 'pending' | 'processing' | 'ready' | 'failed' | 'expired'

interface StatusBody {
  request_id: string
  status: Status
  requested_at: string
  download_url?: string
  expires_at?: string
  ready_at?: string
  error?: string
}

interface ApiError {
  response?: { data?: { error?: string }; status?: number }
}

export function DataExportSection() {
  const [requestId, setRequestId] = useState<string | null>(null)
  const [status, setStatus] = useState<StatusBody | null>(null)
  const [error, setError] = useState<string>('')
  const [submitting, setSubmitting] = useState(false)
  const pollRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [])

  const startPolling = (id: string) => {
    if (pollRef.current) window.clearInterval(pollRef.current)
    pollRef.current = window.setInterval(async () => {
      try {
        const res = await apiClient.get<StatusBody>(
          `/auth/account/data-export/${id}/`,
        )
        setStatus(res.data)
        if (res.data.status === 'ready' || res.data.status === 'failed') {
          if (pollRef.current) window.clearInterval(pollRef.current)
          pollRef.current = null
        }
      } catch {
        // Ignore transient errors; keep polling.
      }
    }, 5000)
  }

  const submit = async () => {
    setError('')
    setSubmitting(true)
    try {
      const res = await apiClient.post<StatusBody>(
        '/auth/account/data-export/',
        {},
      )
      setRequestId(res.data.request_id)
      setStatus(res.data)
      startPolling(res.data.request_id)
    } catch (e) {
      const err = e as ApiError
      if (err.response?.status === 429) {
        setError(
          err.response.data?.error ||
            'You can only request one export per 24 hours.',
        )
      } else {
        setError(err.response?.data?.error || 'Failed to request export.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const isWorking =
    status?.status === 'pending' || status?.status === 'processing'

  return (
    <Card>
      <CardHeader>
        <CardTitle>Export your data</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Download a zip of your profile, conversations, sparks, knowledge-base
          documents, usage logs, and audit log. Encrypted secrets (BYOK API
          keys, MCP credentials) are redacted.
        </p>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {status?.status === 'ready' && status.download_url && (
          <Alert>
            <AlertDescription>
              Your export is ready.{' '}
              <a
                href={status.download_url}
                target="_blank"
                rel="noreferrer noopener"
                className="font-medium underline"
              >
                Download zip
              </a>
              {status.expires_at && (
                <span className="ml-1 text-xs text-muted-foreground">
                  (expires {new Date(status.expires_at).toLocaleString()})
                </span>
              )}
            </AlertDescription>
          </Alert>
        )}

        {status?.status === 'failed' && (
          <Alert variant="destructive">
            <AlertDescription>
              {status.error || 'Export failed. Please try again.'}
            </AlertDescription>
          </Alert>
        )}

        <Button
          onClick={submit}
          disabled={submitting || isWorking}
          className="gap-2"
        >
          {(submitting || isWorking) && (
            <Loader2 className="h-4 w-4 animate-spin" />
          )}
          {!submitting && !isWorking && <Download className="h-4 w-4" />}
          {isWorking
            ? 'Preparing export…'
            : status?.status === 'ready'
              ? 'Request another export'
              : 'Request data export'}
        </Button>
      </CardContent>
    </Card>
  )
}
