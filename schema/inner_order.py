from pydantic import BaseModel
from collections import defaultdict
from enum import IntEnum
from schema.stock import OrderSide, ExecRpt
from typing import Dict, Set, Optional, List


class InnerOrderStatus(IntEnum):
    Waiting = 1
    Checking = 2
    Done = 3


class InnerOrder(BaseModel):
    symbol: str
    side: OrderSide
    price: Optional[float] = None
    volume: int = 0
    value: float = 0
    trigger_time: str = "tick"
    inner_status: Optional[InnerOrderStatus] = None
    is_suspended: int = 0
    is_st: bool = False
    open: float
    inc_open: float
    price_max: Optional[float] = None
    price_min: Optional[float] = None
