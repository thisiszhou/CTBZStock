import os
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import gm.api as gmapi
from loguru import logger

from config import cons
from schema.inner_order import TransactionLevel
from schema.stock import Position, ExecRpt, OrderSide
from third_part.feishu_service import send_group_msg
from utils.api_func import get_exec_rpt_v2
from utils.context_func import get_all_positions, get_context_cash, get_all_market_value
from utils.timetool import date2str

_LEVEL_NAME = {int(x): x.name for x in TransactionLevel}
_DATA_DIR = "data"
_ORDER_PLAN_FILE = "order_plan.txt"
_TRADE_HISTORY_FILE = "trade_history.txt"


def _fmt_slide_pct(rate: float) -> str:
    pct = round(rate * 100, 2)
    if abs(pct) < 1e-9:
        return "0%"
    return f"{pct:+.2f}%"


def _get_symbol_names(symbols: List[str]) -> Dict[str, str]:
    if not symbols:
        return {}
    try:
        rows = gmapi.get_symbols(
            symbols=symbols,
            exchanges="SHSE, SZSE",
            sec_type1=1010,
            sec_type2=101001,
            skip_st=False,
            skip_suspended=False,
        )
    except Exception as e:
        logger.warning(f"get_symbols for names failed: {e}")
        return {}
    return {row["symbol"]: (row.get("sec_name") or row["symbol"]) for row in rows}


def _fmt_slide_detail_block(
    side_cn: str,
    details: List[Tuple[str, float, float]],
    name_map: Dict[str, str],
) -> str:
    """滑点明细：一行一只，名称全角对齐。"""
    if not details:
        return ""
    names = [name_map.get(symbol, symbol) for symbol, _, _ in details]
    name_w = max(len(n) for n in names)
    lines = [f"{side_cn}："]
    for (symbol, slide, amount), name in zip(details, names):
        pad = "\u3000" * (name_w - len(name))
        lines.append(f"{name}{pad}  {_fmt_slide_pct(slide)}/{int(round(amount))}")
    return "\n".join(lines)


def _fmt_holdings_block(items: List[Tuple[str, float]]) -> str:
    """持仓逐行：名称左对齐（全角空格）、占比右对齐。飞书非等宽，多列会乱。"""
    if not items:
        return "持仓：无"
    # 中文名按字数对齐，补全角空格，飞书里比半角空格稳
    name_w = max(len(name) for name, _ in items)
    lines = ["持仓："]
    for name, pct in items:
        pad = "\u3000" * (name_w - len(name))
        lines.append(f"{name}{pad}  {pct:5.2f}%")
    return "\n".join(lines)


def report_cash_to_client(context):
    positions: Dict[str, Position] = get_all_positions(context)
    cash = get_context_cash(context)
    market_value = get_all_market_value(context, positions=positions)
    assets = cash + market_value
    info = f"Assets: {round(assets)}, cash: {round(cash)}\n"
    if cons.EACH_PERSON_RATE is not None:
        for name, rate in cons.EACH_PERSON_RATE.items():
            info += f"{name}:\nassets: {round(rate * assets, 2)}\n\n"
    info = info.rstrip("\n\n")
    logger.info(info)
    return assets


def report_positions_and_cash(context, send_msg: bool = True):
    positions: Dict[str, Position] = get_all_positions(context)
    cash = get_context_cash(context)
    market_value = get_all_market_value(context, positions=positions)
    assets = cash + market_value
    pos_rate = (market_value / assets * 100) if assets else 0.0

    sorted_pos = sorted(positions.values(), key=lambda p: p.market_value, reverse=True)
    name_map = _get_symbol_names([p.symbol for p in sorted_pos])
    hold_items: List[Tuple[str, float]] = []
    for posi in sorted_pos:
        name = name_map.get(posi.symbol, posi.symbol)
        pct = (posi.market_value / assets * 100) if assets else 0.0
        hold_items.append((name, pct))
        # 本地日志保留盈亏细节，便于排查
        profit = (posi.price / posi.vwap - 1) * 100 if posi.vwap else 0.0
        logger.info(
            f"position detail: {posi.symbol}({name}), value={round(posi.market_value)}, "
            f"asset_pct={pct:.2f}%, profit={profit:.2f}%"
        )

    content = "\n".join([
        "【持仓汇总】",
        f"总资产 {int(round(assets)):,}",
        f"现金 {int(round(cash)):,}",
        f"仓位 {pos_rate:.1f}%",
        f"持仓 {len(positions)}",
        "----------",
        _fmt_holdings_block(hold_items),
    ])
    logger.info(content)
    # 分账仅写日志，不发飞书
    if cons.EACH_PERSON_RATE is not None:
        share_lines = ["分账："]
        share_items = sorted(
            (
                (name, rate * assets, rate * 100)
                for name, rate in cons.EACH_PERSON_RATE.items()
            ),
            key=lambda x: x[1],
            reverse=True,
        )
        for name, amt, rate_pct in share_items:
            share_lines.append(f"  {name}  {int(round(amt)):,}  ({rate_pct:.2f}%)")
        logger.info("\n".join(share_lines))
    if send_msg:
        if cons.REPORT_SWITCH:
            send_group_msg(cons.FEISHU_GROUP, content)
        else:
            info = f"Real Position Rate: {round(pos_rate)}%, Holding Number: {len(positions)}."
            send_group_msg(cons.FEISHU_GROUP, info)
    return assets


def report_dealing_price(context):
    exec_rpt: List[ExecRpt] = get_exec_rpt_v2()
    buy_dict = defaultdict(list)
    sell_dict = defaultdict(list)
    for exec_ in exec_rpt:
        if exec_.side == OrderSide.OrderSide_Buy:
            buy_dict[exec_.symbol].append((exec_.volume, exec_.amount))
        if exec_.side == OrderSide.OrderSide_Sell:
            sell_dict[exec_.symbol].append((exec_.volume, exec_.amount))
    for symbol, value in buy_dict.items():
        volume = sum(v for v, _ in value)
        amount = sum(a for _, a in value)
        if volume > 0:
            logger.info(
                f"Buy order, symbol: {symbol}, avg price: {round(amount / volume, 2)}, total value: {amount}"
            )
    for symbol, value in sell_dict.items():
        volume = sum(v for v, _ in value)
        amount = sum(a for _, a in value)
        if volume > 0:
            logger.info(
                f"Sell order, symbol: {symbol}, avg_price: {round(amount / volume, 2)}, total value: {amount}"
            )

    sell_slide, buy_slide, sell_v, buy_v, sell_details, buy_details = (
        context.order_manager.analyse_slide_price(exec_rpt)
    )
    if not sell_details and not buy_details:
        return

    symbols = [s for s, _, _ in sell_details + buy_details]
    name_map = _get_symbol_names(symbols)
    missing = [s for s in symbols if s not in name_map]
    if missing:
        logger.warning(f"slide name lookup missing {len(missing)}/{len(symbols)}: {missing[:8]}")
    lines = [
        "【滑点统计】",
        f"卖 {_fmt_slide_pct(sell_slide)} / {int(round(sell_v)):,}    "
        f"买 {_fmt_slide_pct(buy_slide)} / {int(round(buy_v)):,}",
    ]
    sell_block = _fmt_slide_detail_block("卖", sell_details, name_map)
    buy_block = _fmt_slide_detail_block("买", buy_details, name_map)
    if sell_block:
        lines.append(sell_block)
    if buy_block:
        lines.append(buy_block)
    content = "\n".join(lines)
    logger.info(content)
    send_group_msg(cons.FEISHU_GROUP, content)


def _parse_level(raw) -> Optional[int]:
    s = str(raw).strip()
    if not s:
        return None
    if s.isdigit():
        level = int(s)
        return level if level in _LEVEL_NAME else None
    name = s.split(".")[-1]
    for level, level_name in _LEVEL_NAME.items():
        if name == level_name:
            return level
    return None


def _read_csv_rows(path: str) -> Optional[List[List[str]]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f if line.strip()]
    except Exception as e:
        logger.warning(f"read file failed: {path}, err={e}")
        return None
    if not lines:
        return None
    return [line.split(",") for line in lines]


def _load_day_order_plan(day: str) -> Optional[Dict[Tuple[str, str], dict]]:
    """
    return: {(symbol, side): {level, plan_value, open}}
    """
    path = os.path.join(_DATA_DIR, day, _ORDER_PLAN_FILE)
    rows = _read_csv_rows(path)
    if not rows:
        return None
    start = 1 if rows[0] and rows[0][0] == "symbol" else 0
    plans: Dict[Tuple[str, str], dict] = {}
    for cols in rows[start:]:
        if len(cols) < 8:
            return None
        symbol, side = cols[0].strip(), cols[1].strip().lower()
        if side not in ("buy", "sell"):
            return None
        level = _parse_level(cols[2])
        if level is None:
            # 兼容 level_name 写在第 3 列异常情况，优先第 3 列数字、第 4 列名字
            level = _parse_level(cols[3]) if len(cols) > 3 else None
        if level is None:
            return None
        try:
            plan_value = float(cols[5])
            open_price = float(cols[6])
        except (TypeError, ValueError):
            return None
        if plan_value < 0 or open_price <= 0:
            return None
        plans[(symbol, side)] = {
            "level": level,
            "plan_value": plan_value,
            "open": open_price,
        }
    return plans if plans else None


def _load_day_trade_fills(day: str) -> Optional[Dict[Tuple[str, str], dict]]:
    """
    return: {(symbol, side): {filled_value, slide_weighted}}
    slide_weighted = sum(slide * amount)
    """
    path = os.path.join(_DATA_DIR, day, _TRADE_HISTORY_FILE)
    if not os.path.exists(path):
        return None
    rows = _read_csv_rows(path)
    # 文件存在但为空：当日无成交，完成度按 0 计
    if rows is None:
        return {}
    fills: Dict[Tuple[str, str], dict] = {}
    for cols in rows:
        # created_at,symbol,side,open,pre_close,level,amount,volume,deal_p
        if len(cols) < 9:
            return None
        symbol, side = cols[1].strip(), cols[2].strip().lower()
        if side not in ("buy", "sell"):
            return None
        try:
            open_price = float(cols[3])
            amount = float(cols[6])
            deal_p = float(cols[8])
        except (TypeError, ValueError):
            return None
        if open_price <= 0 or amount < 0:
            return None
        slide = deal_p / open_price - 1
        key = (symbol, side)
        agg = fills.setdefault(key, {"filled_value": 0.0, "slide_weighted": 0.0})
        agg["filled_value"] += amount
        agg["slide_weighted"] += slide * amount
    return fills


def _analyze_day_slide(day: str) -> Optional[Dict[Tuple[int, str], dict]]:
    plans = _load_day_order_plan(day)
    fills = _load_day_trade_fills(day)
    if plans is None or fills is None:
        return None
    # level, side -> plan_value / filled_value / slide_weighted
    # 完成度：单日单股成交额不超过计划额，超出部分不计
    buckets: Dict[Tuple[int, str], dict] = defaultdict(
        lambda: {"plan_value": 0.0, "filled_value": 0.0, "slide_weighted": 0.0}
    )
    for (symbol, side), plan in plans.items():
        key = (plan["level"], side)
        plan_v = plan["plan_value"]
        buckets[key]["plan_value"] += plan_v
        fill = fills.get((symbol, side))
        if not fill:
            continue
        filled = fill["filled_value"]
        capped = min(filled, plan_v)
        buckets[key]["filled_value"] += capped
        if filled > 0 and capped > 0:
            buckets[key]["slide_weighted"] += fill["slide_weighted"] * (capped / filled)
    return dict(buckets)


def report_slide_history(context, lookback_days: int = 20):
    """
    汇总最近 lookback_days 个交易日（含当日）的计划/成交埋点，
    按 优先级 + 买/卖 打印完成比例、滑点、总交易金额。
    单日缺文件或格式不对则跳过。仅用于盘后 end_report。
    """
    today = date2str(context.now)
    try:
        prev_days = gmapi.get_previous_n_trading_dates("SZSE", today, n=lookback_days - 1)
    except Exception as e:
        logger.warning(f"get_previous_n_trading_dates failed: {e}")
        prev_days = []
    trade_days = [today] + list(prev_days)

    merged: Dict[Tuple[int, str], dict] = defaultdict(
        lambda: {"plan_value": 0.0, "filled_value": 0.0, "slide_weighted": 0.0, "days": 0}
    )
    used_days = []
    skipped_days = []
    for day in trade_days:
        day_stat = _analyze_day_slide(day)
        if day_stat is None:
            skipped_days.append(day)
            continue
        used_days.append(day)
        for key, stat in day_stat.items():
            agg = merged[key]
            agg["plan_value"] += stat["plan_value"]
            agg["filled_value"] += stat["filled_value"]
            agg["slide_weighted"] += stat["slide_weighted"]
            agg["days"] += 1

    lines = [
        f"【近{lookback_days}日滑点分析】",
        f"有效交易日: {len(used_days)}, 跳过: {len(skipped_days)}",
    ]

    if not used_days:
        lines.append("无可用埋点数据")
        content = "\n".join(lines)
        logger.info(content)
        send_group_msg(cons.FEISHU_GROUP, content)
        return content

    # 排序：level 升序，sell 在前 buy 在后
    side_order = {"sell": 0, "buy": 1}
    keys = sorted(merged.keys(), key=lambda x: (x[0], side_order.get(x[1], 9)))
    for level, side in keys:
        stat = merged[(level, side)]
        plan_v = stat["plan_value"]
        filled_v = stat["filled_value"]
        fill_rate = (filled_v / plan_v) if plan_v > 0 else 0.0
        slide = (stat["slide_weighted"] / filled_v) if filled_v > 0 else 0.0
        level_name = _LEVEL_NAME.get(level, str(level))
        side_cn = "卖" if side == "sell" else "买"
        lines.append(
            f"{level_name}({level})/{side_cn}: "
            f"完成度 {fill_rate * 100:.2f}%  |  "
            f"滑点 {_fmt_slide_pct(slide)}  |  "
            f"成交额 {int(round(filled_v)):,}"
        )

    content = "\n".join(lines)
    logger.info(content)
    send_group_msg(cons.FEISHU_GROUP, content)
    return content