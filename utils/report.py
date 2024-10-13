from typing import Dict, List
from schema.stock import Position, ExecRpt, OrderSide
from utils.context_func import get_all_positions, get_cash, get_all_market_value
from utils.api_func import get_exec_rpt
from loguru import logger
from third_part.feishu_service import send_group_msg
from collections import defaultdict


def report_positions_and_cash(context):
    positions: Dict[str, Position] = get_all_positions(context)
    cash = get_cash(context)
    market_value = get_all_market_value(context, positions=positions)
    assets = cash + market_value
    info = f"Assets: {round(assets)}, Cash: {round(cash)}\n"
    info += "All Positions: \n"
    for posi in positions.values():
        info += f"symbol: {posi.symbol}, value: {round(posi.market_value)}, " \
                f"profit: {round((posi.price / posi.vwap - 1) * 100, 2)}%\n"
    info += "\n"
    logger.info(info)
    send_group_msg(context, info)


def report_dealing_price(context):
    exec_rpt: List[ExecRpt] = get_exec_rpt()
    buy_dict = defaultdict(list)
    sell_dict = defaultdict(list)
    for exec_ in exec_rpt:
        if exec_.side == OrderSide.OrderSide_Buy:
            buy_dict[exec_.symbol].append((exec_.volume, exec_.amount))
        if exec_.side == OrderSide.OrderSide_Sell:
            sell_dict[exec_.symbol].append((exec_.volume, exec_.amount))
    buy_r = dict()
    sell_r = dict()
    for symbol, value in buy_dict.items():
        volume = 0
        amount = 0
        for v, a in value:
            volume += v
            amount += a
        logger.info(f"Buy order, symbol: {symbol}, avg_price: {round(amount / volume, 2)}")
        buy_r[symbol] = round(amount / volume, 2)
    for symbol, value in sell_dict.items():
        volume = 0
        amount = 0
        for v, a in value:
            volume += v
            amount += a
        logger.info(f"Sell order, symbol: {symbol}, avg_price: {round(amount / volume, 2)}")
        sell_r[symbol] = round(amount / volume, 2)
    sell_slide, buy_slide = context.order_manager.analyse_slide_price(exec_rpt)
    return buy_r, sell_r, sell_slide, buy_slide
