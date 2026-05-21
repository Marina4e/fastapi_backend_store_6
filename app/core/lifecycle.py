from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.db import create_pool
from app.integrations import Integrations


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.db_pool = await create_pool()
    app.state.integrations = Integrations(settings)
    await app.state.integrations.connect()

    try:
        yield
    finally:
        await app.state.integrations.close()
        await app.state.db_pool.close()
