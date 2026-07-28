from datetime import datetime

from pydantic import BaseModel


class TransactionItem(BaseModel):
    transaction_id: int
    game_name: str
    barcode: str
    platform: str
    operation_type: str
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    username: str
    created_at: datetime
    reversed: bool


class TransactionPage(BaseModel):
    items: list[TransactionItem]
    page: int
    page_size: int
    total: int


class ReverseResponse(BaseModel):
    transaction_id: int
    related_transaction_id: int
    quantity_after: int
    message: str
