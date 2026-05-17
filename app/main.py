import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import get_settings
from app.db import create_pool, get_connection


class PurchaseRequest(BaseModel):
    user_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    purchased_count: int = Field(gt=0)


class PurchaseResponse(BaseModel):
    status: str


class ProductResponse(BaseModel):
    product_id: int
    stock: int
    description: str


class StockResetRequest(BaseModel):
    stock: int = Field(ge=0)


app = FastAPI(title="High Load Store API", version="1.0.0")
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")


@app.middleware("http")
async def disable_frontend_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/frontend"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.on_event("startup")
async def startup() -> None:
    app.state.db_pool = await create_pool()


@app.on_event("shutdown")
async def shutdown() -> None:
    await app.state.db_pool.close()


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse("frontend/index.html")


@app.get("/health")
async def health(connection: asyncpg.Connection = Depends(get_connection)) -> dict[str, str]:
    await connection.fetchval("SELECT 1")
    return {"status": "ok"}


@app.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    connection: asyncpg.Connection = Depends(get_connection),
) -> ProductResponse:
    row = await connection.fetchrow(
        """
        SELECT product_id, stock, description
        FROM products
        WHERE product_id = $1
        """,
        product_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return ProductResponse(**dict(row))


@app.post("/products/{product_id}/reset", response_model=ProductResponse)
async def reset_product_stock(
    product_id: int,
    payload: StockResetRequest,
    connection: asyncpg.Connection = Depends(get_connection),
) -> ProductResponse:
    row = await connection.fetchrow(
        """
        UPDATE products
        SET stock = $1
        WHERE product_id = $2
        RETURNING product_id, stock, description
        """,
        payload.stock,
        product_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return ProductResponse(**dict(row))


@app.post("/purchase", response_model=PurchaseResponse)
async def purchase(
    payload: PurchaseRequest,
    connection: asyncpg.Connection = Depends(get_connection),
) -> PurchaseResponse:
    updated_product_id = await connection.fetchval(
        """
        UPDATE products
        SET stock = stock - $1
        WHERE product_id = $2
          AND stock >= $1
        RETURNING product_id
        """,
        payload.purchased_count,
        payload.product_id,
    )

    if updated_product_id is not None:
        return PurchaseResponse(status="success")

    exists = await connection.fetchval(
        "SELECT EXISTS(SELECT 1 FROM products WHERE product_id = $1)",
        payload.product_id,
    )
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Not enough stock")
