from pydantic import BaseModel, Field


class ProductResponse(BaseModel):
    product_id: int
    stock: int
    description: str


class StockResetRequest(BaseModel):
    stock: int = Field(ge=0)
