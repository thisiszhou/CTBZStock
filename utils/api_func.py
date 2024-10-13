from schema.stock import InnerStockShoot, Order, OrderStatus, OrderSide, ExecRpt, ExecType
import gm.api as gmapi
from utils.timetool import date2str_sec
from loguru import logger
from typing import List


def get_symbol_stock_shot(context, symbol: str, day, price_dict) -> InnerStockShoot:
    day = date2str_sec(day)
    data1_key = ["symbol", "open", "close", "amount", "volume"]
    data2_key = ["symbol", "sec_level", "pre_close", "is_suspended"]
    data1 = price_dict[symbol].dict()
    data1 = {key: value for key, value in data1.items() if key in data1_key}
    data2 = gmapi.get_history_instruments(
        symbols=symbol,
        start_date=day,
        end_date=day,
        fields="symbol,trade_date,sec_level,is_suspended,pre_close")[0]
    data2 = {key: value for key, value in data2.items() if key in data2_key}
    data2["is_st"] = data2["sec_level"] != 1
    logger.debug(f"get_symbol_stock_shot: symbol: {symbol}, time: {day}, data1: {data1}, data2: {data2}")
    data1.update(data2)
    return InnerStockShoot(**data1)


def get_symbol_order(symbol: str):
    orders = gmapi.get_orders()
    orders = [Order(**x) for x in orders]
    orders = [x for x in orders if x.symbol == symbol]
    orders_ori = [x.dict() for x in orders]
    return orders, orders_ori


def check_if_order_finished(symbol):
    """
    try more:
    New, PartiallyFilled: retry
    PendingCancel: waiting
    Rejected: retry 3 times
    PendingNew: waiting
    else: pass
    """
    orders, orders_ori = get_symbol_order(symbol)
    logger.debug(f"checking symbol order: {symbol}, orders_ori: {orders_ori}")
    if len(
            [x for x in orders if x.status in [OrderStatus.New, OrderStatus.PartiallyFilled, OrderStatus.PendingNew]]
    ) == 0:
        return True, None
    else:
        return False, orders_ori


def get_exec_rpt() -> List[ExecRpt]:
    exec_rpts: List[ExecRpt] = [ExecRpt(**x) for x in gmapi.get_execution_reports()]
    exec_rpts = [x for x in exec_rpts if x.exec_type == ExecType.ExecType_Trade]
    tmp_sell = dict()
    tmp_buy = dict()
    for exec_rpt in exec_rpts:
        if exec_rpt.side == OrderSide.OrderSide_Sell:
            tmp = tmp_sell
        else:
            tmp = tmp_buy
        if exec_rpt.symbol not in tmp.keys():
            tmp[exec_rpt.symbol] = exec_rpt
        else:
            tmp[exec_rpt.symbol].volume += exec_rpt.volume
            tmp[exec_rpt.symbol].amount += exec_rpt.amount
    return list(tmp_sell.values()) + list(tmp_buy.values())
