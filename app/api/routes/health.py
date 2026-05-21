import asyncpg
from fastapi import APIRouter, Depends

from app.db import get_connection


router = APIRouter(tags=["health"])


@router.get("/health")
async def health(connection: asyncpg.Connection = Depends(get_connection)) -> dict[str, str]:
    await connection.fetchval("SELECT 1")
    return {"status": "ok"}
