import datetime
import gm.api as gmapi
from utils.timetool import rm_tzinfo, date2str, str2date, is_today_trade_day
from utils.context_func import get_all_positions, get_cash, get_all_market_value
from schema.stock import BaseStock, StockFeature, Position, OrderSide
from typing import Dict, Optional
from transaction.order_manager import OrderManager, InnerOrder
from loguru import logger
from third_part.ak_data import get_post_pre_close_price_and_incre
from utils.api_func import get_symbol_stock_shot
from utils.report import report_positions_and_cash
from third_part.feishu_service import send_group_msg

TOP_NUM = 10


def get_top_min_value_symbols(context, date):
    # 获取当日市值最低的topk股
    # 获取全部股票
    all_stock = [x for x in gmapi.get_instruments(
        exchanges='SHSE, SZSE',
        sec_types=[1],
        skip_st=False,
        skip_suspended=False,
        fields='symbol, sec_name, listed_date, delisted_date, sec_level, '
               'is_suspended, pre_close')
                 ]
    all_stock = [x for x in all_stock if x["symbol"][5:7] == "60" or x["symbol"][5:7] == "00"]
    all_stock = gmapi.get_history_instruments(
        symbols=[x["symbol"] for x in all_stock],
        start_date=date2str(date),
        end_date=date2str(date),
        fields="symbol,trade_date,sec_name,sec_level,is_suspended,pre_close")
    all_stock_dict = {x["symbol"]: BaseStock(**x) for x in all_stock if x["sec_level"] == 1
                      and x["is_suspended"] == 0 and '退' not in x["sec_name"] and '*' not in x["sec_name"]}
    symbols = [x for x in all_stock_dict.keys()]
    stock_feature: Dict[str, StockFeature] = dict()
    i = 0
    n = 200
    while i < len(symbols):
        if len(symbols[i:i + n]) > 0:
            stock_feature_ = {x['symbol']: StockFeature(**x) for x in
                              gmapi.get_fundamentals_n(
                                  'trading_derivative_indicator',
                                  symbols[i:i + n],
                                  date2str(date), fields='TOTMKTCAP',
                                  order_by='TOTMKTCAP', count=1)}
            stock_feature.update(stock_feature_)
        i += n
    assert len(stock_feature) == len(symbols), "stock_feature length not equal with symbols"
    # 小市值排序
    order_list = [(k, v.TOTMKTCAP) for k, v in stock_feature.items()]
    order_list.sort(key=lambda x: x[1])
    logger.info(f"MTV TOP {TOP_NUM * 3}:")
    for i in range(TOP_NUM * 3):
        logger.info(f"top {i}: symbol: {order_list[i]}, mv: {order_list[i]}")
    symbols = [x[0] for x in order_list[:TOP_NUM * 3]]
    logger.info(f"no black list symbols: {symbols}")
    return symbols


def generate_order(context) -> Optional[OrderManager]:
    """
    买入条件：
    st不买，停牌的不买
    """
    if not is_today_trade_day(context.now):
        logger.info("Today is not trading day !")
        return None
    price_dict = get_post_pre_close_price_and_incre()
    # 获取持仓
    positions: Dict[str, Position] = get_all_positions(context)
    logger.info(f"positions return: {positions}")
    # 判断是否需要新买入
    last_trade_day = str2date(gmapi.get_previous_trading_date("SZSE", date2str(context.now)))
    mv_symbols = get_top_min_value_symbols(context, last_trade_day)
    todays_no_st_no_suspend_symbols = [x['symbol'] for x in gmapi.get_instruments(symbols=mv_symbols,
                                                                                  exchanges='SHSE, SZSE',
                                                                                  sec_types=[1],
                                                                                  skip_st=True,
                                                                                  skip_suspended=True,
                                                                                  fields='symbol, pre_close')]
    todays_no_st_no_suspend_symbols = [x for x in mv_symbols if x in todays_no_st_no_suspend_symbols]
    todays_position = todays_no_st_no_suspend_symbols[: TOP_NUM]
    cash = get_cash(context)
    value = get_all_market_value(context, positions)
    logger.info(f"---- init position: total value: {value + cash} cash: {cash}----")
    avg = (cash + value) / len(todays_position)
    context.config.avg_value = avg
    logger.info(f"cash: {cash}, value: {value}, avg_value: {avg}")

    # 开始准备订单
    order_manager = OrderManager()
    order_buffer = []

    # sell out
    for symbol in positions.keys():
        if symbol not in todays_position:
            ss = get_symbol_stock_shot(context, symbol, context.now, price_dict)
            order = InnerOrder(symbol=symbol,
                               price=ss.open,
                               volume=positions[symbol].volume,
                               side=OrderSide.OrderSide_Sell,
                               is_suspended=ss.is_suspended,
                               is_st=ss.is_st,
                               open=ss.open,
                               inc_open=ss.inc_open,
                               price_max=ss.price_max,
                               price_min=ss.price_min
                               )
            order_buffer.append(order)

    # adjust
    for symbol in todays_position:
        position = positions.get(symbol, None)
        if position is None:
            delta = -avg
            price = 0.1
        else:
            delta = positions[symbol].market_value - avg
            price = positions[symbol].price
        volume = delta / price / 100
        logger.debug(f"symbol: {symbol} delta: {delta} volume: {volume}")
        if delta > 1000 and volume > 1.0 * (1 + context.config.slide_rate):
            ss = get_symbol_stock_shot(context, symbol, context.now, price_dict)
            order = InnerOrder(symbol=symbol,
                               price=ss.open,
                               volume=int(volume) * 100,
                               side=OrderSide.OrderSide_Sell,
                               is_suspended=ss.is_suspended,
                               is_st=ss.is_st,
                               open=ss.open,
                               inc_open=ss.inc_open,
                               price_max=ss.price_max,
                               price_min=ss.price_min
                               )
            order_buffer.append(order)
        if delta < -2000 and -volume > 1.0 * (1 + context.config.slide_rate):
            if delta > -5000:
                delta *= 0.7
            if delta > -10000:
                delta *= 0.9
            ss = get_symbol_stock_shot(context, symbol, context.now, price_dict)
            order = InnerOrder(symbol=symbol,
                               price=ss.open,
                               value=-delta * (1 - 0.05),
                               side=OrderSide.OrderSide_Buy,
                               is_suspended=ss.is_suspended,
                               is_st=ss.is_st,
                               open=ss.open,
                               inc_open=ss.inc_open,
                               price_max=ss.price_max,
                               price_min=ss.price_min
                               )
            order_buffer.append(order)
    for order in order_buffer:
        if order.is_suspended:
            continue
        order_manager.add_new_order(order)
    order_manager.print_orders()
    # generate trade info to report
    logger.info(f"-------------- Start order info ---------------")
    content = ""
    for order in order_manager.get_all_unfinished_sell_order() + order_manager.get_all_unfinished_buy_order():
        logger.info(f"order detail: {order}")
        if order.side == OrderSide.OrderSide_Sell:
            content = f"Sell: {order.symbol}, volume: {order.volume}.\n" + content
        else:
            content = content + f"Buy: {order.symbol}, value: {round(order.value, 2)}.\n"
    if content:
        content = "Today's trade has been ready, here is details:\n" + content
        logger.info(content)
        send_group_msg(context, content)
    else:
        content = "Today has no order \n"
        logger.info(content)
        report_positions_and_cash(context)
        send_group_msg(context, content)
    logger.info(f"-----------------------------------------------")
    return order_manager
