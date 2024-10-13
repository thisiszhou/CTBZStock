# coding=utf-8
# 小市值demo实盘代码
from __future__ import print_function, absolute_import
import sys
sys.path.append("../../")
from utils.timetool import get_beijing_now, get_real_time_run_time_node, is_today_trade_day
from loguru import logger
from strategy.mtvw import generate_order
from schema.config import Config
from schema.status import Mode
from transaction.order_trigger import do_transaction, on_tick
from transaction.utils_func import on_error, on_trade_data_disconnected, on_trade_data_connected
from config import master as cons
import traceback
import gm.api as gmapi
import os
from utils.report import report_positions_and_cash

MTV_DEBUG_START = False
MTV_DEBUG_REPORT = False


# 策略中必须有init方法
def init(context):
    # 定时任务,日频
    logger.add(f"{os.path.join('data', get_beijing_now() + '.log')}")
    config = Config(
        mtv_start_time=cons.MTV_RUN_TIME_NODE if not MTV_DEBUG_START else get_real_time_run_time_node(),
        mtv_report_time=cons.MTV_REPORT_TIME_NODE if not MTV_DEBUG_REPORT else get_real_time_run_time_node(),
        mtv_switch=cons.MTV_SWITCH,
        trade_start_time=cons.TRADE_START_TIME,
        shipping_space=cons.SHIPPING_SPACE,
        slide_rate=15 / 1000,
        mode=Mode.LIVE,
        feishu_group=cons.FEISHU_GROUP,
        feishu_app_id=cons.FEISHU_APP_ID,
        feishu_app_secret=cons.FEISHU_APP_SECRET
    )
    context.config = config
    logger.info(f"Init schedule, global config: {config}")
    # mission
    if is_today_trade_day(context.now):
        if config.mtv_switch:
            gmapi.schedule(schedule_func=mtv, date_rule='1d', time_rule=config.mtv_start_time)
        gmapi.schedule(schedule_func=end_report, date_rule='1d', time_rule=config.mtv_report_time)


def mtv(context):
    # start function
    logger.info(f"function start, time: {context.now}, log file: ./data/{context.now}.log")
    try:
        order_manager = generate_order(context)
        context.order_manager = order_manager
        if order_manager is not None:
            do_transaction(context)
    except Exception as e:
        logger.error(f"Start function failed: {e}")
        logger.error(traceback.format_exc())
        raise


def end_report(context):
    report_positions_and_cash(context)


if __name__ == '__main__':
    gmapi.run(strategy_id=cons.STRATEGY_ID,
              filename='cronjob.py',
              mode=gmapi.MODE_LIVE,
              token=cons.TOKEN)


