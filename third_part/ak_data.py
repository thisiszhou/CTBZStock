from loguru import logger
from utils.timetool import date2str, code2symbol
from schema.stock import StockShootD1
from typing import Optional, Dict, Tuple
import akshare as ak
from utils.timetool import get_current_hms_str


def get_post_pre_close_price_and_incre() -> Dict[str, StockShootD1]:
    c_time = get_current_hms_str()
    if c_time < "09:25:00":
        raise ValueError
    elif c_time < "09:30:00":
        status = "before_open"
    else:
        status = "open"
    data_dict = ak.stock_zh_a_spot_em().set_index("代码").to_dict()
    ret = dict()
    for code in data_dict['名称'].keys():
            symbol = code2symbol(code)
            if not symbol:
                continue
            if status == "before_open":
                open_p = data_dict['最新价'][code]
            else:
                open_p = data_dict['今开'][code]
            ret[symbol] = StockShootD1(
                symbol=symbol,
                open=open_p,
                close=data_dict['最新价'][code],
                inc_close=data_dict['涨跌幅'][code],
                pre_close=data_dict['昨收'][code],
                amount=data_dict['成交额'][code],
                volume=data_dict['成交量'][code] * 100
            )
    return ret





