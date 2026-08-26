import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Loader2, Globe, Sparkles } from 'lucide-react'
import { LanguageFlag } from './LanguageFlag'
import type { TTSModelInfo } from '@/types/voiceRoom'

interface DesktopBasicsStepProps {
  isEditMode: boolean
  aiDescription: string
  setAiDescription: (v: string) => void
  isGeneratingRoom: boolean
  handleAIGenerate: () => void
  name: string
  setName: (v: string) => void
  userName: string
  setUserName: (v: string) => void
  description: string
  setDescription: (v: string) => void
  language: string
  setLanguage: (v: string) => void
  availableLanguages: TTSModelInfo['languages']
}

/** Step 1 (Basics) content for the desktop dialog. */
export function DesktopBasicsStep({
  isEditMode,
  aiDescription,
  setAiDescription,
  isGeneratingRoom,
  handleAIGenerate,
  name,
  setName,
  userName,
  setUserName,
  description,
  setDescription,
  language,
  setLanguage,
  availableLanguages,
}: DesktopBasicsStepProps) {
  return (
    <div className="h-full flex flex-col gap-5">
      {/* AI Generate - only in create mode */}
      {!isEditMode && (
        <div className="shrink-0 rounded-xl border border-accent-brand/40 bg-gradient-to-br from-accent-brand/10 via-accent-brand/5 to-transparent p-4 space-y-3">
          <div>
            <p className="text-sm font-medium text-foreground">Generate with AI</p>
            <p className="text-xs text-muted-foreground">Describe your room and we'll configure it for you</p>
          </div>
          <textarea
            value={aiDescription}
            onChange={(e) => setAiDescription(e.target.value)}
            placeholder="A podcast with a host and two guests discussing technology trends..."
            rows={2}
            disabled={isGeneratingRoom}
            className="w-full rounded-lg border border-accent-brand/20 bg-background/50 shadow-none focus:outline-none focus:border-accent-brand/50 focus:ring-1 focus:ring-accent-brand/20 text-sm text-foreground placeholder:text-muted-foreground/50 resize-none p-3"
          />
          {aiDescription.trim() && (
            <Button
              type="button"
              size="sm"
              onClick={handleAIGenerate}
              disabled={isGeneratingRoom}
              className="btn-premium h-8"
            >
              {isGeneratingRoom ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Sparkles className="h-3.5 w-3.5 mr-1.5" />
                  Generate Room
                </>
              )}
            </Button>
          )}
        </div>
      )}

      {/* Basic Fields - 2 column grid on desktop */}
      <div className="grid grid-cols-2 gap-4 shrink-0">
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Room Name *</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="My Debate Room"
            className="h-9"
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Your Name</Label>
          <Input
            value={userName}
            onChange={(e) => setUserName(e.target.value)}
            placeholder="How agents address you"
            className="h-9"
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Language</Label>
          <Select value={language} onValueChange={setLanguage}>
            <SelectTrigger className="h-9">
              <SelectValue>
                <div className="flex items-center gap-2">
                  {language === 'auto' ? (
                    <>
                      <Globe className="h-3.5 w-3.5 text-muted-foreground" />
                      <span>Auto-detect</span>
                    </>
                  ) : (
                    <>
                      <LanguageFlag countryCode={availableLanguages.find(l => l.language_id === language)?.country_code || ''} size={14} />
                      <span>{availableLanguages.find(l => l.language_id === language)?.name || language}</span>
                    </>
                  )}
                </div>
              </SelectValue>
            </SelectTrigger>
            <SelectContent className="max-h-[300px]">
              <SelectItem value="auto">
                <div className="flex items-center gap-2">
                  <Globe className="h-3.5 w-3.5 text-muted-foreground" />
                  <span>Auto-detect</span>
                </div>
              </SelectItem>
              {availableLanguages.map((lang) => (
                <SelectItem key={lang.language_id} value={lang.language_id}>
                  <div className="flex items-center gap-2">
                    <LanguageFlag countryCode={lang.country_code} size={14} />
                    <span>{lang.name}</span>
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Description - fills remaining space */}
      <div className="flex-1 flex flex-col space-y-1.5 min-h-0">
        <Label className="text-xs text-muted-foreground shrink-0">Description</Label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What's this room about?"
          className="flex-1 w-full rounded-lg border border-border bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 resize-none p-3 focus:outline-none focus:ring-1 focus:ring-border"
        />
      </div>
    </div>
  )
}
