from .sos_db import LocalDb, KEY_SYMBOL, KEY_DAY_DATA
from .schema import Stock
from typing import Dict, List, Optional, cast
from loguru import logger
import gm.api as gmapi
from utils.timetool import code2symbol, symbol2code, date2str_offline, date2str, rm_day_str_line, offline_str2date, \
    date_str2year
import traceback
from dataset.bkapi import get_next_trade_day


def _get_symbol_codes(db: LocalDb) -> Dict[str, str]:
    return cast(Dict[str, str], db.get(KEY_SYMBOL) or {})


def _get_stock(db: LocalDb, key: str) -> Optional[Stock]:
    return cast(Optional[Stock], db.get(key, Stock))


def _codes_to_symbols(codes: Dict[str, str]) -> List[str]:
    symbols: List[str] = []
    for code in codes:
        symbol = code2symbol(code)
        if symbol is not None:
            symbols.append(symbol)
    return symbols


def update_symbols(db: LocalDb):
    logger.info("update_symbols start!")
    all_stock = [x for x in gmapi.get_symbols(
        sec_type1=1010,
        sec_type2=101001,
        exchanges='SHSE,SZSE',
        skip_suspended=False,
        skip_st=False
    )]
    symbols = dict()
    for i, data in enumerate(all_stock):
        symbol = data["symbol"]
        sec_name = data["sec_name"]
        symbols[symbol2code(symbol)] = sec_name
    db.set(KEY_SYMBOL, symbols)
    logger.info("update_symbols done !")


def update_history_data(start_day, end_day, db: LocalDb):
    logger.info("update_history_data start!")
    codes: Dict[str, str] = _get_symbol_codes(db)
    for i, code in enumerate(codes):
        symbol = code2symbol(code)
        if symbol is None:
            continue
        history_data = gmapi.history(symbol=symbol,
                                     frequency='1d',
                                     start_time=start_day,
                                     end_time=end_day,
                                     fields='open, close, low, high, eob, cum_amount'
                                     # adjust=1
                                     )
        for data in history_data:
            date = data["eob"]
            day = date2str_offline(date)
            key = KEY_DAY_DATA.format(day, code)
            stock = _get_stock(db, key)
            if stock is None:
                stock = Stock(code=code, day=day)
            stock.open = data["open"]
            stock.close = data["close"]
            stock.low = data["low"]
            stock.high = data["high"]
            db.set(key, stock)
        if i % 10 == 0:
            logger.info(f"update_history_data: {i}/{len(codes)}")


def update_increase_info(start_day, end_day, db: LocalDb):
    logger.info("update_increase_info start!")
    codes: Dict[str, str] = _get_symbol_codes(db)
    for i, code in enumerate(codes):
        symbol = code2symbol(code)
        if symbol is None:
            continue
        history_data = gmapi.history(symbol=symbol,
                                     frequency='1d',
                                     start_time=start_day,
                                     end_time=end_day,
                                     fields='close,eob',
                                     adjust=1
                                     )
        day2close = dict()
        trade_day = []
        for data in history_data:
            day = date2str_offline(data["eob"])
            trade_day.append(day)
            day2close[day] = data["close"]
        trade_day.sort()
        for j, day in enumerate(trade_day[1:]):
            last_day = trade_day[j]
            last_close = day2close[last_day]
            # if gmapi.get_next_trading_date("SZSE", offline_str2date(last_day)) == date2str(offline_str2date(day)):
            #     last_close = day2close[last_day]
            # else:
            #     logger.warning(f'code: {code}, day : {gmapi.get_next_trading_date("SZSE", offline_str2date(last_day))} data not find')
            close = day2close[day]
            if close is None or last_close is None or last_close == 0:
                continue
            key = KEY_DAY_DATA.format(day, code)
            stock = _get_stock(db, key)
            if stock is not None and stock.open is not None and stock.close is not None:
                if stock.increase_rate is None:
                    open_price = stock.open
                    close_price = stock.close
                    increase_rate = (close - last_close) * 100 / last_close
                    stock.increase_rate = increase_rate
                    stock.open_increase_rate = (open_price / close_price * (increase_rate / 100 + 1) - 1) * 100
                    db.set(key, stock)
        if i % 10 == 0:
            logger.info(f"update_increase_info: {i}/{len(codes)}")


def update_increase_info_v2(start_day, end_day, db: LocalDb):
    logger.info("update_increase_info_v2 start!")
    list_ = gmapi.get_trading_dates_by_year("SHSE",
                                           int(date_str2year(start_day)),
                                           int(date_str2year(end_day)))["trade_date"]
    trading_days = [rm_day_str_line(x) for x in list_ if x != '']
    codes: Dict[str, str] = _get_symbol_codes(db)
    for i, code in enumerate(codes):
        symbol = code2symbol(code)
        if symbol is None:
            continue
        # logger.info(f"trading_days: {trading_days}")
        # raise
        for day in trading_days:
            key = KEY_DAY_DATA.format(day, code)
            stock = _get_stock(db, key)
            if stock is not None and stock.open is not None and stock.close is not None:
                pre_close = stock.pre_close
                if pre_close is None or pre_close == 0:
                    logger.warning(f"pre close invalid, stock: {stock}")
                    continue
                close_price = stock.close
                open_price = stock.open
                increase_rate = (close_price - pre_close) * 100 / pre_close
                open_increase_rate = (open_price - pre_close) * 100 / pre_close
                if stock.increase_rate is not None:
                    if abs(increase_rate - stock.increase_rate) >= 0.01:
                        logger.warning(f"code: {code}, day: {day}, stock: {stock}")
                        stock.increase_rate = round(increase_rate, 2)
                        stock.open_increase_rate = round(open_increase_rate, 2)
                        db.set(key, stock)
                else:
                    stock.increase_rate = round(increase_rate, 2)
                    stock.open_increase_rate = round(open_increase_rate, 2)
                    db.set(key, stock)
        if i % 10 == 0:
            logger.info(f"update_increase_info_v2: {i}/{len(codes)}")


def update_history_market_value_info_v2(start_day, end_day, db: LocalDb):
    logger.info("update_history_market_value_info_v2 start!")
    codes: Dict[str, str] = _get_symbol_codes(db)
    symbols = _codes_to_symbols(codes)
    current_day = start_day
    while current_day < end_day:
        fundamentals = gmapi.stk_get_daily_mktvalue_pt(symbols,
                                        fields='tot_mv,a_mv',
                                        trade_date=current_day)
        for info in fundamentals:
            code = symbol2code(info["symbol"])
            date = info["trade_date"]
            day = rm_day_str_line(date)
            key = KEY_DAY_DATA.format(day, code)
            stock = _get_stock(db, key)
            if stock is None:
                stock = Stock(code=code, day=day)
            if stock.open is None:
                continue
            stock.market_value = info["tot_mv"]
            stock.circulate_value = info["a_mv"]
            db.set(key, stock)
        current_day = gmapi.get_next_n_trading_dates("SZSE", current_day, n=1)[0]
        logger.info(f"update_history_market_value_info_v2: {current_day} finished!")


def update_history_market_value_info(start_day, end_day, db: LocalDb):
    logger.info("update_history_market_value_info start!")
    codes: Dict[str, str] = _get_symbol_codes(db)
    for i, code in enumerate(codes):
        symbol = code2symbol(code)
        if symbol is None:
            continue
        # 每日基本面
        fundamentals = gmapi.stk_get_daily_mktvalue(
            symbol,
            fields='tot_mv,a_mv',
            start_date=start_day,
            end_date=end_day,
        )
        for info in fundamentals:
            date = info["trade_date"]
            day = rm_day_str_line(date)
            key = KEY_DAY_DATA.format(day, code)
            stock = _get_stock(db, key)
            if stock is None:
                stock = Stock(code=code, day=day)
            if stock.open is None:
                continue
            stock.market_value = info["tot_mv"]
            stock.circulate_value = info["a_mv"]
            db.set(key, stock)
        if i % 10 == 0:
            logger.info(f"update_history_market_value_info: {i}/{len(codes)}")


def update_income_info(start_day, end_day, db:LocalDb):
    logger.info("update_income_info start!")
    codes: Dict[str, str] = _get_symbol_codes(db)
    for i, code in enumerate(codes):
        # if i <= 810:
        #     continue
        symbol = code2symbol(code)
        if symbol is None:
            continue
        # 每日数据
        stock_infos = gmapi.stk_get_fundamentals_income(
            symbol=symbol,
            start_date=start_day,
            end_date=end_day,
            rpt_type=12,
            data_type=101,
            fields="eps_base,inc_oper,net_prof"
        )
        stock_infos = [x for x in stock_infos if x["pub_date"] is not None and x["rpt_date"] is not None]
        stock_infos.sort(key=lambda x: x["rpt_date"])
        try:
            for stock_info in stock_infos:
                sd = rm_day_str_line(max(start_day, f"{stock_info['rpt_date'][:4]}-01-01"))
                ed = rm_day_str_line(min(end_day, stock_info["rpt_date"]))
                cd = sd
                while cd <= ed:
                    day = cd
                    key = KEY_DAY_DATA.format(day, code)
                    stock = _get_stock(db, key)
                    if stock is None:
                        cd = date2str_offline(get_next_trade_day(offline_str2date(cd)))
                        continue
                    stock.pub_date = stock_info["pub_date"]
                    stock.rpt_date = stock_info["rpt_date"]
                    stock.eps_base = stock_info["eps_base"]
                    stock.inc_oper = stock_info["inc_oper"]
                    stock.net_prof = stock_info["net_prof"]
                    db.set(key, stock)
                    cd = date2str_offline(get_next_trade_day(offline_str2date(cd)))
        except:
            logger.error(f"stock_infos: {stock_infos}")
            logger.error(traceback.format_exc())
            raise
        if i % 10 == 0:
            logger.info(f"update_income_info: {i}/{len(codes)}")


def update_income_info_batch(start_day, end_day, db:LocalDb):
    logger.info("update_income_info_batch start!")
    codes: Dict[str, str] = _get_symbol_codes(db)
    symbols = _codes_to_symbols(codes)
    stock_infos = gmapi.stk_get_fundamentals_income_pt(
        symbols=symbols,
        # date=end_day,
        rpt_type=12,
        data_type=101,
        fields="eps_base,inc_oper,net_prof"
    )
    stock_infos = [x for x in stock_infos if x["pub_date"] is not None and x["rpt_date"] is not None]
    for info in stock_infos:
        # if i <= 810:
        #     continue
        code = symbol2code(info["symbol"])
        sd = rm_day_str_line(max(start_day, f"{info['rpt_date'][:4]}-01-01"))
        ed = rm_day_str_line(min(end_day, info["rpt_date"]))
        cd = sd
        while cd <= ed:
            try:
                day = cd
                key = KEY_DAY_DATA.format(day, code)
                stock = _get_stock(db, key)
                if stock is None:
                    cd = date2str_offline(get_next_trade_day(offline_str2date(cd)))
                    continue
                if stock.pub_date is not None:
                    break
                stock.pub_date = info["pub_date"]
                stock.rpt_date = info["rpt_date"]
                stock.eps_base = info["eps_base"]
                stock.inc_oper = info["inc_oper"]
                stock.net_prof = info["net_prof"]
                db.set(key, stock)
                cd = date2str_offline(get_next_trade_day(offline_str2date(cd)))
            except:
                logger.error(f"stock_infos: {stock_infos}")
                logger.error(traceback.format_exc())
                raise
    logger.info(f"update_income_info_batch: {end_day} finished!")


_FINANCE_PRIME_FIELDS = "roe_weight_avg,inc_oper_yoy,net_prof_pcom_yoy,eps_yoy"


def _apply_finance_prime(stock: Stock, info: dict) -> None:
    stock.roe_weight_avg = info.get("roe_weight_avg")
    stock.inc_oper_yoy = info.get("inc_oper_yoy")
    stock.net_prof_pcom_yoy = info.get("net_prof_pcom_yoy")
    stock.eps_yoy = info.get("eps_yoy")
    if stock.pub_date is None:
        stock.pub_date = info["pub_date"]
    if stock.rpt_date is None:
        stock.rpt_date = info["rpt_date"]


def update_finance_prime(start_day, end_day, db: LocalDb):
    """按年报回填财务主要指标：加权ROE、营收/归母净利/EPS同比。"""
    logger.info("update_finance_prime start!")
    codes: Dict[str, str] = _get_symbol_codes(db)
    for i, code in enumerate(codes):
        symbol = code2symbol(code)
        if symbol is None:
            continue
        stock_infos = gmapi.stk_get_finance_prime(
            symbol=symbol,
            start_date=start_day,
            end_date=end_day,
            rpt_type=12,
            data_type=101,
            fields=_FINANCE_PRIME_FIELDS,
        )
        stock_infos = [x for x in stock_infos if x["pub_date"] is not None and x["rpt_date"] is not None]
        stock_infos.sort(key=lambda x: x["rpt_date"])
        try:
            for stock_info in stock_infos:
                sd = rm_day_str_line(max(start_day, f"{stock_info['rpt_date'][:4]}-01-01"))
                ed = rm_day_str_line(min(end_day, stock_info["rpt_date"]))
                cd = sd
                while cd <= ed:
                    day = cd
                    key = KEY_DAY_DATA.format(day, code)
                    stock = _get_stock(db, key)
                    if stock is None:
                        cd = date2str_offline(get_next_trade_day(offline_str2date(cd)))
                        continue
                    _apply_finance_prime(stock, stock_info)
                    db.set(key, stock)
                    cd = date2str_offline(get_next_trade_day(offline_str2date(cd)))
        except:
            logger.error(f"stock_infos: {stock_infos}")
            logger.error(traceback.format_exc())
            raise
        if i % 10 == 0:
            logger.info(f"update_finance_prime: {i}/{len(codes)}")


def update_finance_prime_batch(start_day, end_day, db: LocalDb):
    """截面拉取最新年报财务主要指标并回填。"""
    logger.info("update_finance_prime_batch start!")
    codes: Dict[str, str] = _get_symbol_codes(db)
    symbols = _codes_to_symbols(codes)
    stock_infos = gmapi.stk_get_finance_prime_pt(
        symbols=symbols,
        rpt_type=12,
        data_type=101,
        fields=_FINANCE_PRIME_FIELDS,
    )
    stock_infos = [x for x in stock_infos if x["pub_date"] is not None and x["rpt_date"] is not None]
    for info in stock_infos:
        code = symbol2code(info["symbol"])
        sd = rm_day_str_line(max(start_day, f"{info['rpt_date'][:4]}-01-01"))
        ed = rm_day_str_line(min(end_day, info["rpt_date"]))
        cd = sd
        while cd <= ed:
            try:
                day = cd
                key = KEY_DAY_DATA.format(day, code)
                stock = _get_stock(db, key)
                if stock is None:
                    cd = date2str_offline(get_next_trade_day(offline_str2date(cd)))
                    continue
                if stock.roe_weight_avg is not None:
                    break
                _apply_finance_prime(stock, info)
                db.set(key, stock)
                cd = date2str_offline(get_next_trade_day(offline_str2date(cd)))
            except:
                logger.error(f"stock_infos: {stock_infos}")
                logger.error(traceback.format_exc())
                raise
    logger.info(f"update_finance_prime_batch: {end_day} finished!")


def update_history_ttm(start_day, end_day, db: LocalDb):
    logger.info("update_history_ttm start!")
    codes: Dict[str, str] = _get_symbol_codes(db)
    for i, code in enumerate(codes):
        symbol = code2symbol(code)
        if symbol is None:
            continue
        # 每日数据
        stock_infos = gmapi.stk_get_daily_valuation(
            symbol=symbol,
            start_date=start_day,
            end_date=end_day,
            fields="pe_ttm,pe_lyr,pb_lyr,pe_mrq,pcf_lyr_oper,dy_ttm,dy_lfy"
        )
        for data in stock_infos:
            date = data["trade_date"]
            day = rm_day_str_line(date)
            key = KEY_DAY_DATA.format(day, code)
            stock = _get_stock(db, key)
            if stock is None:
                continue
            stock.pe_ttm = data["pe_ttm"]
            stock.pe_lyr = data["pe_lyr"]
            stock.pb_lyr = data["pb_lyr"]
            stock.pcf_lyr_oper = data["pcf_lyr_oper"]
            stock.dy_ttm = data["dy_ttm"]
            stock.dy_lfy = data["dy_lfy"]
            db.set(key, stock)
        if i % 10 == 0:
            logger.info(f"update_history_ttm: {i}/{len(codes)}")


def update_history_ttm_v2(start_day, end_day, db: LocalDb):
    logger.info("update_history_ttm_v2 start!")
    codes: Dict[str, str] = _get_symbol_codes(db)
    symbols = _codes_to_symbols(codes)
    current_day = start_day
    while current_day < end_day:
        stock_infos = gmapi.stk_get_daily_valuation_pt(
            symbols=symbols,
            fields="pe_ttm,pe_lyr,pb_lyr,pe_mrq,pcf_lyr_oper,dy_ttm,dy_lfy",
            trade_date=current_day
        )
        for data in stock_infos:
            date = data["trade_date"]
            code = symbol2code(data["symbol"])
            day = rm_day_str_line(date)
            key = KEY_DAY_DATA.format(day, code)
            stock = _get_stock(db, key)
            if stock is None:
                continue
            stock.pe_ttm = data["pe_ttm"]
            stock.pe_lyr = data["pe_lyr"]
            stock.pb_lyr = data["pb_lyr"]
            stock.pcf_lyr_oper = data["pcf_lyr_oper"]
            stock.dy_ttm = data["dy_ttm"]
            stock.dy_lfy = data["dy_lfy"]
            db.set(key, stock)
        current_day = gmapi.get_next_n_trading_dates("SZSE", current_day, n=1)[0]
        logger.info(f"update_history_ttm_v2: {current_day}")


def update_history_suspend_and_st_info(start_day, end_day, db: LocalDb):
    # update: market_value, is_st, is_suspended
    logger.info("update_history_suspend_and_st_info start!")
    codes: Dict[str, str] = _get_symbol_codes(db)
    fail = 0
    # logger.info(f"symbols: {symbols}")
    for i, code in enumerate(codes):
        symbol = code2symbol(code)
        if symbol is None:
            continue
        # 每日数据
        stock_infos = gmapi.get_history_symbol(
            symbol=symbol,
            start_date=start_day,
            end_date=end_day,
            # fields="symbol,trade_date,is_suspended,is_st,listed_date,"
            #          "delisted_date,pre_close,upper_limit,lower_limit,turn_rate"
        )
        for stock_info in stock_infos:
            try:
                date = stock_info["trade_date"]
                day = date2str_offline(date)
                key = KEY_DAY_DATA.format(day, code)
                stock = _get_stock(db, key)
                if stock is None:
                    stock = Stock(code=code, day=day)
                stock.is_st = stock_info["is_st"]
                stock.is_suspended = stock_info["is_suspended"]
                stock.listed_date = date2str_offline(stock_info["listed_date"])
                stock.delisted_date = date2str_offline(stock_info["delisted_date"])
                if stock_info["delisting_begin_date"]:
                    stock.delisting_begin_date = date2str_offline(stock_info["delisting_begin_date"])
                stock.pre_close = stock_info["pre_close"]
                stock.upper_limit = stock_info["upper_limit"]
                stock.lower_limit = stock_info["lower_limit"]
                stock.turn_rate = stock_info["turn_rate"]
                db.set(key, stock)
            except:
                logger.error(f"stock: {stock_info}")
                logger.error(traceback.format_exc())
                raise ValueError
        if i % 10 == 0:
            logger.info(f"update_history_suspend_and_st_info: {i}/{len(codes)}")

