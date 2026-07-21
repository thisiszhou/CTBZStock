"""小市值 Demo（实盘）：全市场按总市值升序，无择时轮动 Top10。"""

import datetime
import os
from typing import Dict, List, Optional, Tuple

import gm.api as gmapi
import numpy as np
from loguru import logger

from config import cons
from schema.stock import OrderSide, Position
from third_part.feishu_service import send_group_msg
from transaction.order_manager import InnerOrder, OrderManager
from utils.api_func import get_symbol_stock_shot_v2
from utils.context_func import get_all_market_value, get_all_positions, get_context_cash
from utils.order_check import is_limit_down, is_limit_up
from utils.report import report_positions_and_cash
from utils.timetool import date2str, is_today_trade_day, rm_tzinfo, str2date

STRATEGY_NAME = "小市值Demo"
TOP_NUM = 10


def get_all_symbols_market_value(symbols: List[str]) -> Dict[str, float]:
    data: Dict[str, float] = {}
    n = 200
    for i in range(0, len(symbols), n):
        batch = symbols[i:i + n]
        if not batch:
            continue
        rows = gmapi.stk_get_daily_mktvalue_pt(symbols=batch, fields="tot_mv")
        data.update({x["symbol"]: x["tot_mv"] for x in rows})
    if len(data) != len(symbols):
        logger.warning(
            f"market value length not equal, output={len(data)}, symbols={len(symbols)}"
        )
    return data


def get_top_min_value_symbols(date) -> List[str]:
    """全市场主板扫描，按总市值升序返回候选列表。"""
    filter_day = date - datetime.timedelta(days=30)
    delisted_day = date + datetime.timedelta(days=30)
    all_stock = [
        x for x in gmapi.get_symbols(
            exchanges="SHSE, SZSE",
            sec_type1=1010,
            sec_type2=101001,
            skip_st=True,
            skip_suspended=True,
        )
        if rm_tzinfo(x["listed_date"]) < filter_day
        and rm_tzinfo(x["delisted_date"]) > delisted_day
        and x["symbol"][5:7] in ("60", "00")
        and "退" not in x["sec_name"]
        and "ST" not in x["sec_name"]
        and "st" not in x["sec_name"]
    ]
    symbols = [x["symbol"] for x in all_stock]
    mv_dict = get_all_symbols_market_value(symbols)
    order_list = [(k, mv_dict[k]) for k in symbols if k in mv_dict and mv_dict[k]]
    order_list.sort(key=lambda x: x[1])
    logger.info(f"[{STRATEGY_NAME}] MTV TOP {TOP_NUM * 3}:")
    for i, (sym, mv) in enumerate(order_list[: TOP_NUM * 3]):
        logger.info(f"top {i}: symbol={sym}, mv={mv}")
    return [x[0] for x in order_list]


def get_position_detail(context) -> Tuple[float, int]:
    """日终记录：当日收益率、Top3 平均市值。"""
    if not is_today_trade_day(context.now):
        check_day = gmapi.get_previous_n_trading_dates("SZSE", date2str(context.now), n=1)[0]
    else:
        check_day = date2str(context.now)
    cash = get_context_cash(context)
    value = get_all_market_value(context)
    last_trade_d = gmapi.get_previous_n_trading_dates("SZSE", check_day, n=1)[0]
    file = os.path.join("data", last_trade_d, "asset.txt")
    asset_last_day = cash + value
    if os.path.exists(file):
        with open(file, "r") as f:
            asset_last_day = float(f.readline().rstrip().split(",")[0])
    mv_symbols = get_top_min_value_symbols(str2date(check_day))
    mv_dict = get_all_symbols_market_value(mv_symbols[:3])
    mv = [mv_dict[s] for s in mv_symbols[:3] if s in mv_dict]
    market_v = int(np.mean(mv)) if mv else 0
    incre = round((cash + value) / asset_last_day * 100 - 100, 2) if asset_last_day else 0.0
    return incre, market_v


def generate_order(context) -> Optional[OrderManager]:
    """无择时：目标仓位始终为全市场市值最小的 TOP_NUM 只，等权配置。"""
    if not is_today_trade_day(context.now):
        logger.info("Today is not trading day !")
        return None

    positions: Dict[str, Position] = get_all_positions(context)
    last_trade_day = str2date(
        gmapi.get_previous_n_trading_dates("SZSE", date2str(context.now), n=1)[0]
    )
    mv_symbols = get_top_min_value_symbols(last_trade_day)
    tradeable = {
        x["symbol"]
        for x in gmapi.get_symbols(
            symbols=mv_symbols[: TOP_NUM * 3],
            exchanges="SHSE, SZSE",
            sec_type1=1010,
            sec_type2=101001,
            skip_st=True,
            skip_suspended=True,
        )
    }
    todays_position = [s for s in mv_symbols if s in tradeable][:TOP_NUM]
    if not todays_position:
        logger.warning(f"[{STRATEGY_NAME}] empty target universe")
        return None

    cash = get_context_cash(context)
    value = get_all_market_value(context, positions)
    avg = (cash + value - 10) * cons.SHIPPING_SPACE / len(todays_position)
    logger.info(
        f"[{STRATEGY_NAME}] cash={cash}, value={value}, avg={avg}, "
        f"target={todays_position}"
    )

    order_manager = OrderManager()
    order_buffer: List[InnerOrder] = []

    for symbol in positions.keys():
        if symbol in todays_position:
            continue
        ss = get_symbol_stock_shot_v2(context, symbol, context.now)
        if ss is None:
            continue
        order_buffer.append(
            InnerOrder(
                symbol=symbol,
                price=ss.open,
                volume=positions[symbol].volume,
                side=OrderSide.OrderSide_Sell,
                is_suspended=ss.is_suspended,
                is_st=ss.is_st,
                open=ss.open,
                inc_open=ss.inc_open,
                price_max=ss.price_max,
                price_min=ss.price_min,
            )
        )

    for symbol in todays_position:
        position = positions.get(symbol)
        if position is None:
            delta = -avg
            price = 0.1
        else:
            delta = position.market_value - avg
            price = position.price or 0.1
        volume = delta / price / 100
        ss = get_symbol_stock_shot_v2(context, symbol, context.now)
        if ss is None:
            continue
        if delta >= cons.MIN_TRANSACTION_AMOUNT and volume > 1.0 * (1 + cons.SLIDE_RATE):
            order_buffer.append(
                InnerOrder(
                    symbol=symbol,
                    price=ss.open,
                    volume=int(volume) * 100,
                    side=OrderSide.OrderSide_Sell,
                    is_suspended=ss.is_suspended,
                    is_st=ss.is_st,
                    open=ss.open,
                    inc_open=ss.inc_open,
                    price_max=ss.price_max,
                    price_min=ss.price_min,
                )
            )
        if delta <= -cons.MIN_TRANSACTION_AMOUNT and -volume > 1.0 * (1 + cons.SLIDE_RATE):
            order_buffer.append(
                InnerOrder(
                    symbol=symbol,
                    price=ss.open,
                    value=int(-delta),
                    side=OrderSide.OrderSide_Buy,
                    is_suspended=ss.is_suspended,
                    is_st=ss.is_st,
                    open=ss.open,
                    inc_open=ss.inc_open,
                    price_max=ss.price_max,
                    price_min=ss.price_min,
                )
            )

    for order in order_buffer:
        if order.is_suspended or order.price is None or np.isnan(order.price):
            continue
        if order.side == OrderSide.OrderSide_Sell:
            if not is_limit_down(order.price_min, order.open):
                order_manager.add_new_order(order)
        elif order.side == OrderSide.OrderSide_Buy:
            if (
                not is_limit_down(order.price_min, order.open)
                and not is_limit_up(order.price_max, order.price)
            ):
                order_manager.add_new_order(order)

    order_manager.print_orders()
    content = ""
    for order in (
        order_manager.get_all_unfinished_sell_order()
        + order_manager.get_all_unfinished_buy_order()
    ):
        logger.info(f"order detail: {order}")
        if order.side == OrderSide.OrderSide_Sell:
            content = f"Sell: {order.symbol}, volume: {order.volume}.\n" + content
        else:
            content += f"Buy: {order.symbol}, value: {round(order.value, 2)}.\n"
    if content:
        content = f"[{STRATEGY_NAME}] Today's trade ready:\n" + content
    else:
        content = f"[{STRATEGY_NAME}] Today has no order\n"
        report_positions_and_cash(context)
    logger.info(content)
    send_group_msg(cons.FEISHU_GROUP, content)
    return order_manager
