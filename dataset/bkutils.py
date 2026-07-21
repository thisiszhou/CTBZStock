import datetime
from datetime import date
from zoneinfo import ZoneInfo
import numpy as np
from holidays.countries.china import China

def date2str(date: datetime.date):
    return date.strftime('%Y%m%d')


def rm_row_line(day):
    return day.replace("-", "")


def date2month(date: datetime.date):
    return date.strftime("%m")


def date2day(date: datetime.date):
    return date.strftime("%d")


def date2month_and_day(date: datetime.date):
    return date.strftime("%m%d")


def date2str_bar(date: datetime.date):
    return date.strftime("%Y-%m-%d")


def str2date(string):
    if isinstance(string, int):
        string = str(string)
    return datetime.datetime.strptime(string, "%Y%m%d").date()


def date2year(date: datetime.date):
    return str(date.year)


def str2year(string):
    return string[:4]


def str2month(string):
    return string[4:6]


def format_date(date_: date):
    return str2date(date2str(date_))


def get_beijing_time_now() -> datetime.datetime:
    return datetime.datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)

def day_is_today(day: date):
    return date2str(day) == date2str(get_beijing_time_now())


def sigmoid(x, alpha=1):
    return 1 / (1 + np.exp(-x * alpha))


def get_spring_festival(years):
    years = int(years)
    cn_holidays = China(years=years)
    spring = []
    for date, name in sorted(cn_holidays.items()):
        if name == "春节" or "Spring Festival" in name:
            spring.append(date)
    spring.sort()
    return spring[0]


