import os
import sys
import time

sys.path.append("../../")

from dataset.sos_db import LocalDb
from loguru import logger
from strategy.backtrade.small_cap_demo import SmallCapDemo

mode = ""
# mode = "debug"

if mode == "debug":
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")
else:
    logger.remove()
    logger.add(sys.stderr, level="INFO")

start_year = 2006
end_year = 2025

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DB = os.path.join(ROOT, "buffer", "db")

t_load0 = time.perf_counter()
data_db = LocalDb(DATA_DB, start_year=start_year - 1, end_year=end_year)
t_load = time.perf_counter() - t_load0
logger.info(f"load_db cost={t_load:.2f}s")

t_bt0 = time.perf_counter()
mov = SmallCapDemo(
    start_money=2000000,
    start_year=start_year - 1,
    end_year=end_year,
    data_db_folder=DATA_DB,
    index_db_folder=None,
    db=data_db,
    index_db=None,
)
result = mov.run(
    start_day=f"{start_year}0101",
    end_day=f"{end_year}1231",
    show_detail=False,
    show_brief=True,
)
t_bt = time.perf_counter() - t_bt0
logger.info(f"backtest cost={t_bt:.2f}s total={t_load + t_bt:.2f}s result={result}")

try:
    data_db.close()
except Exception:
    pass
