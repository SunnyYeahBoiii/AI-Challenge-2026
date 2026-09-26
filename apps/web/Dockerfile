FROM oven/bun:1-alpine AS deps
WORKDIR /app
COPY package.json bun.lock ./
COPY apps/api/package.json ./apps/api/
COPY apps/cloud-api/package.json ./apps/cloud-api/
COPY apps/web/package.json ./apps/web/
RUN bun install --frozen-lockfile --ignore-scripts

FROM oven/bun:1-alpine AS builder
ARG API_BASE_URL=http://api:5000
ARG NEXT_PUBLIC_CLOUD_API_URL=http://localhost:5002
ARG NEXT_PUBLIC_DRES_SESSION_ID
ARG NEXT_PUBLIC_DRES_USERNAME
WORKDIR /app
ENV API_BASE_URL=$API_BASE_URL
ENV NEXT_PUBLIC_CLOUD_API_URL=$NEXT_PUBLIC_CLOUD_API_URL
ENV NEXT_PUBLIC_DRES_SESSION_ID=$NEXT_PUBLIC_DRES_SESSION_ID
ENV NEXT_PUBLIC_DRES_USERNAME=$NEXT_PUBLIC_DRES_USERNAME
COPY package.json bun.lock turbo.json ./
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web/ ./apps/web/
COPY data/objects/classname.json ./data/objects/classname.json
RUN bunx turbo build --filter=@repo/web

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /app/apps/web/public ./apps/web/public

EXPOSE 3000
CMD ["node", "apps/web/server.js"]
