from transaction.order_manager import OrderManager, InnerOrder, InnerOrderStatus
from schema.stock import OrderSide, OrderType, Tick, Order, OrderStatus
import gm.api as gmapi
from loguru import logger
import traceback
from schema.status import PositionEffect
from utils.timetool import get_current_hms_str
import utils.api_func as ua
from third_part.feishu_service import send_group_msg
import time
from typing import Optional, List
from utils.report import report_positions_and_cash, report_dealing_price

SELL_SILDE = 2 / 1000


def do_transaction(context):
    order_manager: OrderManager = context.order_manager
    if order_manager.done():
        return
    orders = order_manager.get_all_unfinished_sell_order() + order_manager.get_all_unfinished_buy_order()
    for order in orders:
        if order.side == OrderSide.OrderSide_Sell:
            slide_price = order.price - max(0.01, round(order.price * SELL_SILDE, 2))
            gmapi.order_volume(symbol=order.symbol,
                               volume=order.volume,
                               side=OrderSide.OrderSide_Sell,
                               order_type=OrderType.OrderType_Limit,
                               price=min(slide_price, order.price_max),
                               position_effect=PositionEffect.PositionEffect_Close)
            logger.info(f"--- Sell order sent before 9:30 --- symbol: {order.symbol} slide price: {slide_price}"
                        f", volume: {order.volume}")
            order_manager.change_status_to_checking(order)
        if order.side == OrderSide.OrderSide_Buy and order_manager.sell_orders_done():
            if order.value / order.price > 1.05 * 100:
                slide_price = order.price + max(0.01, round(order.price * SELL_SILDE, 2))
                gmapi.order_value(symbol=order.symbol,
                                  price=max(slide_price, order.price_min),
                                  value=order.value,
                                  side=OrderSide.OrderSide_Buy,
                                  order_type=OrderType.OrderType_Limit,
                                  position_effect=PositionEffect.PositionEffect_Open)
                logger.info(f"--- Buy order sent before 9:30 --- symbol: {order.symbol} slide price: {slide_price}"
                            f", value: {order.value}")
                order_manager.change_status_to_checking(order)
            else:
                logger.info(f"--- Buy order done, because not enough value --- symbol: {order.symbol}"
                            f" price: {order.price}, value: {order.value}")
                order_manager.change_status_to_done(order)
    # 等待开盘放行
    while get_current_hms_str() < context.config.trade_start_time:
        time.sleep(0.5)
    logger.info(f"----- It's trading time, Let's start ! ----------")
    for symbol in context.order_manager.get_all_symbols():
        gmapi.subscribe(symbols=symbol, frequency="tick")
        logger.info(f"----- symbol: {symbol} subscribe ! ------")


def on_tick(context, tick):
    logger.info(f"receive tick data: {tick}")
    if tick is None:
        logger.warning(f"----- tick is None ! ------")
        return
    try:
        if context.order_manager.is_symbol_done(tick["symbol"]):
            gmapi.unsubscribe(symbols=tick.symbol, frequency='tick')
            logger.info(f"----- symbol: {tick.symbol} unsubscribe ! ------")
            if context.order_manager.done():
                # 上报持仓细节
                report_positions_and_cash(context)
                # 上报成交滑点
                buy_r, sell_r, sl, bl = report_dealing_price(context)
                if len(buy_r) > 0 or len(sell_r) > 0:
                    content = f"Order Slide analyse: sell avg slide: {round(sl, 3)}, buy avg slide: {round(bl, 3)}\n"
                    for symbol in sell_r:
                        content += f"sell {symbol}, avg price: {sell_r[symbol]}\n"
                    for symbol in buy_r:
                        content += f"buy {symbol}, avg price: {buy_r[symbol]}\n"
                    send_group_msg(context, content)
        else:
            single_symbol_tick_transaction(context, tick)
    except Exception as e:
        logger.error(f"on_tick function failed: {e}")
        logger.error(traceback.format_exc())


def single_symbol_tick_transaction(context, data):
    tob: Tick = transform_tick_or_bar(data)
    logger.info(f"receive tick data, symbol: {tob.symbol}!")
    order_manager: Optional[OrderManager] = context.order_manager
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
        logger.info(f"------ symbol: {tob.symbol}, ----- status: Checking --------")
        status, orders = ua.check_if_order_finished(tob.symbol)
        if status:
            # 交易成功
            order_manager.change_status_to_done(i_order)
            return
        else:
            # 有交易失败
            gmapi.order_cancel(orders)
            logger.info(f"------ symbol: {tob.symbol}, ----- order canceled --------")
            time.sleep(5)
            order_transaction(i_order, context, tob)
            return


def order_transaction(inner_order: InnerOrder, context, tob: Tick):
    orders, orders_ori = ua.get_symbol_order(tob.symbol)
    orders: List[Order] = [x for x in orders
                           if x.status == OrderStatus.Canceled
                           or x.status == OrderStatus.Filled
                           or x.status == OrderStatus.PartiallyFilled]
    if inner_order.side == OrderSide.OrderSide_Sell:
        volume = inner_order.volume - sum([x.filled_volume for x in orders if x.side == OrderSide.OrderSide_Sell])
        if volume > 0:
            if tob.quotes is not None:
                price = tob.quotes[4].bid_p
            else:
                price = tob.price
            if price == 0:
                logger.error(f"price is zero ! symbol: {tob.symbol}, price: {price}, quotes: {tob.quotes}")
                context.order_manager.change_status_to_done(inner_order)
            gmapi.order_volume(symbol=tob.symbol,
                               volume=volume,
                               side=OrderSide.OrderSide_Sell,
                               order_type=OrderType.OrderType_Limit,
                               price=price,
                               position_effect=PositionEffect.PositionEffect_Close)
            time.sleep(2)
            context.order_manager.change_status_to_checking(inner_order)
            logger.info(f"--- Sell happened --- symbol: {tob.symbol} current price: {tob.price}"
                        f" report price: {price}, volume: {volume}")
    if inner_order.side == OrderSide.OrderSide_Buy and context.order_manager.sell_orders_done():
        value = inner_order.value - sum([x.filled_amount for x in orders if x.side == OrderSide.OrderSide_Buy])
        if tob.quotes is not None:
            price = tob.quotes[4].ask_p
        else:
            price = tob.price
        if price == 0:
            logger.error(f"price is zero ! symbol: {tob.symbol}, price: {price}, quotes: {tob.quotes}")
            context.order_manager.change_status_to_done(inner_order)
        elif (value / price) > (1 + context.config.slide_rate) * 100:
            gmapi.order_value(symbol=tob.symbol,
                              price=price,
                              value=value,
                              side=OrderSide.OrderSide_Buy,
                              order_type=OrderType.OrderType_Limit,
                              position_effect=PositionEffect.PositionEffect_Open)
            time.sleep(2)
            context.order_manager.change_status_to_checking(inner_order)
            logger.info(f"--- Buy happened --- symbol: {tob.symbol} current price: {tob.price}"
                        f" report price: {price}, value: {value}")
        else:
            context.order_manager.change_status_to_done(inner_order)


def transform_tick_or_bar(data):
    return Tick(symbol=data['symbol'],
                price=data['price'],
                quotes=data['quotes']
                )
