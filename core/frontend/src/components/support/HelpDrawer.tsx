import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Search, Send, Loader2, ExternalLink } from 'lucide-react'
import { toast } from 'sonner'
import { useRouterState } from '@tanstack/react-router'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from '@/components/ui/sheet'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useHelpDrawerStore } from '@/store/helpDrawerStore'
import { useAuthStore } from '@/store/authStore'
import { faqArticles, faqCategories } from '@/content/faq'
import { supportApi } from '@/api/support'
import { SITE_CONFIG } from '@/config/site'

function FaqArticleView({ slug, onBack }: { slug: string; onBack: () => void }) {
  const article = faqArticles.find((a) => a.slug === slug)
  if (!article) return null
  return (
    <div>
      <button
        onClick={onBack}
        className="text-sm text-muted-foreground hover:text-foreground mb-3 flex items-center gap-1"
      >
        ← Back
      </button>
      <h3 className="font-semibold mb-3">{article.title}</h3>
      <div className="prose prose-sm dark:prose-invert max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{article.body}</ReactMarkdown>
      </div>
    </div>
  )
}

function FaqTab() {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<string | null>(null)

  const filtered = faqArticles.filter(
    (a) =>
      !query ||
      a.title.toLowerCase().includes(query.toLowerCase()) ||
      a.body.toLowerCase().includes(query.toLowerCase()),
  )

  const grouped = faqCategories.reduce<Record<string, typeof faqArticles>>(
    (acc, cat) => {
      const items = filtered.filter((a) => a.category === cat)
      if (items.length) acc[cat] = items
      return acc
    },
    {},
  )

  return (
    <div className="flex flex-col gap-3 h-full">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search FAQ…"
          className="pl-9"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setSelected(null)
          }}
        />
      </div>
      <ScrollArea className="flex-1">
        {selected ? (
          <FaqArticleView slug={selected} onBack={() => setSelected(null)} />
        ) : (
          Object.entries(grouped).map(([cat, items]) => (
            <div key={cat} className="mb-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1 px-1">
                {cat}
              </p>
              {items.map((article) => (
                <button
                  key={article.slug}
                  className="w-full text-left px-2 py-2 rounded-lg hover:bg-secondary transition-colors text-sm"
                  onClick={() => setSelected(article.slug)}
                >
                  {article.title}
                </button>
              ))}
            </div>
          ))
        )}
        {filtered.length === 0 && (
          <p className="text-sm text-muted-foreground text-center mt-8">
            No articles match your search.
          </p>
        )}
      </ScrollArea>
    </div>
  )
}

function ContactTab() {
  const { user, isAuthenticated } = useAuthStore()
  const routerState = useRouterState()
  const currentRoute = routerState.location.pathname

  const [email, setEmail] = useState(isAuthenticated ? (user?.email ?? '') : '')
  const [subject, setSubject] = useState('')
  const [message, setMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    try {
      await supportApi.createRequest({
        email,
        subject,
        message,
        context: {
          route: currentRoute,
          browser: navigator.userAgent.split(' ').slice(-2).join(' '),
          userAgent: navigator.userAgent,
          plan: 'unknown',
        },
      })
      setSubmitted(true)
      toast.success("Message sent — we'll get back to you soon.")
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      toast.error(detail ?? 'Failed to send your message. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  if (submitted) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
        <div className="h-12 w-12 rounded-full bg-brand-500/10 flex items-center justify-center">
          <Send className="h-6 w-6 text-brand-500" />
        </div>
        <p className="font-semibold">Message received!</p>
        <p className="text-sm text-muted-foreground">
          Check your inbox for a confirmation. We typically reply within 1–2 business days.
        </p>
        <Button variant="outline" size="sm" onClick={() => setSubmitted(false)}>
          Send another message
        </Button>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {!isAuthenticated && (
        <div className="space-y-1">
          <Label htmlFor="support-email">Your email</Label>
          <Input
            id="support-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </div>
      )}
      <div className="space-y-1">
        <Label htmlFor="support-subject">Subject</Label>
        <Input
          id="support-subject"
          required
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="What's the issue?"
          maxLength={255}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="support-message">Message</Label>
        <Textarea
          id="support-message"
          required
          rows={6}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Describe what happened…"
          minLength={10}
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Your current page, browser info, and plan will be attached automatically.
      </p>
      <Button type="submit" disabled={isLoading} className="w-full">
        {isLoading ? (
          <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Sending…</>
        ) : (
          <><Send className="mr-2 h-4 w-4" /> Send message</>
        )}
      </Button>
    </form>
  )
}

function StatusTab() {
  return (
    <div className="flex flex-col h-full gap-2">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">Powered by Better Uptime</p>
        <a
          href={SITE_CONFIG.statusPageUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-brand-500 flex items-center gap-1 hover:underline"
        >
          Open <ExternalLink className="h-3 w-3" />
        </a>
      </div>
      <iframe
        src={SITE_CONFIG.statusPageUrl}
        className="flex-1 w-full rounded-lg border"
        title="Sterna Status Page"
        sandbox="allow-scripts allow-same-origin"
      />
    </div>
  )
}

export function HelpDrawer() {
  const { isOpen, activeTab, close, setTab } = useHelpDrawerStore()

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && close()}>
      <SheetContent side="right" className="w-[400px] sm:w-[400px] flex flex-col p-0">
        <SheetHeader className="px-6 pt-6 pb-4 border-b">
          <SheetTitle>Help & Support</SheetTitle>
        </SheetHeader>

        <Tabs
          value={activeTab}
          onValueChange={(v) => setTab(v as 'faq' | 'contact' | 'status')}
          className="flex-1 flex flex-col overflow-hidden"
        >
          <TabsList className="mx-6 mt-3 grid w-auto grid-cols-3">
            <TabsTrigger value="faq">FAQ</TabsTrigger>
            <TabsTrigger value="contact">Contact us</TabsTrigger>
            <TabsTrigger value="status">Status</TabsTrigger>
          </TabsList>

          <TabsContent value="faq" className="flex-1 overflow-hidden px-6 pb-6 mt-4">
            <FaqTab />
          </TabsContent>
          <TabsContent value="contact" className="flex-1 overflow-auto px-6 pb-6 mt-4">
            <ContactTab />
          </TabsContent>
          <TabsContent value="status" className="flex-1 flex flex-col px-6 pb-6 mt-4">
            <StatusTab />
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  )
}
