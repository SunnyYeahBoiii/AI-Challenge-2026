FROM node:22-alpine AS deps

WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN corepack enable \
    && corepack prepare pnpm@9.15.0 --activate \
    && pnpm install --frozen-lockfile --filter @repo/web...

FROM node:22-alpine AS builder

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY . .
ARG API_BASE_URL=http://api:5000
ENV API_BASE_URL=${API_BASE_URL}
RUN corepack enable \
    && corepack prepare pnpm@9.15.0 --activate \
    && cd apps/web \
    && pnpm build

FROM node:22-alpine AS runner

WORKDIR /app/apps/web
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
COPY --from=builder /app/apps/web/.next/standalone /app/
COPY --from=builder /app/apps/web/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
