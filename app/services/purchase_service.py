import asyncpg
from fastapi import FastAPI, HTTPException, status

from app.integrations import Integrations
from app.repositories.products import decrement_stock_if_available, product_exists
from app.schemas.purchase import PurchaseRequest


async def purchase_product(
    connection: asyncpg.Connection,
    payload: PurchaseRequest,
) -> None:
    updated_product_id = await decrement_stock_if_available(
        connection,
        payload.product_id,
        payload.purchased_count,
    )
    if updated_product_id is not None:
        return

    if not await product_exists(connection, payload.product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Not enough stock")


async def publish_purchase_event(app: FastAPI, payload: PurchaseRequest) -> None:
    integrations: Integrations = app.state.integrations
    try:
        await integrations.publish_purchase(payload.model_dump())
    except Exception:
        # Purchase response must not fail after stock was already decremented.
        pass
