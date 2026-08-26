import '@testing-library/jest-dom'
import { beforeEach, vi } from 'vitest'

// ---------------------------------------------------------------------------
// localStorage / sessionStorage
//
// Node >= 22 ships an experimental global `localStorage` that is non-functional
// unless the process is started with a valid `--localstorage-file`. Under
// vitest it shadows jsdom's implementation, so `localStorage.getItem` blows up
// at module scope (e.g. src/api/client.ts) and zustand's persist middleware
// fails with "storage.setItem is not a function". Provide a complete
// in-memory Storage implementation on both globalThis and window.
// ---------------------------------------------------------------------------
class MemoryStorage implements Storage {
  private store = new Map<string, string>()

  get length(): number {
    return this.store.size
  }

  clear(): void {
    this.store.clear()
  }

  getItem(key: string): string | null {
    return this.store.has(String(key)) ? this.store.get(String(key))! : null
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null
  }

  removeItem(key: string): void {
    this.store.delete(String(key))
  }

  setItem(key: string, value: string): void {
    this.store.set(String(key), String(value))
  }
}

const localStorageMock = new MemoryStorage()
const sessionStorageMock = new MemoryStorage()

const globalScopes: object[] = [globalThis, window]
for (const target of globalScopes) {
  Object.defineProperty(target, 'localStorage', {
    value: localStorageMock,
    writable: true,
    configurable: true,
  })
  Object.defineProperty(target, 'sessionStorage', {
    value: sessionStorageMock,
    writable: true,
    configurable: true,
  })
}

// Keep tests isolated from one another
beforeEach(() => {
  localStorageMock.clear()
  sessionStorageMock.clear()
})

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// Mock IntersectionObserver
class MockIntersectionObserver implements IntersectionObserver {
  readonly root: Element | Document | null = null;
  readonly rootMargin: string = '0px';
  readonly scrollMargin: string = '0px';
  readonly thresholds: ReadonlyArray<number> = [0];

  constructor() {}
  disconnect() {}
  observe() {}
  unobserve() {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}

global.IntersectionObserver = MockIntersectionObserver

// Mock ResizeObserver (Radix UI primitives use this)
class MockResizeObserver implements ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
global.ResizeObserver = MockResizeObserver