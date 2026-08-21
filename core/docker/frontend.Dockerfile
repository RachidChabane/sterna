# The project is pnpm-managed (pnpm-lock.yaml is the only lockfile).
# corepack pins the pnpm major so image builds match local installs.

# Development stage
FROM node:20-alpine AS development

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@10 --activate

# Copy package files
COPY frontend/package.json frontend/pnpm-lock.yaml ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy application files
COPY frontend/ ./

# Expose port
EXPOSE 5173

# Start development server with host binding
CMD ["pnpm", "dev", "--host", "0.0.0.0"]

# Builder stage for production
FROM node:20-alpine AS builder

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@10 --activate

# Copy package files
COPY frontend/package.json frontend/pnpm-lock.yaml ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy application files
COPY frontend/ ./

# Build the application (tsc -b && vite build — typecheck is enforced).
# tsc + rollup on this codebase exceed node's default heap on 7 GB CI
# runners; raise it explicitly.
ENV NODE_OPTIONS=--max-old-space-size=4096
RUN pnpm build

# Production stage with nginx
FROM nginx:alpine AS production

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
