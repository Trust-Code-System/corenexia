# Corenexia "God View" frontend — Next.js (standalone output), multi-stage for a slim runtime.
#
# NEXT_PUBLIC_* values are inlined at build time, so the API base must be passed as a build arg.
# It defaults to the browser-facing host port published by docker-compose (localhost:8000).

# --- deps + build ---------------------------------------------------------
FROM node:22-alpine AS builder
WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
RUN npm run build

# --- runtime --------------------------------------------------------------
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000

# Run as the built-in non-root user.
USER node

# Standalone output bundles only what the server needs (no full node_modules).
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
