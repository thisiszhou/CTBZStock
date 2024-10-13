from pydantic import BaseModel
from schema.status import Mode
from typing import Dict


class Config(BaseModel):
    mtv_start_time: str
    mtv_report_time: str
    mtv_switch: bool
    cb_start_time: str
    trade_start_time: str
    shipping_space: float
    slide_rate: float = 0
    avg_value: float = 0
    mode: Mode
    # feishu api
    feishu_group: str
    feishu_app_id: str
    feishu_app_secret: str



