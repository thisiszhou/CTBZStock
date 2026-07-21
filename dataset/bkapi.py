import time
from typing import Dict
from .schema import Stock
from .sos_db import LocalDb, KEY_SYMBOL, KEY_DAY_DATA
from .bkutils import get_beijing_time_now, format_date, str2date, date2str, day_is_today, date2year, date2month, date2day
import akshare as ak
from loguru import logger
from datetime import date
import datetime
import traceback
import copy

tool_trade_date_hist_sina_df = ak.tool_trade_date_hist_sina()
trade_days_list = [x[0] for x in tool_trade_date_hist_sina_df.values]
trade_days_list.sort()
trade_days_reverse_dict: Dict[date, int] = {day: i for i, day in enumerate(trade_days_list)}


def get_last_trade_day(day: date):
    if day in trade_days_reverse_dict.keys():
        return trade_days_list[trade_days_reverse_dict[day] - 1]
    else:
        last_day = day
        while last_day not in trade_days_reverse_dict.keys():
            last_day = last_day - datetime.timedelta(days=1)
        return last_day


def get_next_trade_day(day: date):
    if day in trade_days_reverse_dict.keys():
        return trade_days_list[trade_days_reverse_dict[day] + 1]
    else:
        next_day = day
        while next_day not in trade_days_reverse_dict.keys():
            next_day = next_day + datetime.timedelta(days=1)
        return next_day


def get_online_interval_day():
    today_date = get_beijing_time_now()
    today_date = format_date(today_date)
    if today_date in trade_days_reverse_dict.keys():
        end_day = today_date
    else:
        end_day = get_last_trade_day(today_date)
    start_day = get_last_trade_day(end_day - datetime.timedelta(days=31))
    return date2str(start_day), date2str(end_day)


def is_trade_day(day: date):
    return day in trade_days_reverse_dict.keys()


def is_today_trade_day():
    today = format_date(get_beijing_time_now())
    return today in trade_days_reverse_dict.keys()


def is_today_first_trade_day_of_month(day: date):
    last_td = get_last_trade_day(day)
    if date2month(day) != date2month(last_td):
        return True
    else:
        return False


def get_last_year_last_trade_day(day: date):
    last_year_last_day = str2date(f"{day.year - 1}1231")
    return get_last_trade_day(get_next_trade_day(last_year_last_day))


def is_today_last_trade_day_of_month(day: date):
    next_td = get_next_trade_day(day)
    if date2month(day) != date2month(next_td):
        return True
    else:
        return False


def is_today_last_trade_day_of_year(day: date):
    next_td = get_next_trade_day(day)
    if date2year(day) != date2year(next_td):
        return True
    else:
        return False


def is_today_first_trade_day_of_year(day: date):
    last_td = get_last_trade_day(day)
    if date2year(day) != date2year(last_td):
        return True
    else:
        return False


def is_today_first_trade_day_of_jan(day: date):
    last_td = get_last_trade_day(day)
    if date2month(day) != date2month(last_td) and date2month(day) == "01":
        return True
    else:
        return False


def is_today_first_trade_day_of_oct(day: date):
    last_td = get_last_trade_day(day)
    if date2month(day) != date2month(last_td) and date2month(day) == "10":
        return True
    else:
        return False


def get_real_time_data(day: date) -> Dict[str, Stock]:
    assert day in trade_days_reverse_dict.keys()
    assert day_is_today(day)
    data_dict = ak.stock_zh_a_spot_em().set_index("代码").to_dict()
    ret = dict()
    for code in data_dict['名称'].keys():
        ret[code] = Stock(
            code=code,
            day=date2str(day),
            name=data_dict['名称'][code],
            open=data_dict['今开'][code],
            close=data_dict['最新价'][code],
            increase_rate=data_dict['涨跌幅'][code]
        )
    return ret
