import datetime
import gm.api as gmapi
from loguru import logger
import holidays
import time
from typing import Literal, overload


def get_format_time(date, ttype=1):
    if ttype == 1:
        return date.strftime("%Y-%m-%d/%H-%M-%S")
    elif ttype == 2:
        return date.strftime("%Y-%m-%d %H:%M:%S")


def get_real_time_run_time_node():
    date = datetime.datetime.utcnow() + datetime.timedelta(hours=8) + datetime.timedelta(seconds=3)
    # date = datetime.datetime.utcnow() - datetime.timedelta(hours=7) + datetime.timedelta(seconds=3)
    return date.strftime("%H:%M:%S")


def rm_tzinfo(date):
    return date.replace(tzinfo=None)


def get_current_hms_str():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%H:%M:%S")


@overload
def get_beijing_now(format: Literal[True] = True) -> str:
    ...


@overload
def get_beijing_now(format: Literal[False]) -> datetime.datetime:
    ...


def get_beijing_now(format=True):
    if format:
        return get_format_time(datetime.datetime.utcnow() + datetime.timedelta(hours=8))
    else:
        return datetime.datetime.utcnow() + datetime.timedelta(hours=8)


def date2str(date):
    return date.strftime("%Y-%m-%d")


def rm_day_str_line(string):
    return string.replace("-", "")


def date2str_offline(date):
    return date.strftime("%Y%m%d")


def date2str_sec(date):
    return date.strftime("%Y-%m-%d %H:%M:%S")


def date_str2year(string):
    return string[:4]


def date2month(date):
    return date.strftime("%m")


def offline_str2date(string):
    return datetime.datetime.strptime(string, "%Y%m%d").date()


def str2date(string):
    return datetime.datetime.strptime(string, "%Y-%m-%d")


def code2symbol(code):
    if code.startswith("60") or code.startswith("68"):
        return "SHSE." + code
    if code.startswith("00") or code.startswith("30"):
        return "SZSE." + code


def symbol2code(symbol):
    return symbol.split(".")[-1]


def date2strclose(date):
    return date.strftime("%Y-%m-%d 15:00:00")


def is_today_trade_day(date):
    today = date2str(date)
    return is_day_trade_day(today)


def is_today_first_day_of_month(date):
    day = date2str(date)
    last_day = gmapi.get_previous_n_trading_dates("SZSE", day, n=1)[0]
    logger.debug(f"in is_today_first_day_of_month: date: {date}, day: {day}, last_day: {last_day}, "
                 f"m1: {str2date(last_day).month}, m2: {date.month}")
    if str2date(last_day).month != date.month:
        return True
    else:
        return False


def is_yesterday_trade_day(date):
    yesterday = date2str(date - datetime.timedelta(days=1))
    return is_day_trade_day(yesterday)


def is_day_trade_day(day: str):
    last_day = gmapi.get_previous_n_trading_dates("SZSE", day, n=1)[0]
    next_day = gmapi.get_next_n_trading_dates("SZSE", last_day, n=1)[0]
    return day == next_day


def get_last_trade_day_exclude(day: str):
    next_day = gmapi.get_next_n_trading_dates("SZSE", day, n=1)[0]
    return gmapi.get_previous_n_trading_dates("SZSE", next_day, n=1)[0]


def get_spring_festival(years):
    years = int(years)
    cn_holidays = holidays.China(years=years)
    # logger.info(f"cn_holidays : {cn_holidays}")
    spring = []
    for date, name in sorted(cn_holidays.items()):
        if name == "春节":
            spring.append(date)
    spring.sort()
    spring = spring[0]
    return spring


def str2strptime(start_time_str):
    time_array = time.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
    return int(time.mktime(time_array))
