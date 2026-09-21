# FrameSeeker — AI Challenge 2026

AI-powered video and image search application. Users input text or image queries, the system finds relevant video moments using vector similarity search, and results can be submitted to the competition platform (DRES).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4 |
| Backend | Python 3.11, Flask, OpenCLIP (DFN5B-CLIP-ViT-H-14-384) |
| Vector DB | Milvus Cloud (183K+ embeddings) |
| Search DB | Elasticsearch Cloud (367K+ documents) |
| Monorepo | Turborepo, pnpm |
| Container | Docker Compose |

## Prerequisites

- **Node.js** 22+
- **pnpm** 9+
- **Python** 3.11+
- **uv** (Python package manager) — `pip install uv`
- **Docker** & Docker Compose (for containerized setup)

## Quick Start

### Option 1: Docker Compose (recommended)

```bash
git clone <repo-url>
cd AI-Challenge-2026

# Copy environment files and fill in your credentials
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env

# Build and run everything
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:5001
- TRAKE collab: http://localhost:5002

> **Teammates**: set `NEXT_PUBLIC_TRAKE_COLAB_URL` in `apps/web/.env` to the IP of the machine running `trake-colab`, then rebuild. See [Configuring TRAKE Collab URL](#configuring-trake-collab-url).

### Option 2: Local Development (Turborepo)

```bash
git clone <repo-url>
cd AI-Challenge-2026

# Install root dependencies
pnpm install

# Set up Python backend
cd apps/api
cp .env.example .env        # Fill in your credentials
uv sync                      # Create venv and install deps
cd ../..

# Set up frontend
cp apps/web/.env.example apps/web/.env
# Edit apps/web/.env if you need to change NEXT_PUBLIC_TRAKE_COLAB_URL

# Start everything
pnpm dev
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:5001
- TRAKE collab: http://localhost:5002

> **Teammates**: set `NEXT_PUBLIC_TRAKE_COLAB_URL` in `apps/web/.env` to the IP of the machine running `trake-colab`. See [Configuring TRAKE Collab URL](#configuring-trake-collab-url).

### Option 3: Individual Services

```bash
# Frontend only
cd apps/web
cp .env.example .env        # Set NEXT_PUBLIC_TRAKE_COLAB_URL if needed
pnpm install
pnpm dev

# Backend only (requires Python 3.11+ and uv)
cd apps/api
uv sync
uv run flask --app app.main run --port 5000 --debug
```

## Docker Images (Pre-built)

Pre-built images are published to GitHub Container Registry on every push to `main` and on version tags.

### Available Images

| Image | Description |
|-------|-------------|
| `ghcr.io/sunnyyeahboiii/ai-challenge-2026/api` | Python/Flask backend |
| `ghcr.io/sunnyyeahboiii/ai-challenge-2026/web` | Next.js frontend |

### Tags

- `latest` — latest build from `main`
- `main` — latest build from `main` branch
- `v1.0.0` — release tag (semver)
- `<sha>` — commit SHA (e.g. `a1b2c3d`)

### Running with Pre-built Images

Create a `docker-compose.prod.yml`:

```yaml
services:
  web:
    image: ghcr.io/sunnyyeahboiii/ai-challenge-2026/web:latest
    ports:
      - "3000:3000"
    depends_on:
      - api
    environment:
      - API_BASE_URL=http://api:5000
      - NEXT_PUBLIC_TRAKE_COLAB_URL=http://trake-colab:5002

  api:
    image: ghcr.io/sunnyyeahboiii/ai-challenge-2026/api:latest
    ports:
      - "5000:5000"
    env_file:
      - ./apps/api/.env
    depends_on:
      milvus:
        condition: service_healthy
      elasticsearch:
        condition: service_healthy

  milvus:
    image: milvusdb/milvus:v2.4.17
    command: ["milvus", "run", "standalone"]
    ports:
      - "19530:19530"
      - "9091:9091"
    volumes:
      - milvus_data:/var/lib/milvus
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    environment:
      - ETCD_USE_EMBED=true
      - COMMON_STORAGETYPE=local

  elasticsearch:
    image: elasticsearch:8.12.0
    ports:
      - "9200:9200"
    volumes:
      - es_data:/usr/share/elasticsearch/data
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:9200/_cluster/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - xpack.security.http.ssl.enabled=false
      - ES_JAVA_OPTS=-Xms512m -Xmx512m

volumes:
  milvus_data:
  es_data:
```

Then run:

```bash
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env
# Fill in credentials and set NEXT_PUBLIC_TRAKE_COLAB_URL if needed
docker compose -f docker-compose.prod.yml up -d
```

> **Note**: Pre-built web images have `NEXT_PUBLIC_TRAKE_COLAB_URL` baked in. To override, rebuild locally:
> ```bash
> docker compose -f docker-compose.prod.yml build --build-arg NEXT_PUBLIC_TRAKE_COLAB_URL=http://your-host:5002 web
> ```

## Environment Variables

Copy `apps/api/.env.example` to `apps/api/.env` and fill in:

| Variable | Description | Source |
|----------|-------------|--------|
| `MILVUS_URI` | Milvus Cloud connection URI | Zilliz Cloud dashboard |
| `MILVUS_TOKEN` | Milvus Cloud authentication token | Zilliz Cloud dashboard |
| `ES_URL` | Elasticsearch Cloud endpoint | Elastic Cloud dashboard |
| `ES_USER` | Elasticsearch username | Elastic Cloud dashboard |
| `ES_PASS` | Elasticsearch password | Elastic Cloud dashboard |
| `OPENAI_API_KEY` | OpenAI API key (for query enhancement) | OpenAI dashboard |
| `SECRET_KEY` | Flask secret key | Generate any random string |

### Optional REPEAT graph

The REPEAT badge uses a precomputed SigLIP2 graph and does not require the
active retrieval model to be SigLIP2. It is intentionally distributed outside
Git. Copy both matching artifacts beside the shared metadata before starting
the API:

```text
data/repeat_graphs/siglip2-repeat-graph.npz
data/repeat_graphs/siglip2-repeat-graph.manifest.json
```

The API validates the manifest and metadata checksum. If either file is absent
or belongs to different metadata, REPEAT is disabled while normal search stays
available.

**Web Container**:

| Variable | Description | Default | Notes |
|----------|-------------|---------|-------|
| `API_BASE_URL` | Backend API URL | `http://api:5000` | Server-side only |
| `NEXT_PUBLIC_TRAKE_COLAB_URL` | TRAKE collab server URL | `http://localhost:5002` | Client-side, baked at build time |

## Configuring TRAKE Collab URL

One machine in the team runs `trake-colab` (NestJS + SQLite). Other teammates must point their frontend to that machine.

### Who runs trake-colab?

The machine running `trake-colab` uses the default `http://localhost:5002` — no changes needed.

### For teammates (connecting to remote trake-colab)

Set `NEXT_PUBLIC_TRAKE_COLAB_URL` to the host machine's IP:

**Local development** (apps/web/.env):

```bash
# apps/web/.env
NEXT_PUBLIC_TRAKE_COLAB_URL=http://192.168.1.100:5002
```

Then restart the dev server (`pnpm dev` or `docker compose up`).

**Docker** (requires rebuild since `NEXT_PUBLIC_*` is baked at build time):

Edit `docker-compose.yml`:

```yaml
web:
  build:
    args:
      NEXT_PUBLIC_TRAKE_COLAB_URL: http://192.168.1.100:5002
  environment:
    - NEXT_PUBLIC_TRAKE_COLAB_URL=http://192.168.1.100:5002
```

Then rebuild:

```bash
docker compose up --build web
```

Or pass as build arg:

```bash
docker compose build --build-arg NEXT_PUBLIC_TRAKE_COLAB_URL=http://192.168.1.100:5002 web
docker compose up -d
```

> **Note**: `NEXT_PUBLIC_*` variables are embedded into the JavaScript bundle at build time. Changing them requires a rebuild in Docker, but only a dev server restart in local development.

## Project Structure

```
AI-Challenge-2026/
├── apps/
│   ├── web/            # Next.js 16 frontend (port 3000)
│   ├── api/            # Flask backend (port 5000)
│   └── trake-colab/    # TRAKE collaboration server (port 5002)
├── docs/               # Project documentation
├── docker-compose.yml
├── turbo.json
└── pnpm-workspace.yaml
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/search` | Text-based vector search |
| `POST` | `/api/search/image` | Image-based vector search |
| `POST` | `/api/frames` | Multi-query search with BoxQuery |
| `GET` | `/api/videos` | List video metadata |
| `POST` | `/api/embed/text` | Generate text embeddings |
| `POST` | `/api/embed/image` | Generate image embeddings |
| `POST` | `/api/dres/submit/kis` | Submit KIS answer to DRES |

## Reproducing on Another Machine

1. Clone the repo
2. Install prerequisites: Node.js 22+, pnpm 9+, Python 3.11+, uv, Docker
3. Copy env files:
   - `cp apps/api/.env.example apps/api/.env` — fill in credentials
   - `cp apps/web/.env.example apps/web/.env` — set `NEXT_PUBLIC_TRAKE_COLAB_URL` if connecting to remote trake-colab
4. Run `docker compose up --build` (Docker) or `pnpm dev` (local)
5. Verify: open http://localhost:3000, check http://localhost:5001/api/health

## Acknowledgments

- [OpenCLIP](https://github.com/mlfoundations/open_clip) — Text and image embeddings
- [Milvus](https://milvus.io/) — Vector similarity search
- [Elasticsearch](https://www.elastic.co/) — Full-text search
- [Next.js](https://nextjs.org/) — React framework
- [Flask](https://flask.palletsprojects.com/) — Python web framework
