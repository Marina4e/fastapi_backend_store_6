from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import api_router
from app.config import get_settings
from app.core.lifecycle import lifespan
from app.middleware.cors import setup_cors
from app.middleware.frontend_cache import DisableFrontendCacheMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="High Load Store API",
        version="1.0.0",
        lifespan=lifespan,
    )

    setup_cors(app, settings.allowed_origins)
    app.add_middleware(DisableFrontendCacheMiddleware)
    app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")
    app.include_router(api_router)

    @app.get("/", include_in_schema=False)
    async def root() -> FileResponse:
        return FileResponse("frontend/index.html")

    return app
