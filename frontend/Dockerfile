# Code Engine: Next.js 15 frontend container, multi-stage so the final image
# only carries the production build + minimal node_modules.
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

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/package.json ./
COPY --from=builder /app/next.config.ts ./next.config.ts
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["npm", "run", "start"]
