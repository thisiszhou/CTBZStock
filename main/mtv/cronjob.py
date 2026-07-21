# coding=utf-8
# 小市值实盘代码
from __future__ import print_function, absolute_import
import sys
sys.path.append("../../")
from datetime import timedelta
from typing import Any, cast
from utils.timetool import (
    get_beijing_now, get_real_time_run_time_node, is_today_trade_day,
    date2str, get_format_time, get_current_hms_str,
)
from loguru import logger
from strategy.online.small_cap_demo import generate_order, get_position_detail
from schema.status import Mode
# from transaction.report import report_trade
from utils.context_func import get_all_positions
from transaction.order_trigger import do_transaction, on_tick
from transaction.utils_func import on_error, on_trade_data_disconnected, on_trade_data_connected
from config import cons
import traceback
import gm.api as gmapi
import os
from utils.report import report_positions_and_cash, report_cash_to_client, report_slide_history
import time
from third_part.feishu_service import send_group_msg
import subprocess

MTV_DEBUG_START = False
MTV_DEBUG_REPORT = False
IPO_DEBUG = False
TRADE = True


# 策略中必须有init方法
def init(context):
    # 定时任务,日频
    logger.info(f"Init schedule, cons: MODE={cons.MODE}, MTV_SWITCH={cons.MTV_SWITCH}, "
                f"REPORT_SWITCH={cons.REPORT_SWITCH}, TRADE_START_TIME={cons.TRADE_START_TIME}")
    # mission
    if is_today_trade_day(context.now) or MTV_DEBUG_START or MTV_DEBUG_REPORT or IPO_DEBUG:
        if cons.MODE == Mode.LIVE and cons.IPO:
            gmapi.schedule(schedule_func=ipo, date_rule='1d',
                           time_rule=cons.IPO_RUN_TIME_NODE if not IPO_DEBUG else get_real_time_run_time_node())
        if cons.MTV_SWITCH:
            gmapi.schedule(schedule_func=mtv, date_rule='1d',
                           time_rule=cons.MTV_RUN_TIME_NODE if not MTV_DEBUG_START else get_real_time_run_time_node())
        if cons.REPORT_SWITCH or MTV_DEBUG_REPORT:
            gmapi.schedule(schedule_func=end_report, date_rule='1d',
                           time_rule=cons.MTV_REPORT_TIME_NODE if not MTV_DEBUG_REPORT else get_real_time_run_time_node())
    else:
        logger.info("Today is not trading day ! No mission !")
        exit()


def ipo(context):
    logger.debug(f"ipo_get_instruments: {gmapi.ipo_get_instruments(cast(Any, 1))}")
    logger.debug(f"ipo_get_instruments: {gmapi.ipo_get_instruments(cast(Any, 8))}")
    logger.debug(f"ipo_get_quota: {gmapi.ipo_get_quota()}")
    start_time = get_format_time(get_beijing_now(False) - timedelta(days=7), 2) or ""
    end_time = get_format_time(get_beijing_now(False), 2) or ""
    logger.debug(f"ipo_get_match_number: {gmapi.ipo_get_match_number(start_time, end_time)}")
    logger.debug(f"ipo_get_lot_info: {gmapi.ipo_get_lot_info(start_time, end_time)}")
    new_bonds = gmapi.ipo_get_instruments(cast(Any, 8))
    for bond in new_bonds:
        gmapi.ipo_buy(bond['symbol'], 10000, 100)


def mtv(context):
    # start function
    t0 = time.time()
    logger.info(
        f"function start, time: {context.now}, "
        f"wall_hms={get_current_hms_str()}, "
        f"trade_start_time={cons.TRADE_START_TIME}, "
        f"log file: ./data/{context.now}.log"
    )
    try:
        t_gen = time.time()
        order_manager = generate_order(context)
        logger.info(
            f"[timing] generate_order done, elapsed={time.time() - t_gen:.3f}s, "
            f"wall_hms={get_current_hms_str()}, "
            f"order_manager_is_none={order_manager is None}"
        )
        context.order_manager = order_manager
        if order_manager is not None and TRADE:
            t_tx = time.time()
            do_transaction(context)
            logger.info(f"[timing] do_transaction done, elapsed={time.time() - t_tx:.3f}s")
        else:
            logger.info(f"[timing] skip do_transaction, TRADE={TRADE}, order_manager={order_manager}")
        logger.info(f"[timing] mtv total elapsed={time.time() - t0:.3f}s")
    except Exception as e:
        logger.error(f"Start function failed: {e}")
        logger.error(traceback.format_exc())
        raise


def end_report(context):
    # 【滑点统计】已在交易完成时发过；此处发持仓汇总 + 近20日滑点，并落盘
    report_cash_to_client(context)
    assets = report_positions_and_cash(context, send_msg=True)
    positions = get_all_positions(context)
    filename = os.path.join("data", date2str(context.now), "asset.txt")
    with open(filename, "w") as f:
        f.write(f"{','.join([str(assets)] + list(positions.keys()))}")
    # inc
    inc, value = get_position_detail(context)
    filename = os.path.join("data", date2str(context.now), "record.txt")
    with open(filename, "w") as f:
        f.write(f"{inc},{value}")
    # 近 20 日滑点/完成度（按优先级 + 买/卖），缺埋点的交易日自动跳过
    report_slide_history(context, lookback_days=20)
    exit()


def run_client():
    subprocess.run(
        ["start", "cindasc.exe"],
        cwd=r"C:\Users\Administrator\AppData\Roaming\Cindasc Goldminer",
        shell=True,  # Windows 下执行内置命令需要 shell=True
    )
    time.sleep(180)


def shutdown_client():
    subprocess.run(
        # ["taskkill", "-f", "-im", "vanhogm3b.exe"],
        ["taskkill", "-f", "-im", "cindasc.exe"],
        shell=True,  # Windows 下执行内置命令需要 shell=True
    )
    time.sleep(5)


if __name__ == '__main__':
    logger.add(f"{os.path.join('data', get_beijing_now() + '.log')}")
    status = False
    for i in range(5):
        if not MTV_DEBUG_REPORT and not MTV_DEBUG_START and not IPO_DEBUG:
            shutdown_client()
            run_client()
        try:
            gmapi.run(strategy_id=cons.STRATEGY_ID,
                      filename='cronjob.py',
                      mode=gmapi.MODE_LIVE,
                      token=cons.TOKEN)
            status = True
        except gmapi.GmError as e:
            logger.error(f"type e: {type(e)}, e: {e}")
            if e.status in [1001, 1010, 1013, 1015, 1018, 1019]:
                status = False
            else:
                status = True
        except Exception as e:
            logger.error(f"type e: {type(e)}, e: {e}")
            status = True
        if status:
            break
