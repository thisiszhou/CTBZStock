from pydantic import BaseModel
from typing import List, Dict, Optional


class Stock(BaseModel):
    code: str
    day: str
    open: Optional[float] = None
    close: Optional[float] = None
    pre_close: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    turn_rate: Optional[float] = None
    upper_limit: Optional[float] = None
    lower_limit: Optional[float] = None
    increase_rate: Optional[float] = None  # 现11元, 基10元, 涨幅10%, increase_rate=10
    name: Optional[str] = None
    open_increase_rate: Optional[float] = None
    market_value: Optional[float] = None
    circulate_value: Optional[float] = None
    is_st: Optional[bool] = None
    is_suspended: Optional[bool] = None
    listed_date: Optional[str] = None
    delisted_date: Optional[str] = None
    delisting_begin_date: Optional[str] = None
    pe_lyr: Optional[float] = None
    pe_ttm: Optional[float] = None
    pb_lyr: Optional[float] = None
    pcf_lyr_oper: Optional[float] = None
    dy_ttm: Optional[float] = None  # 股息率 TTM %
    dy_lfy: Optional[float] = None  # 股息率 年报/LFY %
    pub_date: Optional[str] = None
    rpt_date: Optional[str] = None
    eps_base: Optional[float] = None
    inc_oper: Optional[float] = None
    net_prof: Optional[float] = None
    roe_weight_avg: Optional[float] = None  # 加权平均 ROE %
    inc_oper_yoy: Optional[float] = None  # 营业收入同比 %
    net_prof_pcom_yoy: Optional[float] = None  # 归母净利润同比 %
    eps_yoy: Optional[float] = None  # 每股收益同比 %


class DIndex(BaseModel):
    name: Optional[str] = None
    code: str
    day: str
    open: Optional[float] = None
    close: Optional[float] = None
    pre_close: Optional[float] = None
    increase_rate: Optional[float] = None  # 现11元，基10元，涨幅10%，increase_rate=10
    open_increase_rate: Optional[float] = None
    avg_market_value: Optional[float] = None
    avg_volume: Optional[float] = None
    pe_lyr: Optional[float] = None
    pb_lyr: Optional[float] = None
    constituents: Optional[List[str]] = None
    high_retrace_rate: Optional[float] = None  # 当前close距历史前高的回撤跌幅，单位%，新高时为0
    historical_high: Optional[float] = None



