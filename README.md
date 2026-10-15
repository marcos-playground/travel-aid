# Travel Aid

Plan a vacation through a natural conversation and compare flights and hotels within a budget.

Product requirements and architecture decisions live in the wiki:

- [MVP Requirements](https://github.com/Marcos-Coca/travel-aid/wiki/MVP)
- [Architecture](https://github.com/Marcos-Coca/travel-aid/wiki/Architecture)

## Repository layout

```text
apps/web/              Next.js + TypeScript frontend
apps/api/              Python + FastAPI backend (modular monolith)
packages/api-client/   TypeScript client generated from the FastAPI OpenAPI schema
.github/workflows/     CI
```

## Prerequisites

- Node.js 24 (see `.nvmrc`) and pnpm 11 (`corepack enable`)
- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 automatically)

## Setup

```bash
pnpm install
cd apps/api && uv sync && cd ../..
cp apps/web/.env.example apps/web/.env.local
cp apps/api/.env.example apps/api/.env
```

## Development

Run the backend and frontend in separate terminals:

```bash
pnpm dev:api   # FastAPI on http://127.0.0.1:8000 (docs at /docs)
pnpm dev:web   # Next.js on http://localhost:3000
```

The web app proxies `/api/*` to the backend, so the browser always talks to one origin.
Check the connection at http://localhost:3000/api/health.

## Common tasks

```bash
pnpm lint                  # lint the web app
pnpm typecheck             # type-check TypeScript packages
pnpm build                 # production build of the web app
pnpm generate:api-client   # regenerate the TypeScript client after backend API changes
```

Backend checks run from `apps/api` (see its [README](apps/api/README.md)).
