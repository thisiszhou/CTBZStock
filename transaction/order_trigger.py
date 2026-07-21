from transaction.order_manager import OrderManager, InnerOrder, InnerOrderStatus, TransactionLevel
from schema.stock import OrderSide, OrderType, Tick, Order, OrderStatus
import gm.api as gmapi
from loguru import logger
import traceback
from schema.status import PositionEffect, Mode
from utils.timetool import get_current_hms_str, date2str
import utils.api_func as ua
from third_part.feishu_service import send_group_msg
import time
from typing import Optional, List
from utils.report import report_positions_and_cash, report_dealing_price
from config import cons


def do_transaction(context):
    order_manager: OrderManager = context.order_manager
    if order_manager.done():
        logger.info("[timing] do_transaction skip, order_manager already done")
        return
    t0 = time.time()
    now_hms = get_current_hms_str()
    logger.info(
        f"[timing] do_transaction enter, now={now_hms}, "
        f"trade_start_time={cons.TRADE_START_TIME}"
    )
    order_manager.start(context)
    father_orders = order_manager.get_all_unfinished_sell_order() + order_manager.get_all_unfinished_buy_order()
    sell_n = sum(1 for o in father_orders if o.side == OrderSide.OrderSide_Sell)
    buy_n = sum(1 for o in father_orders if o.side == OrderSide.OrderSide_Buy)
    logger.info(f"[timing] place initial child orders begin, sell={sell_n}, buy={buy_n}, now={get_current_hms_str()}")
    t_place = time.time()
    for f_order in father_orders:
        if f_order.side == OrderSide.OrderSide_Sell:
            order_manager.do_child_sell_orders(context, f_order, start_time=f"{date2str(context.now)} 09:30:00")
        if f_order.side == OrderSide.OrderSide_Buy and order_manager.is_buy_order_ready(context, f_order):
            order_manager.do_child_buy_orders(context, f_order, start_time=f"{date2str(context.now)} 09:30:00")
    logger.info(
        f"[timing] place initial child orders done, "
        f"elapsed={time.time() - t_place:.3f}s, now={get_current_hms_str()}"
    )
    # 等待开盘放行
    start_time = cons.TRADE_START_TIME
    wait_begin = get_current_hms_str()
    if wait_begin < start_time:
        logger.info(f"[timing] wait trade_start_time begin, now={wait_begin}, target={start_time}")
    while get_current_hms_str() < start_time:
        time.sleep(0.5)
    logger.info(
        f"[timing] trade gate open, waited_from={wait_begin}, "
        f"now={get_current_hms_str()}, target={start_time}, "
        f"do_transaction_elapsed={time.time() - t0:.3f}s"
    )
    logger.info(f"----- It's trading time, Let's start ! ----------")
    symbols = context.order_manager.get_all_symbols()
    logger.info(f"[timing] subscribe begin, symbol_count={len(symbols)}")
    for symbol in symbols:
        gmapi.subscribe(symbols=symbol, frequency="tick")
        logger.info(f"----- symbol: {symbol} subscribe ! ------")
    logger.info(f"[timing] do_transaction exit, total_elapsed={time.time() - t0:.3f}s")


def on_tick(context, tick):
    # logger.info(f"receive tick data: {tick}")
    if tick is None:
        logger.warning(f"----- tick is None ! ------")
        return
    if get_current_hms_str() < "09:30:00" or "11:30:00" < get_current_hms_str() < "13:00:00":
        logger.warning(f"rest time! tick: {tick}")
        return
    try:
        if context.order_manager.is_symbol_done(tick["symbol"]):
            gmapi.unsubscribe(symbols=tick.symbol, frequency='tick')
            logger.info(f"----- symbol: {tick.symbol} unsubscribe ! ------")
            if context.order_manager.done() and not context.order_manager.if_reported():
                # 上报持仓细节
                report_positions_and_cash(context)
                # 上报当日滑点统计（个股明细）；内部会落盘 trade_history
                report_dealing_price(context)
                context.order_manager.set_reported()
        else:
            single_symbol_tick_transaction(context, tick)
    except Exception as e:
        logger.error(f"on_tick function failed: {e}")
        logger.error(traceback.format_exc())


def single_symbol_tick_transaction(context, data):
    """
    return: tick, status(True is Done, False is processing)
    """
    tob: Tick = transform_tick_or_bar(data)
    order_manager: OrderManager = context.order_manager
    if order_manager.is_symbol_done(tob.symbol):
        logger.info(f"in single_symbol_tick_transaction, symbols: {tob.symbol} mission done!")
        return
    i_order: Optional[InnerOrder] = order_manager.get_unfinished_order(tob.symbol)
    if i_order is None:
        return
    assert i_order.inner_status != InnerOrderStatus.Done
    if i_order.inner_status == InnerOrderStatus.Waiting:
        logger.info(f"------ symbol: {tob.symbol}, ----- status: Waiting --------")
        order_transaction(i_order, context, tob)
    elif i_order.inner_status == InnerOrderStatus.Checking:
        if i_order.transaction_level != TransactionLevel.CanWait:
            logger.info(f"------ symbol: {tob.symbol}, ----- status: Checking --------")
        o_s, t_s = order_manager.check_order_finished(context, i_order)
        if o_s:
            # 交易成功
            return
        else:
            # 有交易失败
            if t_s:
                order_transaction(i_order, context, tob)
            return


def order_transaction(father_order: InnerOrder, context, tob: Tick):
    order_manager: OrderManager = context.order_manager
    if father_order.side == OrderSide.OrderSide_Sell:
        order_manager.do_child_sell_orders(context, father_order, tob)
    if father_order.side == OrderSide.OrderSide_Buy and order_manager.is_buy_order_ready(context, father_order):
        order_manager.do_child_buy_orders(context, father_order, tob)


def transform_tick_or_bar(data):
    return Tick(symbol=data['symbol'],
                price=data['price'],
                quotes=data['quotes']
                )