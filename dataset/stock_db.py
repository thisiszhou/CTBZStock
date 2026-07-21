from dataset.sos_db import LocalDb, KEY_SYMBOL, KEY_DAY_DATA
from dataset.schema import Stock, DIndex
from dataset.bkutils import date2str
from dataset.bkapi import get_last_trade_day
from dataset.index_names import index_name_lookup_candidates
from typing import Any, Dict, Optional
from datetime import date
import numpy as np


def is_stock_up_limit(price, stock: Stock):
    if price >= stock.upper_limit:
        return True
    else:
        return False


def is_stock_down_limit(price, stock: Stock):
    if price <= stock.lower_limit:
        return True
    else:
        return False


class StockDB(object):
    def __init__(self, data_db: LocalDb, index_db: Optional[LocalDb] = None, etf_db: Optional[LocalDb] = None):
        self.db = data_db
        self.etf = etf_db
        self.index_db = index_db
        symbols: Dict[str, Any] = self.db.get(KEY_SYMBOL) or {}
        if etf_db is not None:
            etf_symbols = etf_db.get(KEY_SYMBOL) or {}
            symbols.update(etf_symbols)
        self.symbols = symbols

    def get_price(self, symbol, day: date, time_node):
        assert time_node in ["open", "close"]
        data: Optional[Stock]
        if symbol.startswith("15") or symbol.startswith("51"):
            assert self.etf is not None
            data = self.etf.get(KEY_DAY_DATA.format(date2str(day), symbol), Stock)
        else:
            data = self.db.get(KEY_DAY_DATA.format(date2str(day), symbol), Stock)
        if data is None:
            return None, None
        if data.is_suspended:
            return None, None
        if time_node == "open":
            return data.open, data.open_increase_rate
        else:
            return data.close, data.increase_rate

    def get_recent_price(self, *, day, code, time_node):
        price, inc = self.get_price(code, day, time_node)
        if price is not None and not np.isnan(price):
            return price, inc
        else:
            return self.get_recent_price(
                day=get_last_trade_day(day), code=code, time_node="close"
            )

    def if_price_boundary(self, symbol, day, time_node, boundary_type):
        assert time_node in ["open", "close"]
        assert boundary_type in ["high", "low"]
        data: Optional[Stock]
        if symbol.startswith("15") or symbol.startswith("51"):
            assert self.etf is not None
            data = self.etf.get(KEY_DAY_DATA.format(date2str(day), symbol), Stock)
        else:
            data = self.db.get(KEY_DAY_DATA.format(date2str(day), symbol), Stock)
        if data is None:
            return False
        if data.is_suspended:
            return False
        if time_node == "open":
            if data.open is None:
                return False
            if boundary_type == "high":
                return is_stock_up_limit(data.open, data)
            else:
                return is_stock_down_limit(data.open, data)
        else:
            if data.close is None:
                return False
            if boundary_type == "high":
                return is_stock_up_limit(data.close, data)
            else:
                return is_stock_down_limit(data.close, data)

    def get_stock_info(self, symbol, day: date) -> Optional[Stock]:
        if symbol.startswith("15") or symbol.startswith("51"):
            assert self.etf is not None
            return self.etf.get(KEY_DAY_DATA.format(date2str(day), symbol), Stock)
        return self.db.get(KEY_DAY_DATA.format(date2str(day), symbol), Stock)

    def get_index_info(self, index_name, day: date) -> Optional[DIndex]:
        if self.index_db is None:
            return None
        for name in index_name_lookup_candidates(index_name):
            data = self.index_db.get(
                KEY_DAY_DATA.format(date2str(day), name), DIndex,
            )
            if data is not None:
                return data
        return None

    def get_name(self, symbol):
        return self.symbols.get(symbol, None)

    def set(self, day: str, code, stock: Stock):
        assert len(day) == 8 and isinstance(day, str)
        key = KEY_DAY_DATA.format(day, code)
        self.db.set(key, stock)