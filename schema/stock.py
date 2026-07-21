from pydantic import BaseModel
from typing import List, Dict, Set, Optional, Union
from schema.status import OrderType, OrderStatus, OrderSide, ExecType, OrderRejectReason, CancelOrderRejectReason
import datetime
from utils.timetool import date2str_sec


class InnerStockShoot(BaseModel):
    symbol: str
    pre_close: float
    is_suspended: int
    is_st: bool

    open: float
    close: float
    amount: float
    volume: float

    inc_close: float
    inc_open: float
    price_max: float
    price_min: float
    turn_rate: float  # 换手率 * 100

    pe_lyr: Optional[float] = None
    pcf_lyr_oper: Optional[float] = None

    def __init__(self, **kwargs):
        kwargs["pre_close"] = round(kwargs["pre_close"], 2)
        kwargs["inc_close"] = (kwargs["close"] / kwargs["pre_close"] - 1) * 100
        kwargs["inc_open"] = (kwargs["open"] / kwargs["pre_close"] - 1) * 100
        super().__init__(**kwargs)


class BaseStock(BaseModel):
    symbol: str
    sec_name: Optional[str] = None
    sec_level: int
    is_suspended: int
    pre_close: float
    trade_date: datetime.datetime


class StockFeature(BaseModel):
    symbol: str
    tot_mv: Optional[float] = None
    pe_lyr: Optional[float] = None


class StockShootD1(BaseModel):
    symbol: str
    open: float
    close: float
    inc_close: float
    pre_close: float
    amount: float
    volume: float
    turn_rate: float


class Position(BaseModel):
    symbol: str  # 'SHSE.600419'
    side: int
    volume: int  # 总持仓量
    volume_today: int  # 今买入量
    market_value: float  # 持仓总市值
    price: float  # 当前行情价
    vwap: float  # 持仓均价


class Quote(BaseModel):
    bid_p: float  # 买价
    bid_v: int  # 买量
    ask_p: float  # 卖价
    ask_v: int  # 卖量


class Tick(BaseModel):
    symbol: str
    price: float  # 最新价
    quotes: Optional[List[Quote]] = None


class Order(BaseModel):
    symbol: str
    strategy_id: str
    account_id: str
    cl_ord_id: str
    status: OrderStatus
    side: OrderSide
    order_type: OrderType
    volume: int
    price: float
    value: float
    filled_volume: int  # 已成量
    filled_amount: float  # 已成金额
    ord_rej_reason: Optional[Union[OrderRejectReason, CancelOrderRejectReason]] = None  # 委托拒绝原因
    ord_rej_reason_detail: Optional[str] = None  # 委托拒绝原因描述


class ExecRpt(BaseModel):
    symbol: str
    side: OrderSide
    exec_type: ExecType
    price: float
    volume: int
    amount: float
    commission: float
    cost: float
    created_at: str

    def __init__(self, **kwargs):
        kwargs["created_at"] = date2str_sec(kwargs["created_at"])
        super().__init__(**kwargs)



