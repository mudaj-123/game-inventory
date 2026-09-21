"""管理员运营请求。"""

from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AdjustmentRequest(BaseModel):
    client_scan_id: UUID
    quantity_delta: int = Field(ge=-1000000, le=1000000)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("必须填写调整原因")
        return value.strip()

    @field_validator("quantity_delta")
    @classmethod
    def nonzero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("调整数量不能为零")
        return value
