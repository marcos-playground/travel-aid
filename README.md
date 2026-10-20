# Travel Aid

Plan a vacation through a natural conversation and compare flights and hotels within a budget.

Product requirements and architecture decisions live in the wiki:

- [MVP Requirements](https://github.com/marcos-playground/travel-aid/wiki/MVP)
- [Architecture](https://github.com/marcos-playground/travel-aid/wiki/Architecture)

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

## Deployment (Vercel)

The repository deploys as **one Vercel project** using [Vercel Services](https://vercel.com/docs/services)
(beta), configured in the root [`vercel.json`](vercel.json):

| Service | Root        | Serves   | Built as                                                      |
| ------- | ----------- | -------- | ------------------------------------------------------------- |
| `web`   | `apps/web/` | `/*`     | Next.js, installed from the pnpm workspace root               |
| `api`   | `apps/api/` | `/api/*` | One Python function from `asgi:app`, dependencies from `uv.lock` |

Production keeps the same single origin as local development. Vercel routes `/api/*` to FastAPI
before Next.js sees the request, so the browser never calls the backend cross-origin and no CORS
setup is needed. The Next.js `/api` rewrite (driven by `API_URL`) only applies locally and is
skipped on Vercel. Both services deploy, preview and roll back together, so every preview pairs a
frontend with its matching backend.

[`apps/api/asgi.py`](apps/api/asgi.py) is the Vercel entrypoint. It re-exports
`travel_aid.main:app` because Vercel resolves entrypoints relative to `apps/api`, not `src/`.
FastAPI's `/docs` and `/openapi.json` are not under `/api`, so they are not public in deployments.

### Project settings

Configure these once in the Vercel dashboard:

- **Team:** the personal `marcoscocas-projects` team.
- **Root Directory:** the repository root (leave empty).
- **Framework Preset:** Services. Vercel only builds `services` when this preset is selected.
- **Node.js version:** 24.x.
- **Build, Install and Output commands:** leave empty, because each service builds itself.

pnpm needs no override. The lockfile installs with Vercel's pnpm, and pnpm 10 switches to the
version pinned in `packageManager` on its own.

### Environment variables

In Services mode, project environment variables are shared by both services. Server-side
secrets are visible to the Next.js server runtime too, but only variables prefixed
`NEXT_PUBLIC_` reach the browser.

| Variable      | Used by | Value on Vercel                                                     |
| ------------- | ------- | ------------------------------------------------------------------- |
| `ENVIRONMENT` | api     | `production` for Production, `preview` for Preview                  |
| `API_URL`     | web     | Leave unset. It is only for the local proxy to `uv run fastapi dev` |

Provider and service credentials (SerpApi, database, authentication, model provider) are added
here as they are integrated.

### Limits checked against the Vercel docs (October 2026)

- **Python:** 3.12, read from `apps/api/.python-version`. Vercel also supports 3.13 and 3.14.
- **Bundle size:** 500 MB uncompressed per function. The API bundle is about 61 MB today.
  Tests and `src/` are excluded because the installed package is bundled.
- **Duration:** `maxDuration` is 300 s, the maximum on Hobby. Pro allows up to 800 s, and
  1800 s in beta. Raise it in `vercel.json` only together with a plan change. Work that must
  outlive a request needs durable execution, not a longer timeout.
- **Streaming:** enabled by default for Python functions. FastAPI lifespan shutdown gets at
  most 500 ms.

If the frontend and backend later need independent releases, split them into two Vercel
projects with Root Directories `apps/web` and `apps/api`. Then set `API_URL` on the web project
to the API's URL, and the existing Next.js rewrite proxies `/api/*` to it.
