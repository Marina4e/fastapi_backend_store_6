import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from app.db import get_connection
from app.repositories.products import get_product_by_id, reset_stock
from app.schemas.products import ProductResponse, StockResetRequest


router = APIRouter(prefix="/products", tags=["products"])


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    connection: asyncpg.Connection = Depends(get_connection),
) -> ProductResponse:
    row = await get_product_by_id(connection, product_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return ProductResponse(**dict(row))


@router.post("/{product_id}/reset", response_model=ProductResponse)
async def reset_product_stock(
    product_id: int,
    payload: StockResetRequest,
    connection: asyncpg.Connection = Depends(get_connection),
) -> ProductResponse:
    row = await reset_stock(connection, product_id, payload.stock)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return ProductResponse(**dict(row))
