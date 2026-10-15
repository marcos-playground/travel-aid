from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


@router.get("/health", operation_id="getHealth")
def get_health() -> HealthResponse:
    return HealthResponse(status="ok")
