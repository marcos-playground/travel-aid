# @travel-aid/web

Next.js frontend for Travel Aid. See the [root README](../../README.md) for setup.

- `pnpm dev` starts the app on http://localhost:3000.
- Requests to `/api/*` are proxied to the FastAPI backend at `API_URL` (see `.env.example`).
- Backend types come from `@travel-aid/api-client`, generated from the FastAPI OpenAPI schema.
