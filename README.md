# FrameSeeker — AI Challenge 2026

AI-powered video and image search application. Users input text or image queries, the system finds relevant video moments using vector similarity search, and results can be submitted to the competition platform (DRES).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4 |
| Backend | Python 3.11, Flask, BEiT-3/MetaCLIP2/Perception/BGE-VL, RRF ensemble |
| Vector DB | One Milvus collection per embedding model |
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

# Copy environment file and fill in your credentials
cp apps/api/.env.example apps/api/.env

# Build and run everything
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:5000

### Option 2: Local Development (Turborepo)

```bash
git clone <repo-url>
cd AI-Challenge-2026

# Install root dependencies
pnpm install

# Set up Python backend
cd apps/api
cp .env.example .env        # Fill in your credentials
uv sync --extra models --extra dev  # API, model adapters and verification tools
cd ../..

# Start everything
pnpm dev
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:5000

### Option 3: Individual Services

```bash
# Frontend only
cd apps/web
pnpm install
pnpm dev

# Backend only (requires Python 3.11+ and uv)
cd apps/api
uv sync
uv run flask --app app.main run --port 5000 --debug
```

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
| `ENSEMBLE_CONFIG_PATH` | Versioned model/collection configuration | Repository config |
| `KEYFRAMES_DIR` | Canonical keyframe root (`/data/keyframes/keyframes` in Docker) | Local dataset |
| `GUNICORN_WORKERS` | API worker count; keep at 1 unless GPU memory permits more | Runtime sizing |
| `DRES_BASE_URL` | Organizer-provided DRES server URL | Competition organizer |
| `DRES_EVALUATION_ID` | Active DRES evaluation ID | Competition organizer |
| `DRES_SESSION_TOKEN` | Optional pre-issued DRES session token | DRES profile |
| `SECRET_KEY` | Flask secret key | Generate any random string |

## Project Structure

```
AI-Challenge-2026/
├── apps/
│   ├── web/          # Next.js 16 frontend (port 3000)
│   └── api/          # Flask backend (port 5000)
├── docs/             # Project documentation
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
| `POST` | `/api/search/composed` | Text + selected-image feedback search |
| `POST` | `/api/frames` | Multi-query search with BoxQuery |
| `GET` | `/api/models` | List enabled ensemble models |
| `GET` | `/api/videos` | List video metadata |
| `POST` | `/api/embed/text` | Generate text embeddings |
| `POST` | `/api/embed/image` | Generate image embeddings |
| `POST` | `/api/dres/login` | Authenticate to DRES v2 |
| `POST` | `/api/dres/submit/{kis,qa,track}` | Submit an answer to DRES v2 |

## Reproducing on Another Machine

1. Clone the repo
2. Install prerequisites: Node.js 22+, pnpm 9+, Python 3.11+, uv, Docker
3. Copy `apps/api/.env.example` → `apps/api/.env` and fill in credentials
4. Run `docker compose up --build` (Docker) or `pnpm dev` (local)
5. Verify: open http://localhost:3000, check http://localhost:5000/api/health

## Inference and Ensemble

See [docs/inference-ensemble.md](docs/inference-ensemble.md) for canonical Frame manifests,
multi-model image inference, checksummed artifacts, per-model Milvus loading, RRF/WRRF,
composed image feedback and reproducible Recall@K/MRR/mAP ablations.

## Acknowledgments

- [BEiT-3](https://github.com/microsoft/unilm/tree/master/beit3) — Image-text retrieval
- [BGE-VL](https://huggingface.co/BAAI/BGE-VL-large) — Joint image-text retrieval
- [Perception Encoder](https://github.com/facebookresearch/perception_models) — Image-text retrieval
- [OpenCLIP](https://github.com/mlfoundations/open_clip) — Text and image embeddings
- [Milvus](https://milvus.io/) — Vector similarity search
- [Elasticsearch](https://www.elastic.co/) — Full-text search
- [Next.js](https://nextjs.org/) — React framework
- [Flask](https://flask.palletsprojects.com/) — Python web framework
