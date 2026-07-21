import copy
import os
import time
from schema.status import OrderType, PositionEffect, Mode
from schema.stock import OrderSide, ExecRpt, Order, Tick
from schema.inner_order import InnerOrder, InnerOrderStatus, TransactionLevel
from typing import Dict, Set, Optional, List
from loguru import logger
import gm.api as gmapi
from utils.context_func import get_all_positions, get_context_cash
from utils.api_func import get_symbol_order, get_cash, get_all_positions_from_api
from utils.timetool import str2strptime, date2str, get_beijing_now, get_current_hms_str
import numpy as np
from config.cons import ENABLE_FREE_FIVE, SLIDE_RATE
from transaction.utils_func import print_report_price_queue
from dataset.local_saver import LocalSaver

if not ENABLE_FREE_FIVE:
    MIN_BUCKET_VALUE = 50000
    SPLIT_MAX_NUM = 10
else:
    MIN_BUCKET_VALUE = 1000
    SPLIT_MAX_NUM = 100


class OrderManager(object):
    def __init__(self):
        self.sell_symbols: Dict[str, InnerOrder] = dict()
        self.buy_symbols: Dict[str, InnerOrder] = dict()
        self.sell_done_symbols: Set = set()
        self.buy_done_symbols: Set = set()
        self.order_keys = set()
        self.target_volume: Dict[str, int] = dict()
        self.order_waiting_time: Dict[str, int] = dict()
        self.reported = False
        self.saver = LocalSaver()

    def if_reported(self):
        return self.reported

    def set_reported(self):
        self.reported = True

    def add_new_order(self, order: InnerOrder):
        if order.symbol in self.order_keys:
            raise TypeError(f"Order already exists ! symbol: {order.symbol}")
        order.inner_status = InnerOrderStatus.Waiting
        if order.side == OrderSide.OrderSide_Buy:
            self.buy_symbols[order.symbol] = order
        elif order.side == OrderSide.OrderSide_Sell:
            self.sell_symbols[order.symbol] = order
        else:
            raise TypeError("Wrong Order Side !")
        self.order_keys.add(order.symbol)

    def __register_order(self, symbol, start_time):
        if start_time is None:
            self.order_waiting_time[symbol] = int(time.time())
        else:
            self.order_waiting_time[symbol] = str2strptime(start_time)

    def check_order_waiting_time(self, symbol, second):
        if int(time.time()) - self.order_waiting_time[symbol] >= second:
            return True
        else:
            return False

    def print_orders(self):
        logger.info(f"sell_order: ")
        for order in self.sell_symbols.values():
            logger.info(order)
        logger.info(f"buy_order: ")
        for order in self.buy_symbols.values():
            logger.info(order)

    def start(self, context):
        positions = get_all_positions(context)
        # 计划单快照：symbol -> plan 字段（供落盘与完成度统计）
        plan_rows: List[list] = []
        buy_orders: List[InnerOrder] = self.get_all_unfinished_buy_order()
        for buy_order in buy_orders:
            symbol = buy_order.symbol
            if symbol in positions:
                base_volume = positions[symbol].volume
            else:
                base_volume = 0
            if buy_order.price is None:
                logger.error(f"buy order price is None, skip. symbol: {symbol}, order: {buy_order}")
                continue
            buy_volume = int(buy_order.value / buy_order.price / 100) * 100
            self.target_volume[symbol] = buy_volume + base_volume
            plan_value = int(round(buy_order.value))
            plan_rows.append([
                symbol,
                "buy",
                int(buy_order.transaction_level),
                buy_order.transaction_level.name,
                buy_volume,
                plan_value,
                buy_order.open,
                buy_order.pre_close,
            ])
        sell_orders: List[InnerOrder] = self.get_all_unfinished_sell_order()
        for sell_order in sell_orders:
            symbol = sell_order.symbol
            if symbol in positions:
                base_volume = positions[symbol].volume
            else:
                base_volume = 0
            self.target_volume[symbol] = base_volume - sell_order.volume
            plan_volume = sell_order.volume
            plan_value = int(round(sell_order.value)) if sell_order.value else int(round(plan_volume * sell_order.open))
            plan_rows.append([
                symbol,
                "sell",
                int(sell_order.transaction_level),
                sell_order.transaction_level.name,
                plan_volume,
                plan_value,
                sell_order.open,
                sell_order.pre_close,
            ])
        logger.info(f"target volume: {self.target_volume}")
        self._dump_order_plan(context, plan_rows)

    def _dump_order_plan(self, context, plan_rows: List[list]):
        """
        交易开始前落盘当日计划单。
        字段: symbol, side, level, level_name, plan_volume, plan_value, open, pre_close
        """
        day = context.now
        header = [[
            "symbol", "side", "level", "level_name",
            "plan_volume", "plan_value", "open", "pre_close",
        ]]
        folder = os.path.join(self.saver.folder, date2str(day))
        os.makedirs(folder, exist_ok=True)
        self.saver.write_list(day, header + plan_rows, "order_plan.txt")
        logger.info(
            f"[timing] order_plan dumped, count={len(plan_rows)}, "
            f"path={os.path.join(folder, 'order_plan.txt')}"
        )
        for row in plan_rows:
            logger.info(
                f"order_plan: {row[0]} {row[1]} level={row[2]}({row[3]}) "
                f"vol={row[4]} value={row[5]} open={row[6]}"
            )

    def sell_order_exec(self, context, inner_order: InnerOrder, c_price):
        if inner_order.price_max is None or inner_order.price_min is None:
            logger.error(f"sell order price_max/price_min is None, skip. symbol: {inner_order.symbol}, "
                         f"price_max: {inner_order.price_max}, price_min: {inner_order.price_min}")
            return
        report_price = max(min(round(c_price, 2), inner_order.price_max), inner_order.price_min)
        gmapi.order_volume(symbol=inner_order.symbol,
                           volume=inner_order.volume,
                           side=OrderSide.OrderSide_Sell,
                           order_type=OrderType.OrderType_Limit,
                           price=report_price,
                           position_effect=PositionEffect.PositionEffect_Close)
        logger.info(f"--- Sell child order happened --- symbol: {inner_order.symbol}, price: {report_price}, "
                    f"volume: {inner_order.volume}")

    def buy_order_exec(self, context, inner_order: InnerOrder, c_price):
        cash = get_cash()
        if inner_order.price_max is None or inner_order.price_min is None:
            logger.error(f"buy order price_max/price_min is None, skip. symbol: {inner_order.symbol}, "
                         f"price_max: {inner_order.price_max}, price_min: {inner_order.price_min}")
            return
        report_price = max(min(round(c_price, 2), inner_order.price_max), inner_order.price_min)
        if inner_order.value / report_price / 100 < 1 * (SLIDE_RATE + 1) < cash / report_price / 100:
            report_value = int((SLIDE_RATE + 1) * report_price * 100)
        elif cash / report_price / 100 < 1 * (1 + SLIDE_RATE):
            logger.info(f"--- Buy child order stopped, no enough cash --- symbol:{inner_order.symbol} "
                        f"report price: {report_price}, value: {inner_order.value}")
            return
        else:
            report_value = int(inner_order.value)
        gmapi.order_value(symbol=inner_order.symbol,
                          price=report_price,
                          value=report_value,
                          side=OrderSide.OrderSide_Buy,
                          order_type=OrderType.OrderType_Limit,
                          position_effect=PositionEffect.PositionEffect_Open)
        logger.info(f"--- Buy child order happened --- symbol: {inner_order.symbol}, price: {report_price}, "
                    f"value: {report_value}")

    def get_buy_order_config(self, father_order: InnerOrder, tick: Tick) -> Optional[tuple[float, float, int]]:
        # return: max_price, min_price, order_waiting_second
        if father_order.transaction_level == TransactionLevel.CanWait:
            if tick.quotes is None:
                logger.error(f"tick.quotes is None in get_buy_order_config, symbol: {father_order.symbol}")
                return None
            if tick.quotes[0].bid_p != 0:
                anchor_price = tick.quotes[0].bid_p
            else:
                anchor_price = tick.quotes[0].ask_p
            max_price = min(round(anchor_price * 0.998, 2),
                            round(father_order.open * 0.994, 2),
                            round(father_order.pre_close * 0.998, 2))
            min_price = min(round(anchor_price * 0.99, 2),
                            round(father_order.open * 0.99, 2),
                            round(father_order.pre_close * 0.99, 2))
            order_waiting_second = 1800
        elif father_order.transaction_level == TransactionLevel.Normal:
            if get_current_hms_str() < "09:30:00":
                if father_order.inc_open >= 0:
                    anchor_price = round((father_order.open + father_order.pre_close) / 2, 2)
                elif 0 > father_order.inc_open >= -2:
                    anchor_price = round(father_order.open * 1.005, 2)
                else:
                    anchor_price = round(father_order.open * 1.008, 2)
                order_waiting_second = 120
            else:
                if tick.quotes is None:
                    logger.error(f"tick.quotes is None in get_buy_order_config, symbol: {father_order.symbol}")
                    return None
                anchor_price = tick.quotes[0].ask_p
                order_waiting_second = 60
            max_price = round(anchor_price * 1.002, 2)
            min_price = round(anchor_price * 0.982, 2)
        elif father_order.transaction_level == TransactionLevel.MostUrgent:
            anchor_price = tick.price
            max_price = round(anchor_price * 1.015, 2)
            min_price = round(anchor_price * 1.01, 2)
            if get_current_hms_str() < "09:30:00":
                order_waiting_second = 30
            else:
                order_waiting_second = 10
        else:
            raise ValueError(f"wrong TransactionLevel !")
        logger.info(f"get_buy_order_config: symbol: {father_order.symbol}, transaction_level: "
                    f"{father_order.transaction_level}, max_price: {max_price}, min_price: {min_price}, "
                    f"ows: {order_waiting_second}, anchor_price: {anchor_price}")
        return max_price, min_price, order_waiting_second

    def do_child_buy_orders(self, context, father_order: InnerOrder, tick: Optional[Tick] = None, start_time=None):
        if self.is_symbol_done(father_order.symbol):
            self.__change_status_to_done(father_order.symbol)
            return
        if tick is not None:
            logger.debug(f"tick in buy: {tick}")
        else:
            data = gmapi.current(father_order.symbol)[0]
            tick = Tick(**data)
            logger.debug(f"current in buy: {tick}")
        if tick is None:
            logger.error(f"tick is None !")
            return
        orders = get_symbol_order(father_order.symbol)
        if len(orders) > 0:
            gmapi.order_cancel(orders)
            logger.info(f"--- symbol: {father_order.symbol}, --- order cancel ---")
            time.sleep(1)
        if tick.quotes is not None and tick.quotes[0].ask_p == 0:
            logger.info(f"--- Buy has no space ---")
            self.__change_status_to_done(father_order.symbol)
            return
        buy_config = self.get_buy_order_config(father_order, tick)
        if buy_config is None:
            return
        max_price, min_price, order_waiting_second = buy_config
        if max_price == 0 or min_price == 0:
            logger.error(f"price is zero! tick: {tick}, order: {father_order}")
            self.__change_status_to_done(father_order.symbol)
            return
        father_order.waiting_second = order_waiting_second
        positions = get_all_positions_from_api()
        cash = get_cash()
        if father_order.symbol not in positions:
            hand_volume = 0
        else:
            hand_volume = positions[father_order.symbol].volume
        left_volume = self.target_volume[father_order.symbol] - hand_volume
        left_value = min(left_volume * tick.price * (1 + SLIDE_RATE), cash)
        logger.debug(f"split_num_debug, left_volume: {left_volume}, "
                     f"current_price: {tick.price}, cash: {cash}, "
                     f"target_volume: {self.target_volume[father_order.symbol]}, "
                     f"hand_volume: {hand_volume}")
        price_sn = (max_price - min_price) * 100 + 1
        value_sn = np.floor(left_value / MIN_BUCKET_VALUE)
        split_num = max(min(int(price_sn), int(value_sn), SPLIT_MAX_NUM), 1)
        split_num = max(min(split_num, int(left_volume / 100)), 1)
        logger.info(f"father_order: {father_order}, child buy order detail: left_value: {left_value}, "
                    f"split_num: {split_num}")
        print_report_price_queue(tick)
        if split_num == 1:
            if cash / tick.price / 100 < 1 * (1 + SLIDE_RATE):
                logger.info(f"--- Buy child order stopped, no enough cash --- symbol: {father_order.symbol} "
                            f"current_price: {tick.price}, left value: {left_value}, cash: {cash}")
                self.__change_status_to_done(father_order.symbol)
                return
            if left_value / tick.price / 100 < 1 * (1 + SLIDE_RATE):
                logger.info(f"--- Buy child order stopped, no enough left value --- symbol: {father_order.symbol} "
                            f"current_price: {tick.price}, left value: {left_value}, cash: {cash}")
                self.__change_status_to_done(father_order.symbol)
                return
            order_ = copy.deepcopy(father_order)
            order_.value = left_value
            c_price = max_price
            self.buy_order_exec(context, order_, c_price)
        else:
            per_value = int(left_value / split_num)
            delta_price = (max_price - min_price) / (split_num - 1)
            for i in range(split_num):
                order_ = copy.deepcopy(father_order)
                order_.value = per_value
                c_price = round(max_price - delta_price * i, 2)
                self.buy_order_exec(context, order_, c_price)
        self.__register_order(father_order.symbol, start_time)
        self.__change_status_to_checking(father_order)

    def get_sell_order_config(self, father_order: InnerOrder, tick: Tick) -> Optional[tuple[float, float, int]]:
        # return: max_price, min_price, order_waiting_second
        if father_order.transaction_level == TransactionLevel.CanWait:
            if tick.quotes is None:
                logger.error(f"tick.quotes is None in get_sell_order_config, symbol: {father_order.symbol}")
                return None
            if tick.quotes[0].ask_p != 0:
                anchor_price = tick.quotes[0].ask_p
            else:
                anchor_price = tick.quotes[0].bid_p
            max_price = max(round(anchor_price * 1.012, 2),
                            round(father_order.open * 1.016, 2),
                            round(father_order.pre_close * 1.016, 2))
            min_price = max(round(anchor_price * 1.002, 2),
                            round(father_order.open * 1.006, 2),
                            round(father_order.pre_close * 1.006, 2))
            order_waiting_second = 1800
        elif father_order.transaction_level == TransactionLevel.Normal:
            if get_current_hms_str() < "09:30:00":
                if father_order.inc_open >= 2:
                    anchor_price = round(father_order.open * 0.985, 2)
                elif 2 > father_order.inc_open >= 0:
                    anchor_price = round(father_order.open * 0.99, 2)
                elif 0 > father_order.inc_open >= -2:
                    anchor_price = round(father_order.open * 1.005, 2)
                else:
                    anchor_price = round(father_order.open * 1.01, 2)
                order_waiting_second = 120
            else:
                if tick.quotes is None:
                    logger.error(f"tick.quotes is None in get_sell_order_config, symbol: {father_order.symbol}")
                    return None
                bid_p = tick.quotes[0].bid_p
                ask_p = tick.quotes[0].ask_p
                if bid_p != 0 and ask_p != 0:
                    anchor_price = round((bid_p + ask_p) / 2, 2)
                elif bid_p != 0:
                    anchor_price = bid_p
                else:
                    anchor_price = ask_p
                order_waiting_second = 60
            max_price = round(anchor_price * 1.018, 2)
            min_price = round(anchor_price * 0.999, 2)
        elif father_order.transaction_level == TransactionLevel.SellUrgent:
            anchor_price = max(tick.price, father_order.pre_close)
            max_price = round(anchor_price * 0.998, 2)
            min_price = round(anchor_price * 0.995, 2)
            if get_current_hms_str() < "09:30:00":
                order_waiting_second = 60
            else:
                order_waiting_second = 20
        elif father_order.transaction_level == TransactionLevel.MostUrgent:
            anchor_price = tick.price
            max_price = round(anchor_price * 0.99, 2)
            min_price = round(anchor_price * 0.985, 2)
            order_waiting_second = 10
        else:
            raise ValueError(f"wrong TransactionLevel !")
        logger.info(f"get_sell_order_config: symbol: {father_order.symbol}, transaction_level: "
                    f"{father_order.transaction_level}, max_price: {max_price}, min_price: {min_price}, "
                    f"ows: {order_waiting_second}, anchor_price: {anchor_price}")
        return max_price, min_price, order_waiting_second

    def do_child_sell_orders(self, context, father_order: InnerOrder, tick: Optional[Tick] = None, start_time=None):
        if self.is_symbol_done(father_order.symbol):
            self.__change_status_to_done(father_order.symbol)
            return
        if tick is not None:
            logger.debug(f"tick in sell: {tick}")
        else:
            data = gmapi.current(father_order.symbol)[0]
            tick = Tick(**data)
            logger.debug(f"current in sell: {tick}")
        if tick is None:
            logger.error(f"tick is None !")
            return
        orders = get_symbol_order(father_order.symbol)
        if len(orders) > 0:
            gmapi.order_cancel(orders)
            logger.info(f"--- symbol: {father_order.symbol}, --- order cancel ---")
            time.sleep(1)
        # 排除跌停
        if tick.quotes is not None and tick.quotes[0].bid_p == 0:
            logger.info(f"--- Sell has no space ---")
            self.sell_order_exec(context, father_order, tick.quotes[0].ask_p)
            self.__change_status_to_done(father_order.symbol)
            return
        sell_config = self.get_sell_order_config(father_order, tick)
        if sell_config is None:
            return
        max_price, min_price, order_waiting_second = sell_config
        if max_price == 0 or min_price == 0:
            logger.error(f"price is zero! tick: {tick}, order: {father_order}")
            self.__change_status_to_done(father_order.symbol)
            return
        father_order.waiting_second = order_waiting_second
        positions = get_all_positions_from_api()
        if father_order.symbol not in positions:
            hand_volume = 0
        else:
            hand_volume = positions[father_order.symbol].volume
        left_volume = hand_volume - self.target_volume[father_order.symbol]
        if left_volume < 0:
            logger.error(
                f"sell left_volume < 0, skip. symbol: {father_order.symbol}, "
                f"hand_volume: {hand_volume}, target_volume: {self.target_volume[father_order.symbol]}, "
                f"left_volume: {left_volume}"
            )
            # 持仓已低于目标（同步延迟/超额成交），按已完成处理，避免 assert 打断 tick 链路
            self.__change_status_to_done(father_order.symbol)
            return
        if left_volume == 0:
            logger.info(
                f"sell left_volume == 0, done. symbol: {father_order.symbol}, "
                f"hand_volume: {hand_volume}, target_volume: {self.target_volume[father_order.symbol]}"
            )
            self.__change_status_to_done(father_order.symbol)
            return
        value = left_volume * tick.price
        price_sn = (max_price - min_price) * 100 + 1
        value_sn = np.floor(value / MIN_BUCKET_VALUE)
        split_num = max(min(int(price_sn), int(value_sn), SPLIT_MAX_NUM), 1)
        split_num = max(min(split_num, int(left_volume / 100)), 1)
        logger.info(f"father_order: {father_order}, child sell order detail: value: {value}, "
                    f"current_price: {tick.price}, "
                    f"split num: {split_num}, left_volume: {left_volume}")
        print_report_price_queue(tick)
        if split_num == 1:
            order_ = copy.deepcopy(father_order)
            order_.volume = left_volume
            c_price = min_price
            self.sell_order_exec(context, order_, c_price)
        else:
            per_volume = int(left_volume / split_num / 100) * 100
            delta_price = (max_price - min_price) / (split_num - 1)
            for i in range(split_num):
                order_ = copy.deepcopy(father_order)
                if i != split_num - 1:
                    order_.volume = per_volume
                else:
                    order_.volume = left_volume - per_volume * (split_num - 1)
                c_price = round(min_price + delta_price * i, 2)
                self.sell_order_exec(context, order_, c_price)
        self.__register_order(father_order.symbol, start_time)
        self.__change_status_to_checking(father_order)

    def is_buy_order_ready(self, context, order: InnerOrder):
        if order.inner_status == InnerOrderStatus.Waiting:
            cash = get_cash()
            logger.debug(f"order_ready: {order}, value: {order.value} cash: {cash}")
            if cash >= order.value:
                return True
            elif self.sell_orders_done():
                return True
            else:
                return False
        else:
            return True

    def get_all_symbols(self):
        return list(self.order_keys)

    def get_unfinished_order(self, symbol) -> Optional[InnerOrder]:
        if symbol in self.sell_symbols.keys() and self.__order_is_not_done(symbol, OrderSide.OrderSide_Sell):
            return self.sell_symbols[symbol]
        elif symbol in self.buy_symbols.keys() and self.__order_is_not_done(symbol, OrderSide.OrderSide_Buy):
            return self.buy_symbols[symbol]
        else:
            return None

    def get_all_unfinished_sell_order(self):
        return [order for order in self.sell_symbols.values()
                if self.__order_is_not_done(order.symbol, OrderSide.OrderSide_Sell)]

    def get_all_unfinished_buy_order(self):
        return [order for order in self.buy_symbols.values()
                if self.__order_is_not_done(order.symbol, OrderSide.OrderSide_Buy)]

    def check_order_finished(self, context, i_o: InnerOrder) -> tuple[bool, bool]:
        transaction_status = False
        symbol = i_o.symbol
        if self.is_symbol_done(symbol):
            return True, False
        positions = get_all_positions(context)
        if symbol not in positions:
            holding_volume = 0
        else:
            holding_volume = positions[symbol].volume
        if self.check_order_waiting_time(symbol, i_o.waiting_second):
            logger.info(f"order_waiting_time: {self.order_waiting_time}, current time: {int(time.time())}")
            transaction_status = True
        if i_o.transaction_level != TransactionLevel.CanWait:
            logger.info(f"check finished symbol: {symbol}, holding volume: {holding_volume}, "
                        f"target volume: {self.target_volume[symbol]}")
        if i_o.side == OrderSide.OrderSide_Buy:
            if get_current_hms_str() >= "14:52:00":
                self.__change_status_to_done(symbol)
                logger.info(f"Timeout! symbol: {symbol}")
                orders = get_symbol_order(symbol)
                if len(orders) > 0:
                    gmapi.order_cancel(orders)
                return True, False
            if holding_volume >= self.target_volume[symbol]:
                self.__change_status_to_done(symbol)
                return True, transaction_status
            else:
                return False, transaction_status
        elif i_o.side == OrderSide.OrderSide_Sell:
            if get_current_hms_str() >= "14:52:00":
                self.__change_status_to_done(symbol)
                logger.info(f"Timeout! symbol: {symbol}")
                return True, False
            if holding_volume <= self.target_volume[symbol]:
                self.__change_status_to_done(symbol)
                return True, transaction_status
            else:
                return False, transaction_status
        return False, False

    def is_symbol_done(self, symbol):
        sell_status = True
        buy_status = True
        if symbol in self.sell_symbols and symbol not in self.sell_done_symbols:
            sell_status = False
        if symbol in self.buy_symbols and symbol not in self.buy_done_symbols:
            buy_status = False
        return sell_status and buy_status

    def done(self):
        return self.buy_orders_done() and self.sell_orders_done()

    def sell_orders_done(self):
        return len(self.sell_done_symbols) == len(self.sell_symbols)

    def buy_orders_done(self):
        return len(self.buy_done_symbols) == len(self.buy_symbols)

    def __change_status_to_checking(self, order: InnerOrder):
        if order.side == OrderSide.OrderSide_Buy:
            self.buy_symbols[order.symbol].inner_status = InnerOrderStatus.Checking
        elif order.side == OrderSide.OrderSide_Sell:
            self.sell_symbols[order.symbol].inner_status = InnerOrderStatus.Checking

    def __change_status_to_done(self, symbol):
        if symbol in self.buy_symbols:
            self.buy_symbols[symbol].inner_status = InnerOrderStatus.Done
            self.buy_done_symbols.add(symbol)
        elif symbol in self.sell_symbols:
            self.sell_symbols[symbol].inner_status = InnerOrderStatus.Done
            self.sell_done_symbols.add(symbol)

    def analyse_slide_price(self, exec_rpts: List[ExecRpt]):
        """
        return:
            sell_slide_rate, buy_slide_rate, sell_values, buy_values,
            sell_details, buy_details
        details: List[(symbol, slide_rate, amount)]，按成交额降序
        """
        sell_slide = []
        sell_value = []
        buy_slide = []
        buy_value = []
        # symbol -> [slide_i * amount_i, amount_i]
        sell_by_symbol: Dict[str, List[float]] = {}
        buy_by_symbol: Dict[str, List[float]] = {}
        write_info = []
        for exec_rpt in exec_rpts:
            if exec_rpt.side == OrderSide.OrderSide_Sell and exec_rpt.symbol in self.sell_symbols:
                od = self.sell_symbols[exec_rpt.symbol]
                price = od.open
                deal_p = exec_rpt.amount / exec_rpt.volume
                slide = deal_p / price - 1
                sell_slide.append(slide)
                sell_value.append(exec_rpt.amount)
                agg = sell_by_symbol.setdefault(exec_rpt.symbol, [0.0, 0.0])
                agg[0] += slide * exec_rpt.amount
                agg[1] += exec_rpt.amount
                logger.debug(f"sell symbol: {exec_rpt.symbol}, open: {price}, deal_p: {deal_p}, "
                             f"buy_value: {exec_rpt.amount}")
                write_info.append([exec_rpt.created_at, exec_rpt.symbol, "sell", od.open, od.pre_close, od.transaction_level,
                                   exec_rpt.amount, exec_rpt.volume, round(deal_p, 2)])
            if exec_rpt.side == OrderSide.OrderSide_Buy and exec_rpt.symbol in self.buy_symbols:
                od = self.buy_symbols[exec_rpt.symbol]
                price = od.open
                deal_p = exec_rpt.amount / exec_rpt.volume
                slide = deal_p / price - 1
                buy_slide.append(slide)
                buy_value.append(exec_rpt.amount)
                agg = buy_by_symbol.setdefault(exec_rpt.symbol, [0.0, 0.0])
                agg[0] += slide * exec_rpt.amount
                agg[1] += exec_rpt.amount
                logger.debug(f"buy symbol: {exec_rpt.symbol}, open: {price}, deal_p: {deal_p}, "
                             f"buy_value: {exec_rpt.amount}")
                write_info.append([exec_rpt.created_at, exec_rpt.symbol, "buy", od.open, od.pre_close, od.transaction_level,
                                   exec_rpt.amount, exec_rpt.volume, round(deal_p, 2)])
        self.saver.write_list(get_beijing_now(False), write_info, "trade_history.txt")
        if len(sell_slide) > 0:
            sell_slide_rate = sum([slide * sell_value[i] for i, slide in enumerate(sell_slide)]) / sum(sell_value)
            sell_values = sum(sell_value)
        else:
            sell_slide_rate = 0
            sell_values = 0
        if len(buy_slide) > 0:
            buy_slide_rate = sum([slide * buy_value[i] for i, slide in enumerate(buy_slide)]) / sum(buy_value)
            buy_values = sum(buy_value)
        else:
            buy_slide_rate = 0
            buy_values = 0

        def _to_details(by_symbol: Dict[str, List[float]]):
            details = [
                (symbol, weighted / amount, amount)
                for symbol, (weighted, amount) in by_symbol.items()
                if amount > 0
            ]
            details.sort(key=lambda x: x[2], reverse=True)
            return details

        sell_details = _to_details(sell_by_symbol)
        buy_details = _to_details(buy_by_symbol)
        return sell_slide_rate, buy_slide_rate, sell_values, buy_values, sell_details, buy_details

    def __order_is_not_done(self, symbol, side: OrderSide):
        if side == OrderSide.OrderSide_Buy:
            return symbol not in self.buy_done_symbols
        elif side == OrderSide.OrderSide_Sell:
            return symbol not in self.sell_done_symbols
        else:
            raise TypeError("Wrong Order Side !")