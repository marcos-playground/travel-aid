# travel-aid API

FastAPI backend for Travel Aid: product endpoints, search coordination, persistence, and the AI
planning workflow. See the [root README](../../README.md) for setup.

```bash
uv sync                  # install dependencies into .venv
uv run fastapi dev       # http://127.0.0.1:8000, docs at /docs
uv run pytest            # tests
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy src tests    # type check
uv run migrate           # create initial planning tables; requires Neon connection
```

Modules under `src/travel_aid/` follow the [Architecture](https://github.com/marcos-playground/travel-aid/wiki/Architecture)
page. All public routes live under `/api`. On Vercel the app is loaded through `asgi.py` (see
[Deployment](../../README.md#deployment-vercel) in the root README).

## Flight integration decision

Use [Fli](https://github.com/punitarani/fli) (`flights` on PyPI, `fli` in Python) as a library
inside a flight provider adapter. API handlers and the planning agent reuse the same search
function. The initial integration uses HTTP page retrieval without a headless browser or a
separate MCP server. Map Fli results into application-owned offers before returning them to
the frontend.

See the [Fli dependency review](https://github.com/marcos-playground/travel-aid/wiki/Fli-Dependency-Review)
for the source inspection, scanner results, limitations, and remaining validation. Flight
search is the first delivery milestone; hotel integration comes later.

The flight workflow is implemented in `planning/`, `providers/fli.py`, and
`recommendations/flights.py`. Planning needs `OPENAI_API_KEY` and `DATABASE_URL`; it defaults
to `gpt-6-luna` via the Responses API. Apply the migration with `DATABASE_URL_UNPOOLED` before
serving planning requests.

`pytest` runs isolated workflow and HTTP tests without provider credentials. To exercise real
PostgreSQL locking and recovery locally, supply **a dedicated test database** as
`TEST_DATABASE_URL`. That integration test skips when unset; CI runs it with a PostgreSQL
service. It never reads the runtime `DATABASE_URL` for tests. Live OpenAI/Neon verification is
available separately from automated tests.
