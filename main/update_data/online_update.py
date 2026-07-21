import datetime
import sys
sys.path.append("../../")
import os
from utils.timetool import get_real_time_run_time_node, is_today_trade_day
from dataset.api import update_history_suspend_and_st_info, update_history_market_value_info, update_symbols, \
    update_history_data, update_increase_info, update_increase_info_v2, update_history_ttm, \
    update_history_market_value_info_v2, update_history_ttm_v2, update_income_info_batch
from dataset.sos_db import LocalDb
from config import cons
import gm.api as gmapi
from loguru import logger
from utils.timetool import str2strptime, date2str, get_beijing_now

DEBUG = True
DOWNLOAD_ADVANCE_DAYS = 10


def init(context):
    # mission
    logger.add(f"{os.path.join('data', get_beijing_now() + '.log')}")
    if is_today_trade_day(context.now) or DEBUG:
        time_node = get_real_time_run_time_node()
        logger.info(f"start time: {time_node}")
        gmapi.schedule(schedule_func=start, date_rule='1d', time_rule=time_node)
    else:
        logger.info("Today is not trading day ! No mission !")
        exit()


def start(context):
    lastest_day = f"{context.now.year - 1}-12-25"
    logger.info(f"lastest_day: {lastest_day}")
    data_folder = "../../buffer"
    if not os.path.exists(data_folder):
        os.mkdir(data_folder)
    data_folder = os.path.join(data_folder, "db")
    if os.path.exists(data_folder):
        start_day = gmapi.get_previous_n_trading_dates("SZSE", date2str(context.now), n=DOWNLOAD_ADVANCE_DAYS)
        start_day = start_day[0]
    else:
        start_day = lastest_day
    end_day = date2str(context.now + datetime.timedelta(days=1))
    logger.info(f"start_day: {start_day}, end_day: {end_day}")
    logger.info("start!")
    db = LocalDb(data_folder, start_year=start_day[:4], end_year=context.now.year)
    update_symbols(db)
    update_history_data(start_day, end_day, db)
    update_history_suspend_and_st_info(start_day, end_day, db)
    update_history_market_value_info_v2(start_day, end_day, db)
    # update_increase_info(start_day, end_day, db)
    update_increase_info_v2(start_day, end_day, db)
    update_history_ttm_v2(start_day, end_day, db)
    update_income_info_batch(start_day, end_day, db)
    db.wash()
    logger.info(f"update data finished !")
    exit()


if __name__ == '__main__':
    gmapi.run(strategy_id=cons.DATA_UPDATE_STRATEGY_ID ,
              filename="online_update.py",
              mode=gmapi.MODE_LIVE,
              token=cons.TOKEN)


