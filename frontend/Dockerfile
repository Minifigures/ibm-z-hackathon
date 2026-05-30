# Code Engine: Next.js 15 frontend container in **standalone output mode**.
# next.config.ts sets `output: 'standalone'`, so `npm run build` emits a
# self-contained server bundle at .next/standalone/server.js that includes
# only the production deps Next.js traced. The runner stage copies that
# bundle plus the static assets and runs `node server.js` directly, no
# npm and no full node_modules. Final runner image is ~80 MB (vs ~242 MB
# under the classic `npm run start` setup), which keeps us well under
# IBM Container Registry's 0.5 GB Lite-tier quota.
# Build context: frontend/

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --legacy-peer-deps

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_BASE=/api
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}
RUN npm run build
# Ensure public/ exists so the runner stage's COPY never fails, even if the
# repo doesn't ship one. Next.js falls back gracefully when it's empty.
RUN mkdir -p public

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Standalone bundle: self-contained server with traced-only deps.
COPY --from=builder /app/.next/standalone ./
# Static chunks live separately and need to be mounted under .next/static
# (the standalone server expects to find them there at runtime).
COPY --from=builder /app/.next/static ./.next/static
# public/ assets aren't part of the standalone bundle; copy them next to it.
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
