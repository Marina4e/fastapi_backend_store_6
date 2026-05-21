import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.db import get_connection
from app.schemas.purchase import PurchaseRequest, PurchaseResponse
from app.services.purchase_service import purchase_product, publish_purchase_event


router = APIRouter(tags=["purchase"])


@router.post("/purchase", response_model=PurchaseResponse)
async def purchase(
    payload: PurchaseRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    connection: asyncpg.Connection = Depends(get_connection),
) -> PurchaseResponse:
    await purchase_product(connection, payload)
    background_tasks.add_task(publish_purchase_event, request.app, payload)
    return PurchaseResponse(status="success")
