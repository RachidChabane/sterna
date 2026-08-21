# Sterna - Frontend

React SPA for Sterna, the multi-model AI chat platform.

## Tech Stack

- **Framework**: React 19 with TypeScript
- **Build Tool**: Vite
- **Routing**: TanStack Router (file-based)
- **State Management**: Zustand
- **Styling**: Tailwind CSS + shadcn/ui components
- **API Client**: Axios with interceptors
- **Tests**: Vitest (unit) + Playwright (e2e)

## Getting Started

### Prerequisites

- Node.js 20+
- pnpm
- Backend server running on port 8000 (see `core/README.md`)

### Installation

```bash
pnpm install
```

### Development

```bash
# Start development server on port 5173
pnpm dev
```

The app will be available at http://localhost:5173 (in the Docker dev stack, the `frontend` service runs this for you).

### Build

```bash
# Typecheck + build for production
pnpm build

# Preview production build
pnpm preview
```

## Project Structure

```
src/
├── api/                # Axios client + per-domain API modules
├── components/         # UI components (chat, models, sparks, sandbox, consent, …)
│   └── ui/             # shadcn/ui primitives
├── content/legal/      # Legal pages (MDX)
├── hooks/              # Custom React hooks
├── lib/                # Utilities and helpers
├── routes/             # TanStack Router routes (chats, models, sparks, knowledge, voice-rooms, settings, legal, …)
├── store/              # Zustand stores (authStore, modelStore, conversationStore, consentStore, …)
└── utils/              # Shared utilities
```

## Key Features

### Authentication
- JWT-based authentication with access/refresh tokens
- Automatic token refresh on 401 responses
- GitHub / Google OAuth and Turnstile CAPTCHA on signup

### API Integration
- Centralized API client with request/response interceptors
- Comprehensive error handling
- Type-safe API calls with TypeScript

### Routing
- File-based routing with TanStack Router
- Protected routes for authenticated users
- Route-level code splitting

## Environment Variables

Create a `.env` file in the frontend directory:

```env
VITE_API_URL=http://localhost:8000
```

## Scripts

- `pnpm dev` - Start development server
- `pnpm build` - Typecheck + build for production
- `pnpm preview` - Preview production build
- `pnpm lint` - Run ESLint
- `pnpm typecheck` - Run TypeScript compiler check
- `pnpm test` - Run Vitest unit tests
- `pnpm test:e2e` - Run Playwright e2e tests (CI runs the `@smoke` subset)

## Integration with Backend

The frontend proxies API requests to the Django backend on port 8000. The proxy configuration is in `vite.config.ts`.

## Design System

See `THEME_GUIDE.md` in this directory for the color palette, theme architecture, and utility classes.

## License

Part of Sterna project
