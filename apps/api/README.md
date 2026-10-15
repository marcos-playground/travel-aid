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
```

Modules under `src/travel_aid/` follow the [Architecture](https://github.com/Marcos-Coca/travel-aid/wiki/Architecture)
page. All public routes live under `/api`.
