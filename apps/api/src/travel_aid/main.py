"""FastAPI application entry point."""

from fastapi import FastAPI

from travel_aid.api.router import api_router


def create_app() -> FastAPI:
    app = FastAPI(title="Travel Aid API", version="0.1.0")
    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
