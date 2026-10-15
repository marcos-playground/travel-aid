from fastapi import APIRouter

from travel_aid.api import health

api_router = APIRouter()
api_router.include_router(health.router)
