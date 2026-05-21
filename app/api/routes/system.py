from fastapi import APIRouter, Request

from app.config import get_settings
from app.integrations import Integrations


router = APIRouter(prefix="/system", tags=["system"])


@router.get("/dependencies")
async def dependencies_status(request: Request) -> dict[str, object]:
    integrations: Integrations = request.app.state.integrations
    return await integrations.status()


@router.get("/runtime")
async def runtime_status() -> dict[str, object]:
    settings = get_settings()
    return {
        "api_workers": settings.api_workers,
        "db_pool_min_size": settings.db_pool_min_size,
        "db_pool_max_size": settings.db_pool_max_size,
        "note": "API workers are changed in .env and require docker compose up --build -d.",
    }
