from dataset.stock_db import StockDB
from dataset.sos_db import LocalDb
from dataset.bkapi import get_last_trade_day, trade_days_list, get_next_trade_day, is_today_first_trade_day_of_year, \
    is_today_last_trade_day_of_year
from dataset.schema import Stock
from system.schema import PositionStock, SellOrder
from dataset.bkutils import str2date, date2str, date2year
from datetime import date
from typing import Any, Dict, List, Optional, cast
from collections import defaultdict
from loguru import logger
import numpy as np
import sys
import pickle
from system.fees import stamp_tax, service_charge, slide_rate, high_discount

sys.setrecursionlimit(4000)


class Simulation(object):
    def __init__(self,
                 *,
                 data_db_folder="buffer/db",
                 index_db_folder="buffer/index",
                 start_money=150000,
                 start_year=None,
                 end_year=None,
                 db=None,
                 index_db=None):
        # load data
        if db is None:
            self.data_db = LocalDb(data_db_folder, start_year=start_year, end_year=end_year)
        else:
            self.data_db = db
        if index_db is not None:
            self.stock_db = StockDB(self.data_db, index_db=index_db)
        elif index_db_folder is not None:
            index_db = LocalDb(index_db_folder, start_year=start_year, end_year=end_year)
            self.stock_db = StockDB(self.data_db, index_db=index_db)
        else:
            self.stock_db = StockDB(self.data_db)
        self.__position: List[PositionStock] = []
        self.__cash = start_money
        self.start_money = start_money
        self.trade_days_list: Optional[List[date]] = None
        self.debug_info = None
        self.analyse_data: Optional[Dict[date, Any]] = None
        self.values = None
        self.sell_orders = defaultdict(list)
        self.buy_orders = defaultdict(list)
        self.holding_orders_detail = []
        self.total_fee = 0
        self.sharpe_ratio = None

    def decide(self, day: date, time_node):
        pass

    def transaction(self, day: date, time_node):
        pass

    def day_t(self, day: date):
        pass

    def buy(self, *, day, cash, code, time_node, buy_price=None):
        assert time_node in ["open", "close"]
        # logger.debug(
        #     f"cash: {cash}, self.__cash: {self.__cash}, price: {self.stock_db.get_price(code, day, time_node)}")
        if cash > self.__cash:
            logger.debug(f"no enough cash !")
            return False
        ceiling = self.stock_db.if_price_boundary(code, day, time_node, "high")
        if ceiling:
            logger.debug(f"code celling ! {code}, {day}, {time_node}, high")
            return False
        price, _ = self.stock_db.get_price(code, day, time_node)
        stock_info = self.stock_db.get_stock_info(code, day)
        if stock_info is None or stock_info.is_suspended:
            logger.debug(f"code suspended !")
            return False
        if not price:
            logger.debug(f"no price !")
            return False
        if buy_price is not None:
            price = buy_price
        price *= 1 + slide_rate
        share = int(cash / price / 100)
        if share <= 0:
            logger.debug(f"not enough share: price: {price}, cash: {cash}")
            return False
        spend = share * 100 * price
        server_c = spend * service_charge
        server_c = 5 if server_c < 5 else server_c
        spend += server_c
        while cash - spend < 0:
            share -= 1
            if share <= 0:
                return False
            spend = share * 100 * price
            server_c = spend * service_charge
            server_c = 5 if server_c < 5 else server_c
            spend += server_c
        assert cash - spend >= 0, f"day: {day}, cash_left:{cash - spend}, per_cash:{cash}, code:{code}, price: {price}" \
                                  f"spend: {spend}, share: {share}, server_c: {server_c}"
        self.total_fee += server_c
        self.__position.append(PositionStock(code=code, share=share, buy_day=day, vwap=round(spend / share / 100, 2)))
        self.buy_orders[code].append(
            PositionStock(code=code, share=share, buy_day=day, vwap=round(spend / share / 100, 2))
        )
        self.__cash -= spend
        return True

    def cash(self):
        return self.__cash

    def could_sell_share(self, day, code):
        self.__position.sort(key=lambda x: x.buy_day)
        could_sell_share = 0
        for position in self.__position:
            if (
                    position.code == code
                    and position.buy_day != day
            ):
                could_sell_share += position.share
        return could_sell_share

    def get_holding_position_share(self):
        # return: Dict[code, share] share 单位是100股
        hold_position = defaultdict(int)
        for position in self.__position:
            if position.share > 0:
                hold_position[position.code] += position.share
        self.__position = [x for x in self.__position if x.share > 0]
        return hold_position

    def sell(self, *, day, code, time_node, share=None, sell_price=None):
        assert time_node in ["open", "close"]
        # check sell legal
        could_sell_share = self.could_sell_share(day, code)
        if share is None or share > could_sell_share:
            share = could_sell_share
        if share == 0:
            return False, 0
        stock_info = self.stock_db.get_stock_info(code, day)
        if stock_info is None or stock_info.is_suspended:
            return False, 0
        if self.stock_db.if_price_boundary(code, day, time_node, "low"):
            return False, 0
        price, inc = self.stock_db.get_price(code, day, time_node)
        if not price:
            return False, 0
        if sell_price is not None:
            price = sell_price
        # sell legal
        will_sell_share = share
        for position in self.__position:
            if position.code == code:
                if will_sell_share > position.share:
                    will_sell_share -= position.share
                    position.share = 0
                else:
                    position.share -= will_sell_share
                    will_sell_share = 0
            if will_sell_share == 0:
                break
        self.__position = [x for x in self.__position if x.share > 0]
        price *= (1 - slide_rate)
        if inc is None:
            print(f"inc is None: {day}, {code}")
        elif sell_price is None and inc > 4:
            price = price * (100 + inc * high_discount) / (100 + inc)
        cost = price * share * 100
        tax = cost * service_charge
        if tax < 5:
            tax = 5
        tax += cost * stamp_tax
        self.total_fee += tax
        # logger.debug(f"in sell: {self.__cash}")
        sell_money = cost - tax
        self.__cash += cost - tax
        hoding = self.get_holding_position_share()
        self.sell_orders[code].append(SellOrder(code=code, sell_value=sell_money))
        if hoding[code] == 0:
            self.analyse_order(day, code, self.sell_orders[code], self.buy_orders[code])
            self.sell_orders[code] = []
            self.buy_orders[code] = []
        # logger.debug(f"in sell after: {self.__cash}")

        return True, sell_money

    def get_holding_start_day(self, code):
        if code in self.buy_orders:
            return min([x.buy_day for x in self.buy_orders[code]])
        else:
            return None

    def analyse_order(self, day, code, sell_orders, buy_orders):
        holding_day = (day - min([x.buy_day for x in buy_orders])).days
        profit = sum([x.sell_value for x in sell_orders]) / sum([x.vwap * x.share * 100 for x in buy_orders]) - 1
        self.holding_orders_detail.append((code, holding_day, profit, min([x.buy_day for x in buy_orders]), day))

    def get_asset(self, day, time_node, show_detail=False):
        asset = self.__cash + sum(self.get_per_position_value(day, time_node).values())
        if show_detail:
            logger.info(f"cash: {self.__cash}")
            logger.info(f"total asset: {asset}")
        return asset

    def get_per_position_value(self, day, time_node):
        holding_position = self.get_holding_position_share()
        output = dict()
        for code in holding_position:
            output[code] = holding_position[code] * 100 * self.get_position_price(
                day=day, code=code, time_node=time_node
            )
        return output

    def get_cash(self):
        return self.__cash

    def get_position_price(self, *, day, code, time_node):
        price, _ = self.stock_db.get_price(code, day, time_node)
        if price is not None and not np.isnan(price):
            return price
        else:
            return self.get_position_price(
                day=get_last_trade_day(day), code=code, time_node='close'
            )

    def reset(self):
        self.__position = []
        self.__cash = self.start_money
        self.total_fee = 0

    def rebase(self, last_day, day):
        for position in self.__position:
            code = position.code
            today_stock = self.stock_db.get_stock_info(code, day)
            if today_stock is None or today_stock.pre_close is None:
                continue
            last_day_stock = self.stock_db.get_stock_info(code, last_day)
            if last_day_stock is None:
                continue
            if last_day_stock.close is None and last_day_stock.pre_close is None:
                continue
            last_p = last_day_stock.close if last_day_stock.close is not None else last_day_stock.pre_close
            today_p = today_stock.pre_close
            if last_p is None or today_p is None:
                continue
            if today_p == last_p:
                continue
            elif today_p < last_p:
                # logger.info(f"REBASE! code: {code}, day: {day}, share: {position.share}")
                # raise
                self.__cash += position.share * (last_p - today_p) * 100
            else:
                # b_share = position.share
                position.share = int(position.share * last_p / today_p)
                # logger.info(f"REBASE! code: {code}, day: {day}, share before: {b_share}, a: {position.share}")
                # raise

    def first_sell_then_buy_t(self, *, code, day, share, sell_price, buy_price):
        stock_info = self.stock_db.get_stock_info(code, day)
        if stock_info is None or stock_info.high is None or stock_info.low is None:
            return
        if stock_info.high < sell_price:
            return
        status, cash = self.sell(day=day, code=code, time_node="open", share=share, sell_price=sell_price)
        logger.debug(f"in t: sell done , cash {cash}")
        if not status:
            return
        if stock_info.low > buy_price:
            status = self.buy(day=day, cash=cash, code=code, time_node="close")
            logger.debug(f"in t: buy done , t not done, status: {status}")
        else:
            status = self.buy(day=day, cash=cash, code=code, time_node="open", buy_price=buy_price)
            logger.debug(f"in t: t done, status: {status}")

    def day_by_day_show(self, day, time_node_type, start_day):
        if time_node_type < 3:
            time_node = "open"
            if time_node_type == 1:
                time_node_2 = "before"
            else:
                time_node_2 = "after"
        else:
            time_node = "close"
            time_node_2 = ""

        asset = self.get_asset(day, time_node=time_node)
        cash = self.get_cash()
        print(f"----- day: {day}, {time_node} {time_node_2} transaction, asset: {int(asset)}, cash: {int(cash)}, "
              f"inc: {round((asset / self.start_money - 1) * 100, 2)}%, "
              f"shipping: {round((1 - cash / asset) * 100)}% -----")
        holdings = self.get_holding_position_share()
        keys = list(holdings.keys())
        keys.sort()
        if len(keys) > 0:
            for code in keys:
                st = self.stock_db.get_stock_info(code, day)
                if st is None:
                    continue
                name = self.stock_db.get_name(code)
                if time_node == "open":
                    if st.open is None:
                        pre_close = st.pre_close or 0.0
                        print(f"{name}, price: {pre_close}, 停牌, "
                              f"value: {holdings[code] * 100 * pre_close}")
                    else:
                        print(f"{name}, price: {st.open}, inc: {st.open_increase_rate}, "
                              f"value: {holdings[code] * 100 * st.open}")
                else:
                    if st.close is None:
                        pre_close = st.pre_close or 0.0
                        print(f"{name}, price: {pre_close}, 停牌, "
                              f"value: {holdings[code] * 100 * pre_close}")
                    else:
                        print(f"{name}, price: {st.close}, inc: {st.increase_rate}, "
                              f"value: {holdings[code] * 100 * st.close}")
        else:
            print("Today has no position.")
        index_400 = self.stock_db.get_index_info("last400", day)
        index_300 = self.stock_db.get_index_info("top300", day)
        if index_400 is None or index_300 is None:
            input()
            return
        last_trade_day = get_last_trade_day(str2date(start_day))
        index_400_prev = self.stock_db.get_index_info("last400", last_trade_day)
        index_300_prev = self.stock_db.get_index_info("top300", last_trade_day)
        if index_400_prev is None or index_300_prev is None:
            input()
            return
        if time_node == "open":
            if index_400.open is None or index_300.open is None or index_400_prev.close is None or index_300_prev.close is None:
                input()
                return
            index_400_diff = index_400.open / index_400_prev.close - 1
            index_300_diff = index_300.open / index_300_prev.close - 1
            index_400_today_diff = index_400.open_increase_rate or 0.0
            index_300_today_diff = index_300.open_increase_rate or 0.0
        else:
            if index_400.close is None or index_300.close is None or index_400_prev.close is None or index_300_prev.close is None:
                input()
                return
            index_400_diff = index_400.close / index_400_prev.close - 1
            index_300_diff = index_300.close / index_300_prev.close - 1
            index_400_today_diff = index_400.increase_rate or 0.0
            index_300_today_diff = index_300.increase_rate or 0.0
        print(f"\nIndex info: "
              f"\nlast400 {time_node} inc: {round(index_400_today_diff, 2)}%, "
              f"total inc: {round(index_400_diff * 100, 2)}%"
              f"\ntop300 {time_node} inc: {round(index_300_today_diff, 2)}%, "
              f"total inc: {round(index_300_diff * 100, 2)}%")
        input()

    def _format_daily_brief(self, day: date, total_asset: float) -> str:
        """简洁日志：日期 + 总资产 + 持仓/现金比例。"""
        cash = self.__cash
        if total_asset > 0:
            position_pct = (total_asset - cash) / total_asset * 100
            cash_pct = cash / total_asset * 100
        else:
            position_pct = cash_pct = 0.0
        return f"{day} asset={total_asset:.2f} position={position_pct:.2f}% cash={cash_pct:.2f}%"

    def _format_daily_positions(self, day: date, total_asset: float, time_node: str = "close") -> str:
        """全打日志：简洁行 + 个股持仓权重明细。"""
        lines = [
            self._format_daily_brief(day, total_asset),
            "  holdings:",
        ]
        position_values = self.get_per_position_value(day, time_node)
        holdings = []
        for code, value in position_values.items():
            if value is None or np.isnan(value) or value <= 0:
                continue
            weight = value / total_asset * 100 if total_asset > 0 else 0.0
            name = self.stock_db.symbols.get(code, code)
            holdings.append((weight, name))
        holdings.sort(key=lambda x: x[0], reverse=True)
        if not holdings:
            lines.append("    (empty)")
        else:
            chunk_size = 5
            for i in range(0, len(holdings), chunk_size):
                chunk = holdings[i:i + chunk_size]
                parts = [f"{name} {weight:.2f}%" for weight, name in chunk]
                lines.append("    " + "  |  ".join(parts))
        return "\n".join(lines)

    def run(
        self,
        start_day,
        end_day,
        show_detail=True,
        show_brief=False,
        day_by_day=False,
        check_start_day=None,
        check_end_day=None,
    ):
        """
        show_detail: 全打，每日总资产/仓位比例 + 个股持仓明细（优先于 show_brief）
        show_brief:  简洁，仅每日总资产与持仓/现金比例
        """
        self.reset()
        self.trade_days_list = [x for x in trade_days_list if str2date(start_day) <= x <= str2date(end_day)]
        assert self.trade_days_list is not None
        bk_ret = dict()
        last_day_asset = self.get_asset(self.trade_days_list[0], time_node="open")
        if check_start_day is not None:
            csd = str2date(check_start_day)
            ced = str2date(check_end_day)
        for i, day in enumerate(self.trade_days_list):
            if i != 0:
                self.rebase(self.trade_days_list[i - 1], day)
            if day_by_day and csd <= day <= ced:
                self.day_by_day_show(day, 1, start_day)
                hd1 = set(self.get_holding_position_share().keys())
            self.transaction(day, time_node="open")
            if day_by_day and csd <= day <= ced:
                hd2 = set(self.get_holding_position_share().keys())
                if hd1 != hd2:
                    self.day_by_day_show(day, 2, start_day)
                self.day_by_day_show(day, 3, start_day)
            self.day_t(day)

            # self.transaction(day, time_node="close")
            self.transaction(day, time_node="close")
            close_asset = self.get_asset(day, time_node='close')

            bk_ret[day] = close_asset, close_asset - last_day_asset, self.get_holding_position_share(), \
                          self.cash() / close_asset, self.debug_info
            self.callback(day, close_asset - last_day_asset)
            if show_detail:
                logger.info(self._format_daily_positions(day, close_asset, time_node="close"))
            elif show_brief:
                logger.info(self._format_daily_brief(day, close_asset))
            last_day_asset = close_asset
        self.log()
        self.write_to_csv(bk_ret, "date,asset,cash_rate,debug_info", "ret.csv")
        close_asset = self.get_asset(self.trade_days_list[-1], time_node='close')
        if show_detail:
            logger.info(
                f"bktesting, end date: {self.trade_days_list[-1]}, position: {self.get_holding_position_share()}, "
                f"self.cash: {round(self.__cash, 2)}, asset: {round(close_asset, 2)}")
        elif show_brief:
            logger.info(self._format_daily_brief(self.trade_days_list[-1], close_asset))
        profits, max_retrace, retrace_list, last_retrace, year_retraces = self.metric(bk_ret)
        year = int(end_day[:4]) - int(start_day[:4]) + 1
        nianhua = profits ** (1 / year) - 1
        sharpe = self.calc_sharpe(bk_ret)
        self.sharpe_ratio = sharpe
        if max_retrace > 0:
            target = round(nianhua / max_retrace, 2)
        else:
            target = 0
        year_retraces = [x for x in year_retraces if x[1] < 0]
        if len(year_retraces) > 0:
            year_max_retrace = abs(min([x[1] for x in year_retraces]))
        else:
            year_max_retrace = 0
        if year_max_retrace > 0:
            year_target = round(nianhua / year_max_retrace, 2)
        else:
            year_target = 0
        profits = f"{round(nianhua * 100, 2)}%"
        max_retrace = f"{round(max_retrace * 100, 2)}%"
        year_max_retrace = f"{round(year_max_retrace * 100, 2)}%"
        last_retrace = f"{round(last_retrace * 100, 2)}%"
        sharpe_str = f"{sharpe:.2f}" if sharpe is not None else "N/A"
        total_fee = round(self.total_fee, 2)
        fee_ratio = round(self.total_fee / self.start_money * 100, 2)
        print(f"----- {start_day} ~ {end_day} ------")
        print(f"metric profits: {profits}, max_retrace: {max_retrace}, Calmar: {target}, "
              f"sharpe: {sharpe_str}, "
              f"total_fee: {total_fee}, fee_ratio: {fee_ratio}%")
        print(f"total retrace >= 15% num: {len(retrace_list)}, retrace detail: ")
        for i, data in enumerate(retrace_list):
            max_retrace_tmp, max_retrace_d, retrace_day, r_start_d, r_end_d = data
            print(f"No.{i + 1}, retrace: {max_retrace_tmp * 100}%, retrace start day: {r_start_d},"
                  f" max retrace day: {max_retrace_d}, end day: {r_end_d}, total retrace day: {retrace_day}")
        print(f"--------- max loss of one year (ref) year_mr={year_max_retrace}, year_Calmar={year_target} -------------")
        for year, data in year_retraces:
            print(f"year: {year}, loss: {round(abs(data) * 100, 2)}%")
        return profits, max_retrace, target, last_retrace, year_max_retrace, sharpe_str

    def log(self):
        pass

    def calc_sharpe(self, bk_ret, risk_free_rate: float = 0.0, trading_days_per_year: int = 252):
        """年化夏普：基于日收益，短周期与长周期口径一致。

        sharpe = mean(r - rf_daily) / std(r - rf_daily) * sqrt(252)

        用日频统计再按交易日年化，不依赖日历年数，因此几个月回测与 20 年回测可直接比较。
        risk_free_rate 为年化无风险利率（默认 0）。
        """
        assert self.trade_days_list is not None
        if len(self.trade_days_list) < 3:
            return None
        assets = np.array([bk_ret[day][0] for day in self.trade_days_list], dtype=float)
        prev = assets[:-1]
        curr = assets[1:]
        mask = np.isfinite(prev) & np.isfinite(curr) & (prev > 0)
        if mask.sum() < 2:
            return None
        daily_rets = curr[mask] / prev[mask] - 1.0
        rf_daily = risk_free_rate / trading_days_per_year
        excess = daily_rets - rf_daily
        std = float(np.std(excess, ddof=1))
        if std < 1e-12:
            return None
        return float(np.mean(excess) / std * np.sqrt(trading_days_per_year))

    def metric(self, bk_ret, threshold=15):
        assert self.trade_days_list is not None
        max_point = self.start_money
        max_retrace = 0
        # 收集大于阈值的回撤
        retrace_list = []
        all_retrace_list = []
        max_retrace_tmp = 0
        max_retrace_day = None
        retrace_day = 0
        retrace_start_day = self.trade_days_list[0]
        last_retrace = 0
        year_max_retraces = []
        base_money = None
        year_max_retrace = 0
        for i, day in enumerate(self.trade_days_list):
            close_asset = bk_ret[day][0]
            if is_today_first_trade_day_of_year(day):
                base_money = close_asset
            if base_money is not None:
                year_max_retrace = min(close_asset / base_money - 1, year_max_retrace)
            if is_today_last_trade_day_of_year(day):
                year_max_retraces.append([date2year(day), year_max_retrace])
                year_max_retrace = 0
            if max_point is None:
                max_point = close_asset
            if close_asset >= max_point:
                max_point = close_asset
                if max_retrace_tmp * 100 >= threshold:
                    retrace_list.append((max_retrace_tmp, max_retrace_day, retrace_day, retrace_start_day, day))
                if max_retrace_tmp * 100 >= 3:
                    all_retrace_list.append(round(max_retrace_tmp * 100, 2))
                max_retrace_tmp = 0
                max_retrace_day = None
                retrace_day = 0
                retrace_start_day = day
            if 1 - close_asset / max_point > max_retrace:
                max_retrace = 1 - close_asset / max_point
            if 1 - close_asset / max_point > max_retrace_tmp:
                max_retrace_tmp = 1 - close_asset / max_point
                max_retrace_day = day
            retrace_day += 1
            last_retrace = 1 - close_asset / max_point
        if max_retrace_tmp * 100 >= threshold:
            retrace_list.append((max_retrace_tmp, max_retrace_day, retrace_day, retrace_start_day,
                                 self.trade_days_list[-1]))
        if max_retrace_tmp * 100 >= 3:
            all_retrace_list.append(round(max_retrace_tmp * 100, 2))
        last_retrace = round(last_retrace, 3)
        profits = round(bk_ret[self.trade_days_list[-1]][0] / self.start_money, 3)
        max_retrace = round(max_retrace, 3)
        if len(year_max_retraces) == 0 and year_max_retrace < 0:
            year_max_retraces.append(["current", year_max_retrace])
        return profits, max_retrace, retrace_list, last_retrace, year_max_retraces

    def save_pickle(self, obj):
        with open("tmp.pkl", "wb") as f:
            pickle.dump(obj, f)

    def load_pickle(self, file="tmp.pkl"):
        with open(file, "rb") as f:
            return pickle.load(f)

    # def write_to_csv(self, bk_ret, keys, file_name):
    #     with open(file_name, "w") as f:
    #         f.write(f"{keys}\n")
    #         for day in self.trade_days_list[1:]:
    #             f.write(str(day) + "," + str(bk_ret[day][0] / self.start_money) + "," + str(bk_ret[day][-2]) + "," +
    #                     str(bk_ret[day][-1]) + "\n")

    def write_to_csv(self, bk_ret, keys, file_name):
        assert self.trade_days_list is not None
        # with open("ret.csv", "w") as f:
        with open(file_name, "w") as f:
            # f.write("date,asset,cash_rate,debug_info\n")
            f.write(f"{keys}\n")
            for day in self.trade_days_list[1:]:
                if self.analyse_data is not None:
                    if self.analyse_data.get(day, None) is None:
                        info = ""
                    elif isinstance(self.analyse_data[day], tuple):
                        info = ",".join([str(x) for x in self.analyse_data[day]])
                    elif isinstance(self.analyse_data[day], list):
                        info = ",".join([str(x) for x in self.analyse_data[day]])
                    else:
                        info = str(self.analyse_data[day])
                else:
                    info = ""
                f.write(str(day) + "," + str(bk_ret[day][0] / self.start_money) + "," + info + "\n")

    def callback(self, *args, **kwargs):
        pass

    def load_middle_income(self, *args, **kwargs):
        pass

    def save_middle_income(self, *args, **kwargs):
        pass