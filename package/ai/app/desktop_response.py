"""Response envelope for desktop-only AI endpoints."""
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    code: int = 0
    msg: str = "success"
    data: T


def success(data: T) -> BaseResponse[T]:
    return BaseResponse(data=data)
