import datetime
import sys
sys.path.append("../../")
import os
from utils.timetool import get_real_time_run_time_node, is_today_trade_day
from dataset.api import update_history_suspend_and_st_info, update_history_market_value_info, update_symbols, \
    update_history_data, update_increase_info, update_increase_info_v2, update_history_ttm, \
    update_history_market_value_info_v2, update_history_ttm_v2, update_income_info
from dataset.sos_db import LocalDb
from config import cons
import gm.api as gmapi
from loguru import logger
from utils.timetool import str2strptime, date2str, get_beijing_now

START_DAY = "2005-12-25"


def init(context):
    # mission
    logger.add(os.path.join("data", f"{get_beijing_now()}.log"))
    time_node = get_real_time_run_time_node()
    logger.info(f"start time: {time_node}")
    gmapi.schedule(schedule_func=start, date_rule='1d', time_rule=time_node)


def start(context):
    start_day = START_DAY
    logger.info(f"start_day: {start_day}")
    data_folder = "../../buffer"
    if not os.path.exists(data_folder):
        os.mkdir(data_folder)
    data_folder = os.path.join(data_folder, "db")
    end_day = date2str(context.now + datetime.timedelta(days=1))
    logger.info(f"start_day: {start_day}, end_day: {end_day}")
    logger.info("start!")
    db = LocalDb(data_folder, start_year=start_day[:4], end_year=end_day[:4])
    update_symbols(db)
    # update_history_data(start_day, end_day, db)
    # update_history_suspend_and_st_info(start_day, end_day, db)
    # update_history_market_value_info(start_day, end_day, db)
    # update_increase_info_v2(start_day, end_day, db)
    update_history_ttm(start_day, end_day, db)
    # update_income_info(start_day, end_day, db)
    db.wash(reload=False)
    logger.info(f"update data finished !")
    exit()


if __name__ == '__main__':
    gmapi.run(strategy_id=cons.DATA_UPDATE_STRATEGY_ID ,
              filename="offline_download.py",
              mode=gmapi.MODE_LIVE,
              token=cons.TOKEN)