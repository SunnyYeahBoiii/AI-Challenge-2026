# 0001: Turborepo Monorepo

We use Turborepo to manage a monorepo with two apps: `apps/web` (Next.js) and `apps/api` (Flask). This lets us run both dev servers with a single `pnpm dev` command, share root-level configs, and keep the frontend and backend in one repository.

**Considered alternatives:** Separate repos (no shared tooling), Nx (better Python support but heavier), bare pnpm workspaces (no task orchestration). Turborepo won for simplicity — it orchestrates JS tasks natively and handles Python via `package.json` wrapper scripts.

**Consequences:** Python setup requires a `package.json` bridge in `apps/api/` that shells out to `uv run`. Dev caching doesn't work well for Python (excluded from turbo cache). Both apps must be started together for full-stack dev.
