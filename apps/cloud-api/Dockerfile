FROM oven/bun:1-alpine AS deps
WORKDIR /app
COPY package.json bun.lock ./
COPY apps/api/package.json ./apps/api/
COPY apps/cloud-api/package.json ./apps/cloud-api/
COPY apps/web/package.json ./apps/web/
COPY apps/cloud-api/prisma ./apps/cloud-api/prisma
RUN bun install --frozen-lockfile --ignore-scripts

FROM oven/bun:1-alpine AS builder
WORKDIR /app
COPY package.json turbo.json ./
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/cloud-api/node_modules ./apps/cloud-api/node_modules
COPY apps/cloud-api/ ./apps/cloud-api/
RUN bunx turbo build --filter=@repo/cloud-api

FROM node:22-alpine AS runner
WORKDIR /app/apps/cloud-api
ENV NODE_ENV=production
COPY --from=builder /app/node_modules /app/node_modules
COPY --from=builder /app/apps/cloud-api/node_modules ./node_modules
COPY --from=builder /app/apps/cloud-api/dist ./dist
COPY --from=builder /app/apps/cloud-api/prisma ./prisma
COPY --from=builder /app/apps/cloud-api/package.json ./package.json

EXPOSE 5002
CMD ["sh", "-c", "npx prisma db push --skip-generate && node dist/main.js"]
