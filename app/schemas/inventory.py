"""扫码 API 的请求和响应结构。"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Platform = Literal["PS5", "PS4", "SWITCH", "SWITCH2"]


class ScanRequest(BaseModel):
    barcode: str = Field(pattern=r"^[0-9]{8,14}$")
    operation: Literal["IN", "OUT"]
    client_scan_id: UUID
    device_id: str | None = Field(default=None, max_length=255)


class ResolveUnknownRequest(ScanRequest):
    operation: Literal["IN"] = "IN"
    game_name: str = Field(min_length=1, max_length=255)
    platform: Platform
    region: str = Field(default="UNKNOWN", max_length=16)
    edition: str | None = Field(default=None, max_length=100)
    low_stock_threshold: int = Field(default=1, ge=0)
    overstock_threshold: int | None = Field(default=10, ge=0)

    @field_validator("game_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("game_name cannot be blank")
        return value


class ScanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    message: str
    barcode: str
    game_name: str | None = None
    platform: str | None = None
    quantity_before: int | None = None
    quantity_after: int | None = None
    transaction_id: int | None = None
    idempotent_replay: bool = False
