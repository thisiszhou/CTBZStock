from schema.stock import OrderSide, ExecRpt
from schema.inner_order import InnerOrder, InnerOrderStatus
from typing import Dict, Set, Optional, List
from loguru import logger


class OrderManager(object):
    def __init__(self):
        self.sell_symbols: Dict[str, InnerOrder] = dict()
        self.buy_symbols: Dict[str, InnerOrder] = dict()
        self.sell_done_symbols: Set = set()
        self.buy_done_symbols: Set = set()
        self.order_keys = set()

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

    def print_orders(self):
        logger.info(f"sell_order: ")
        for order in self.sell_symbols.values():
            logger.info(order)
        logger.info(f"buy_order: ")
        for order in self.buy_symbols.values():
            logger.info(order)

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

    def change_status_to_checking(self, order: InnerOrder):
        if order.side == OrderSide.OrderSide_Buy:
            self.buy_symbols[order.symbol].inner_status = InnerOrderStatus.Checking
        elif order.side == OrderSide.OrderSide_Sell:
            self.sell_symbols[order.symbol].inner_status = InnerOrderStatus.Checking

    def change_status_to_done(self, order: InnerOrder):
        if order.side == OrderSide.OrderSide_Buy:
            self.buy_symbols[order.symbol].inner_status = InnerOrderStatus.Done
            self.buy_done_symbols.add(order.symbol)
        elif order.side == OrderSide.OrderSide_Sell:
            self.sell_symbols[order.symbol].inner_status = InnerOrderStatus.Done
            self.sell_done_symbols.add(order.symbol)

    def analyse_slide_price(self, exec_rpts: List[ExecRpt]):
        sell_slide = []
        sell_value = []
        buy_slide = []
        buy_value = []
        for exec_rpt in exec_rpts:
            if exec_rpt.side == OrderSide.OrderSide_Sell and exec_rpt.symbol in self.sell_symbols:
                price = self.sell_symbols[exec_rpt.symbol].open
                deal_p = exec_rpt.amount / exec_rpt.volume
                sell_slide.append(deal_p / price - 1)
                sell_value.append(exec_rpt.amount)
            if exec_rpt.side == OrderSide.OrderSide_Buy and exec_rpt.symbol in self.buy_symbols:
                price = self.buy_symbols[exec_rpt.symbol].open
                deal_p = exec_rpt.amount / exec_rpt.volume
                buy_slide.append(deal_p / price - 1)
                buy_value.append(exec_rpt.amount)
        if len(sell_slide) > 0:
            sell_slide_rate = sum([slide * sell_value[i] for i, slide in enumerate(sell_slide)]) / sum(sell_value)
        else:
            sell_slide_rate = 0
        if len(buy_slide) > 0:
            buy_slide_rate = sum([slide * buy_value[i] for i, slide in enumerate(buy_slide)]) / sum(buy_value)
        else:
            buy_slide_rate = 0
        return sell_slide_rate, buy_slide_rate

    def __order_is_not_done(self, symbol, side: OrderSide):
        if side == OrderSide.OrderSide_Buy:
            return symbol not in self.buy_done_symbols
        elif side == OrderSide.OrderSide_Sell:
            return symbol not in self.sell_done_symbols
        else:
            raise TypeError("Wrong Order Side !")