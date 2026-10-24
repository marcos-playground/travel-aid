from fastapi import APIRouter

from travel_aid.api import health, planning

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(planning.router)
