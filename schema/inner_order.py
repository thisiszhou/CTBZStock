from pydantic import BaseModel
from collections import defaultdict
from enum import IntEnum
from schema.stock import OrderSide, ExecRpt
from typing import Dict, Set, Optional, List


class InnerOrderStatus(IntEnum):
    Waiting = 1
    Checking = 2
    Done = 3


class TransactionLevel(IntEnum):
    MostUrgent = 1  # +-1.85%
    SellUrgent = 2  # 对方队列 5 价
    Normal = 3  # 对方队列 1 价 or 己方队列 1 价+-0.2%
    CanWait = 4  # 己方队列 1 价 -+ 0.5%


class InnerOrder(BaseModel):
    symbol: str
    side: OrderSide
    price: Optional[float] = None
    pre_close: float = 0
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
    transaction_level: TransactionLevel = TransactionLevel.Normal
    waiting_second: Optional[int] = None
