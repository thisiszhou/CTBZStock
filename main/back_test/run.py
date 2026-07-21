import datetime
import os
import sys

sys.path.append("../../")

from config.cons import FEISHU_GROUP, REPORT_SWITCH
from loguru import logger
from strategy.backtrade.small_cap_demo import STRATEGY_NAME, SmallCapDemo
from third_part.feishu_service import send_group_msg
from utils.timetool import date2str_offline, get_beijing_now

logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add(f"{os.path.join('data', get_beijing_now() + '.log')}", level="INFO")

c_date = get_beijing_now(format=False)
year = c_date.year
end_day = date2str_offline(c_date)
start_day = f"{year}0101"

mov = SmallCapDemo(
    start_money=1500000,
    start_year=year - 1,
    end_year=year,
    data_db_folder="../../buffer/db",
    index_db_folder=None,
)
profits, max_retrace, _, last_retrace, year_max_retrace, _ = mov.run(
    start_day=start_day, end_day=end_day
)

if REPORT_SWITCH:
    info = "\n".join([
        f"【{STRATEGY_NAME}】",
        f"当前收益: {profits}",
        f"年内最大回撤: {max_retrace}",
        f"年内本金最大回撤: {year_max_retrace}",
        f"当前回撤: {last_retrace}",
    ])
else:
    info = "\n".join([
        f"【{STRATEGY_NAME}】",
        "当前收益: *",
        "年内最大回撤: *",
        "年内本金最大回撤: *",
        "当前回撤: *",
    ])

logger.info(info)
print(info)
send_group_msg(FEISHU_GROUP, info)
