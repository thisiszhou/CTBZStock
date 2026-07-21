from schema.stock import InnerStockShoot, Order, OrderStatus, OrderSide, ExecRpt, ExecType
import gm.api as gmapi
from schema.stock import Position
from utils.timetool import date2str_sec, date2str
from loguru import logger
from typing import Any, Dict, List, Optional
import time

# 单次行情/基础面 API 超过该秒数打 warning，用于定位卡顿
_STOCK_SHOT_SLOW_SEC = 2.0


def get_symbol_stock_shot_v2(context, symbol: str, day) -> Optional[InnerStockShoot]:
    if not isinstance(day, str):
        day = date2str(day)
    data2_key = ["symbol", "is_st", "pre_close", "is_suspended", "upper_limit", "lower_limit"]
    t0 = time.time()
    costs: Dict[str, float] = {}

    # 进入时先打点：若卡死在某个子 API，日志会停在对应 begin 行
    logger.debug(f"stock_shot begin: symbol={symbol}, day={day}, step=current")
    t = time.time()
    d_1_ = gmapi.current(symbol)
    costs["current"] = time.time() - t

    logger.debug(f"stock_shot begin: symbol={symbol}, day={day}, step=daily_basic")
    t = time.time()
    d_2_ = gmapi.stk_get_daily_basic(symbol, fields="tclose,turnrate,ttl_shr,circ_shr", start_date=day, end_date=day)
    costs["daily_basic"] = time.time() - t

    logger.debug(f"stock_shot begin: symbol={symbol}, day={day}, step=valuation")
    t = time.time()
    d_3_ = gmapi.stk_get_daily_valuation_pt(symbols=symbol, fields='pe_lyr,pcf_lyr_oper')
    costs["valuation"] = time.time() - t

    if len(d_1_) == 0 or len(d_2_) == 0 or len(d_3_) == 0:
        total = time.time() - t0
        logger.warning(
            f"get_symbol_stock_shot empty: symbol={symbol}, day={day}, "
            f"len(current/basic/val)={len(d_1_)}/{len(d_2_)}/{len(d_3_)}, "
            f"costs={ {k: round(v, 3) for k, v in costs.items()} }, total={total:.3f}s"
        )
        return None
    d_1 = d_1_[0]
    d_2 = d_2_[0]
    d_3 = d_3_[0]
    data1: Dict[str, Any] = {
        "symbol": symbol,
        "open": d_1["open"],
        "close": d_1["price"] if day == date2str(context.now) else d_2["tclose"],
        "amount": d_1["cum_amount"],
        "volume": d_1["cum_volume"],
        "turn_rate": round(d_1["cum_volume"] * 100 / d_2["circ_shr"], 2),
        "pe_lyr": d_3["pe_lyr"],
        "pcf_lyr_oper": d_3["pcf_lyr_oper"]
    }

    logger.debug(f"stock_shot begin: symbol={symbol}, day={day}, step=history_symbol")
    t = time.time()
    data2_ = gmapi.get_history_symbol(
        symbol=symbol,
        start_date=day,
        end_date=day
    )
    costs["history_symbol"] = time.time() - t

    if len(data2_) == 0:
        total = time.time() - t0
        logger.warning(
            f"get_symbol_stock_shot history empty: symbol={symbol}, day={day}, "
            f"costs={ {k: round(v, 3) for k, v in costs.items()} }, total={total:.3f}s"
        )
        return None
    data2_row = data2_[0]
    total = time.time() - t0
    cost_str = {k: round(v, 3) for k, v in costs.items()}
    if total >= _STOCK_SHOT_SLOW_SEC:
        logger.warning(
            f"SLOW get_symbol_stock_shot: symbol={symbol}, day={day}, "
            f"total={total:.3f}s, costs={cost_str}"
        )
    else:
        logger.debug(
            f"get_symbol_stock_shot: symbol={symbol}, day={day}, "
            f"total={total:.3f}s, costs={cost_str}"
        )
    data2: Dict[str, Any] = {key: data2_row[key] for key in data2_key if key in data2_row}
    data2["price_max"] = data2["upper_limit"]
    data2["price_min"] = data2["lower_limit"]
    data1.update(data2)
    return InnerStockShoot(**data1)


def get_symbol_order(symbol: str):
    orders_o = gmapi.get_orders()
    try:
        orders = [Order(**x) for x in orders_o]
        # logger.debug(f"report orders: {orders}")
    except:
        logger.debug(f"origin orders: {orders_o}")
        raise
    orders = [x for x in orders if x.symbol == symbol]
    return [x.dict() for x in orders]


def get_cash():
    return int(gmapi.get_cash()['available'])


def get_all_positions_from_api():
    positions: Dict[str, Position] = {
        x['symbol']: Position(**x) for x in gmapi.get_position() if x['volume'] > 0
    }
    return positions


def get_exec_rpt_v2() -> List[ExecRpt]:
    exec_rpts: List[ExecRpt] = [ExecRpt(**x) for x in gmapi.get_execution_reports()]
    exec_rpts = [x for x in exec_rpts if x.exec_type == ExecType.ExecType_Trade]
    return exec_rpts


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