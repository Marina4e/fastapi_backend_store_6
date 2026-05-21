from pydantic import BaseModel, Field


class PurchaseRequest(BaseModel):
    user_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    purchased_count: int = Field(gt=0)


class PurchaseResponse(BaseModel):
    status: str
