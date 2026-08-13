FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json ./
COPY apps/trake-colab/package.json ./apps/trake-colab/
COPY apps/trake-colab/prisma ./apps/trake-colab/prisma
RUN corepack enable && pnpm install --frozen-lockfile

FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json ./
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/trake-colab/node_modules ./apps/trake-colab/node_modules
COPY apps/trake-colab/ ./apps/trake-colab/
RUN corepack enable && pnpm --filter @repo/trake-colab build

FROM node:22-alpine AS runner
WORKDIR /app/apps/trake-colab
ENV NODE_ENV=production
COPY --from=builder /app/node_modules /app/node_modules
COPY --from=builder /app/apps/trake-colab/node_modules ./node_modules
COPY --from=builder /app/apps/trake-colab/dist ./dist
COPY --from=builder /app/apps/trake-colab/prisma ./prisma
COPY --from=builder /app/apps/trake-colab/package.json ./package.json

EXPOSE 5002
CMD ["sh", "-c", "npx prisma db push --skip-generate && node dist/main.js"]
