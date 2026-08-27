import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { Cpu, Star, GitCompare, MessageSquare } from 'lucide-react'
import { Command, CommandList } from '@/components/ui/command'
import { CommandPaletteItem } from '../CommandPaletteItem'
import type { ModelCommandItem, ConversationCommandItem, CommandItem as CommandItemType } from '../types'

function makeModelItem(overrides: Partial<ModelCommandItem> = {}): ModelCommandItem {
  return {
    id: 'openai/gpt-4',
    type: 'model',
    title: 'GPT-4',
    subtitle: 'OpenAI',
    icon: Cpu,
    modelId: 'openai/gpt-4',
    provider: 'OpenAI',
    isFavorite: false,
    isSelected: false,
    isCurrent: false,
    onSelect: vi.fn(),
    ...overrides,
  }
}

function makeConversationItem(overrides: Partial<ConversationCommandItem> = {}): ConversationCommandItem {
  return {
    id: 'conv-1',
    type: 'conversation',
    title: 'My conversation',
    icon: MessageSquare,
    conversationId: 'conv-1',
    updatedAt: new Date('2024-01-01'),
    onSelect: vi.fn(),
    ...overrides,
  }
}

function renderItem(item: CommandItemType, onSelect = vi.fn()) {
  return render(
    <Command>
      <CommandList>
        <CommandPaletteItem item={item} query="" onSelect={onSelect} />
      </CommandList>
    </Command>
  )
}

describe('CommandPaletteItem — models actions', () => {
  it('renders the favorite and compare actions for a model item', () => {
    const item = makeModelItem({
      actions: [
        { label: 'Add to favorites', icon: Star, onClick: vi.fn() },
        { label: 'Add to comparison', icon: GitCompare, onClick: vi.fn() },
      ],
    })

    renderItem(item)

    expect(screen.getByRole('button', { name: 'Add to favorites' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add to comparison' })).toBeInTheDocument()
  })

  it('dispatches the favorite action without selecting the item or closing the palette', () => {
    const onFavorite = vi.fn()
    const onItemSelect = vi.fn()
    const onPaletteSelect = vi.fn()
    const item = makeModelItem({
      onSelect: onItemSelect,
      actions: [{ label: 'Add to favorites', icon: Star, onClick: onFavorite }],
    })

    renderItem(item, onPaletteSelect)
    fireEvent.click(screen.getByRole('button', { name: 'Add to favorites' }))

    expect(onFavorite).toHaveBeenCalledTimes(1)
    expect(onItemSelect).not.toHaveBeenCalled()
    expect(onPaletteSelect).not.toHaveBeenCalled()
  })

  it('dispatches the compare action independently of the favorite action', () => {
    const onFavorite = vi.fn()
    const onCompare = vi.fn()
    const item = makeModelItem({
      actions: [
        { label: 'Add to favorites', icon: Star, onClick: onFavorite },
        { label: 'Add to comparison', icon: GitCompare, onClick: onCompare },
      ],
    })

    renderItem(item)
    fireEvent.click(screen.getByRole('button', { name: 'Add to comparison' }))

    expect(onCompare).toHaveBeenCalledTimes(1)
    expect(onFavorite).not.toHaveBeenCalled()
  })

  it('still dispatches model switching when the row itself is selected', () => {
    const onItemSelect = vi.fn()
    const onPaletteSelect = vi.fn()
    const item = makeModelItem({
      onSelect: onItemSelect,
      actions: [{ label: 'Add to favorites', icon: Star, onClick: vi.fn() }],
    })

    renderItem(item, onPaletteSelect)
    fireEvent.click(screen.getByText('GPT-4'))

    // cmdk's own click handling and the wrapper's mouse-click bypass can each
    // fire selection, so assert dispatch happened rather than an exact count.
    expect(onItemSelect).toHaveBeenCalled()
    expect(onPaletteSelect).toHaveBeenCalled()
  })

  it('renders no actions row for item types that never declare actions', () => {
    renderItem(makeConversationItem())

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders no actions row for a model item with no actions set', () => {
    const item = makeModelItem({ actions: undefined })
    renderItem(item)

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('skips an action whose icon degraded to {} after persistence round-tripping', () => {
    // A lucide icon is a forwardRef object whose own properties ($$typeof: a
    // symbol, render: a function) are both value types JSON.stringify drops,
    // so it rehydrates as an empty object — even when onClick is still callable.
    const degradedIcon = JSON.parse(JSON.stringify(Star))
    const item = makeModelItem({
      actions: [{ label: 'Add to favorites', icon: degradedIcon, onClick: vi.fn() }],
    })

    expect(() => renderItem(item)).not.toThrow()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('skips an action whose onClick did not survive persistence round-tripping', () => {
    // JSON.stringify drops function-valued properties entirely (the key
    // disappears on parse), even when the icon component survives.
    const rehydrated = JSON.parse(JSON.stringify({ label: 'Add to favorites', onClick: vi.fn() }))
    const item = makeModelItem({
      actions: [{ ...rehydrated, icon: Star }],
    })

    expect(() => renderItem(item)).not.toThrow()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('skips an action after a full persistence round-trip (both icon and onClick degrade)', () => {
    const rehydratedAction = JSON.parse(
      JSON.stringify({ label: 'Add to favorites', icon: Star, onClick: vi.fn() })
    )
    const item = makeModelItem({ actions: [rehydratedAction] })

    expect(() => renderItem(item)).not.toThrow()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
