"""小市值 Demo（回测）：全市场按总市值升序，无择时轮动 Top10。"""

import datetime
from datetime import date
from typing import List

import numpy as np
from loguru import logger

from dataset.bkapi import get_last_trade_day, get_next_trade_day
from dataset.bkutils import str2date
from dataset.schema import Stock
from dataset.stock_db import is_stock_down_limit, is_stock_up_limit
from system.simulation import Simulation

STRATEGY_NAME = "小市值Demo"
TOP_NUM = 10
MIN_TRADE_VALUE = 5000


def buy_stock_filter(day: date, stock_shoot: Stock) -> bool:
    """返回 True 表示过滤掉（不可买入）。"""
    if stock_shoot is None or stock_shoot.open is None:
        return True
    if not stock_shoot.code.startswith("00") and not stock_shoot.code.startswith("60"):
        return True
    if stock_shoot.open < 1.8:
        return True
    if stock_shoot.is_st or stock_shoot.is_suspended:
        return True
    if stock_shoot.listed_date is None:
        return True
    if day - str2date(stock_shoot.listed_date) < datetime.timedelta(days=30):
        return True
    if (
        stock_shoot.delisting_begin_date is not None
        and day >= str2date(stock_shoot.delisting_begin_date)
    ):
        return True
    price, inc = stock_shoot.open, stock_shoot.open_increase_rate
    if price is None or np.isnan(price) or inc is None:
        return True
    if is_stock_down_limit(stock_shoot.open, stock_shoot) or is_stock_up_limit(
        stock_shoot.open, stock_shoot
    ):
        return True
    return False


def holding_stock_filter(day: date, stock_shoot: Stock) -> bool:
    """返回 True 表示应卖出。"""
    if stock_shoot is None:
        return True
    if stock_shoot.is_st:
        return True
    if (
        stock_shoot.delisting_begin_date is not None
        and day >= str2date(stock_shoot.delisting_begin_date)
    ):
        return True
    return False


class SmallCapDemo(Simulation):
    """无择时小市值轮动：每日开盘将持仓调至市值最小的 TOP_NUM 只，等权满仓。"""

    def __init__(self, *args, **kwargs):
        # Demo 不依赖指数库
        kwargs.setdefault("index_db_folder", None)
        super().__init__(*args, **kwargs)
        self.position = dict()

    def get_candidate_codes(self, day: date) -> List[str]:
        min_stock = []
        next_day = get_next_trade_day(day)
        for code in self.stock_db.symbols.keys():
            stock_shoot = self.stock_db.get_stock_info(code, next_day)
            if buy_stock_filter(next_day, stock_shoot):
                continue
            stock_shoot = self.stock_db.get_stock_info(code, day)
            if stock_shoot is None or stock_shoot.market_value is None:
                continue
            value = stock_shoot.market_value
            if len(min_stock) < TOP_NUM * 10:
                min_stock.append((value, code))
            else:
                if min_stock[-1][0] > value:
                    min_stock[-1] = (value, code)
            min_stock.sort(key=lambda x: x[0])
        return [x[1] for x in min_stock]

    def decide(self, day: date, time_node) -> List[str]:
        holding = self.get_holding_position_share()
        # 停牌/跌停无法卖出的持仓强制保留
        forced = []
        for code in holding.keys():
            stock_shoot = self.stock_db.get_stock_info(code, day)
            if stock_shoot is None:
                forced.append(code)
                continue
            if stock_shoot.is_suspended or self.stock_db.if_price_boundary(
                code, day, "open", "low"
            ):
                forced.append(code)

        ranked = self.get_candidate_codes(get_last_trade_day(day))
        target = list(forced)
        for code in ranked:
            if code in target:
                continue
            # 持仓已变 ST / 退市整理的，不再留在目标中
            if code in holding:
                st = self.stock_db.get_stock_info(code, day)
                if holding_stock_filter(day, st):
                    continue
            target.append(code)
            if len(target) >= TOP_NUM:
                break
        return target[:TOP_NUM]

    def transaction(self, day: date, time_node):
        if time_node == "close":
            return
        asset = self.get_asset(day, time_node="open")
        stock_codes = self.decide(day, time_node="open")
        real_p_size = 1.0  # 无择时：始终满仓

        holding_values = self.get_per_position_value(day, time_node)
        dead_m = 0
        dead_n = 0
        for code, val in holding_values.items():
            st = self.stock_db.get_stock_info(code, day)
            if st is not None and st.is_suspended:
                dead_m += val
                dead_n += 1

        if not stock_codes:
            avg_pos = 0
        elif dead_n == 0:
            avg_pos = asset * real_p_size / len(stock_codes)
        elif dead_n == len(stock_codes):
            avg_pos = 0
        else:
            avg_pos = (asset * real_p_size - dead_m) / (len(stock_codes) - dead_n)

        holding_position = self.get_holding_position_share()
        for code in list(holding_position.keys()):
            price, _ = self.stock_db.get_price(code, day, time_node="open")
            if not price or np.isnan(price):
                continue
            value = price * holding_position[code] * 100
            if code in stock_codes:
                sell_share = int((value - avg_pos) / price / 100)
                if value - avg_pos > MIN_TRADE_VALUE and sell_share > 0:
                    self.sell(day=day, code=code, share=sell_share, time_node="open")
            else:
                status = self.sell(day=day, code=code, time_node="open")[0]
                if status and code in self.position:
                    del self.position[code]

        holding_position = self.get_holding_position_share()
        buy_codes = [
            (x, self.stock_db.get_price(x, day, time_node="open")[0]) for x in stock_codes
        ]
        buy_codes = [x for x in buy_codes if x[1] is not None]
        buy_codes.sort(key=lambda x: x[1], reverse=True)
        logger.debug(f"[{STRATEGY_NAME}] day={day} avg_pos={avg_pos} target={stock_codes}")

        for code, price in buy_codes:
            buy_value = avg_pos - holding_position.get(code, 0) * price * 100
            buy_value = min(buy_value, self.cash())
            if buy_value > MIN_TRADE_VALUE and int(buy_value / price / 100) > 0:
                self.buy(day=day, cash=buy_value, code=code, time_node="open")
                if code not in self.position:
                    self.position[code] = price

        for code in list(self.position.keys()):
            if code not in self.get_holding_position_share():
                del self.position[code]