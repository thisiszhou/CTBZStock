from pydantic import BaseModel
from datetime import date


class PositionStock(BaseModel):
    code: str
    share: int
    vwap: float
    buy_day: date


class IndexPositionStock(BaseModel):
    code: str
    share: float
    vwap: float
    buy_day: date


class SellOrder(BaseModel):
    code: str
    sell_value: float

