import datetime
import gm.api as gmapi
from loguru import logger


def get_format_time(date):
    return date.strftime("%Y-%m-%d/%H-%M-%S")


def get_real_time_run_time_node():
    date = datetime.datetime.utcnow() + datetime.timedelta(hours=8) + datetime.timedelta(seconds=3)
    return date.strftime("%H:%M:%S")


def rm_tzinfo(date):
    return date.replace(tzinfo=None)


def get_current_hms_str():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%H:%M:%S")


def get_beijing_now():
    return get_format_time(datetime.datetime.utcnow() + datetime.timedelta(hours=8))


def date2str(date):
    return date.strftime("%Y-%m-%d")


def date2str_offline(date):
    return date.strftime("%Y%m%d")


def date2str_sec(date):
    return date.strftime("%Y-%m-%d %H:%M:%S")


def str2date(string):
    return datetime.datetime.strptime(string, "%Y-%m-%d")


def code2symbol(code):
    if code.startswith("60"):
        return "SHSE." + code
    if code.startswith("00"):
        return "SZSE." + code


def symbol2code(symbol):
    return symbol.split(".")[-1]


def date2strclose(date):
    return date.strftime("%Y-%m-%d 15:00:00")


def is_today_trade_day(date):
    today = date2str(date)
    return is_day_trade_day(today)


def is_yesterday_trade_day(date):
    yesterday = date2str(date - datetime.timedelta(days=1))
    return is_day_trade_day(yesterday)


def is_day_trade_day(day: str):
    last_day = gmapi.get_previous_trading_date("SZSE", day)
    next_day = gmapi.get_next_trading_date("SZSE", last_day)
    return day == next_day
