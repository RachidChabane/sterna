import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, Loader2, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'

type ApiKeyStatus = {
  configured: boolean
  source: 'user_byok' | 'provisioned' | 'session' | null
  is_provisioned: boolean
  has_system_fallback: boolean
}

type ProviderKeyInfo = {
  provider: string
  label: string
  configured: boolean
  masked_key: string | null
}

const SETTINGS_ENDPOINT = '/api/settings/openrouter/'
const PROVIDER_KEYS_ENDPOINT = '/api/settings/provider-keys/'

async function authFetch(input: string, init?: RequestInit): Promise<Response> {
  const { getAccessToken } = await import('@/api/client')
  const accessToken = getAccessToken()
  return fetch(input, {
    ...init,
    headers: {
      ...(init?.headers || {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
  })
}

function ProviderKeysSettings() {
  const [providers, setProviders] = useState<ProviderKeyInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [busyProvider, setBusyProvider] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = async () => {
    try {
      const resp = await authFetch(PROVIDER_KEYS_ENDPOINT)
      if (resp.ok) {
        const data = (await resp.json()) as { providers: ProviderKeyInfo[] }
        setProviders(data.providers ?? [])
      } else {
        setError('Failed to load provider key status')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  const handleSave = async (provider: string) => {
    const draft = (drafts[provider] ?? '').trim()
    if (!draft) return
    setBusyProvider(provider)
    setError(null)
    try {
      const resp = await authFetch(`${PROVIDER_KEYS_ENDPOINT}${provider}/`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: draft }),
      })
      if (resp.ok) {
        setDrafts((d) => ({ ...d, [provider]: '' }))
        await refresh()
      } else {
        const body = await resp.json().catch(() => ({}))
        setError(body?.error || 'Failed to save key')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error')
    } finally {
      setBusyProvider(null)
    }
  }

  const handleRemove = async (provider: string) => {
    setBusyProvider(provider)
    setError(null)
    try {
      const resp = await authFetch(`${PROVIDER_KEYS_ENDPOINT}${provider}/`, {
        method: 'DELETE',
      })
      if (resp.ok) {
        await refresh()
      } else {
        setError('Failed to remove key')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error')
    } finally {
      setBusyProvider(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <h3 className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider">
        Provider API Keys
      </h3>

      <div className="text-xs text-muted-foreground">
        Add a key for a provider and chats with that provider's models
        (e.g. anthropic/…, openai/…) are routed <strong>directly to the
        provider</strong> and billed to your own account there — they skip
        OpenRouter entirely and don't count toward your Sterna quota.
      </div>

      <div className="rounded-lg border border-border divide-y divide-border">
        {providers.map((p) => {
          const busy = busyProvider === p.provider
          return (
            <div key={p.provider} className="p-4 space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-foreground">{p.label}</span>
                {p.configured ? (
                  <span className="flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/5 px-2 py-0.5 text-[11px] text-emerald-500">
                    <CheckCircle2 className="h-3 w-3" />
                    {p.masked_key ?? 'Configured'}
                  </span>
                ) : (
                  <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">
                    Not configured
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="password"
                  value={drafts[p.provider] ?? ''}
                  onChange={(e) =>
                    setDrafts((d) => ({ ...d, [p.provider]: e.target.value }))
                  }
                  placeholder={p.configured ? 'Replace key…' : 'API key…'}
                  className="flex-1 h-9 rounded-md border border-border bg-background px-3 text-sm font-mono placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-accent-brand/50"
                  autoComplete="off"
                  spellCheck={false}
                />
                <button
                  onClick={() => void handleSave(p.provider)}
                  disabled={busy || !(drafts[p.provider] ?? '').trim()}
                  className={cn(
                    'h-9 px-4 rounded-md text-sm font-medium transition-colors',
                    'bg-accent-brand text-white hover:bg-accent-brand/90',
                    'disabled:opacity-50 disabled:cursor-not-allowed',
                  )}
                >
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Save'}
                </button>
                {p.configured && (
                  <button
                    onClick={() => void handleRemove(p.provider)}
                    disabled={busy}
                    className="flex items-center gap-1.5 px-3 h-9 text-sm rounded-md text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Remove
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
      {error && <div className="text-xs text-destructive">{error}</div>}
    </div>
  )
}

export function BYOKSettings() {
  const [status, setStatus] = useState<ApiKeyStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [draftKey, setDraftKey] = useState('')
  const [error, setError] = useState<string | null>(null)

  const refresh = async () => {
    setLoading(true)
    try {
      const resp = await authFetch(SETTINGS_ENDPOINT)
      if (resp.ok) {
        const data = (await resp.json()) as ApiKeyStatus
        setStatus(data)
      } else {
        setError('Failed to load API key status')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  const handleSave = async () => {
    if (!draftKey.trim()) return
    setSaving(true)
    setError(null)
    try {
      const resp = await authFetch(SETTINGS_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: draftKey.trim() }),
      })
      if (resp.ok) {
        setDraftKey('')
        await refresh()
      } else {
        const body = await resp.json().catch(() => ({}))
        setError(body?.error || 'Failed to save key')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error')
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = async () => {
    setRemoving(true)
    setError(null)
    try {
      const resp = await authFetch(SETTINGS_ENDPOINT, { method: 'DELETE' })
      if (resp.ok) {
        await refresh()
      } else {
        setError('Failed to remove key')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error')
    } finally {
      setRemoving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const configured = status?.configured ?? false
  const isProvisioned = status?.is_provisioned ?? false
  const isBYOK = configured && !isProvisioned

  return (
    <div className="space-y-6">
      <ProviderKeysSettings />

      <div className="space-y-3">
        <h3 className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider">
          OpenRouter API Key
        </h3>
        <div className="text-xs text-muted-foreground">
          Fallback for all other models: anything without a provider key
          above (meta-llama/…, qwen/…, etc.) is routed through OpenRouter
          with this key.
        </div>

        {isBYOK && (
          <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-4">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0 space-y-1">
                <div className="text-sm font-medium text-foreground">BYOK key active</div>
                <div className="text-xs text-muted-foreground">
                  OpenRouter-backed features (chat, knowledge base, image gen,
                  MCP tools, coding agent) are billed directly to your OpenRouter
                  account and don't decrement your Sterna weekly quota.
                </div>
              </div>
              <button
                onClick={handleRemove}
                disabled={removing}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-50"
              >
                {removing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                Remove
              </button>
            </div>
          </div>
        )}

        {isProvisioned && (
          <div className="rounded-lg border border-blue-500/40 bg-blue-500/5 p-4">
            <div className="flex items-start gap-3">
              <Info className="h-4 w-4 text-blue-500 flex-shrink-0 mt-0.5" />
              <div className="flex-1 space-y-1">
                <div className="text-sm font-medium text-foreground">
                  Auto-provisioned key in use
                </div>
                <div className="text-xs text-muted-foreground">
                  Sterna pays OpenRouter for your usage. All calls count
                  toward your Sterna plan limits. Upload your own key below
                  to switch to BYOK billing.
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="rounded-lg border border-border p-4 space-y-3">
          <label className="text-sm font-medium text-foreground">
            {isBYOK ? 'Replace your key' : 'Bring your own key'}
          </label>
          <div className="text-xs text-muted-foreground">
            Get a key from{' '}
            <a
              href="https://openrouter.ai/keys"
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent-brand hover:underline"
            >
              openrouter.ai/keys
            </a>
            . Your key is encrypted at rest and never shown again after save.
          </div>
          <div className="flex items-center gap-2">
            <input
              type="password"
              value={draftKey}
              onChange={(e) => setDraftKey(e.target.value)}
              placeholder="sk-or-v1-..."
              className="flex-1 h-9 rounded-md border border-border bg-background px-3 text-sm font-mono placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-accent-brand/50"
              autoComplete="off"
              spellCheck={false}
            />
            <button
              onClick={handleSave}
              disabled={saving || !draftKey.trim()}
              className={cn(
                'h-9 px-4 rounded-md text-sm font-medium transition-colors',
                'bg-accent-brand text-white hover:bg-accent-brand/90',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
            >
              {saving ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Saving
                </span>
              ) : (
                'Save key'
              )}
            </button>
          </div>
          {error && <div className="text-xs text-destructive">{error}</div>}
        </div>
      </div>

      <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-4 w-4 text-amber-500 flex-shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="text-sm font-medium text-foreground">
              BYOK does not cover every feature
            </div>
            <div className="text-xs text-muted-foreground space-y-2">
              <p>
                Voice rooms (TTS / STT), video generation, web search, and maps
                <strong> always bill against your Sterna plan</strong>,
                regardless of BYOK.
              </p>
              <p>
                These providers (ElevenLabs, OpenAI TTS, Deepgram, Runway,
                Brave Search, Google Maps) are not behind OpenRouter, so your
                personal OpenRouter key cannot route them.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default BYOKSettings
