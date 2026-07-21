from schema.status import Mode


MTV_RUN_TIME_NODE = "09:25:10"
MTV_REPORT_TIME_NODE = "15:00:20"
TRADE_START_TIME = "09:29:00"
IPO_RUN_TIME_NODE = "09:35:00"
SHIPPING_SPACE = 1
MIN_TRANSACTION_AMOUNT = 5000
SLIDE_RATE = 15 / 1000
EACH_PERSON_RATE = None
STRATEGY_ID = 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'  # 掘金策略 ID
DATA_UPDATE_STRATEGY_ID = 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'  # 数据更新策略 ID
TOKEN = 'xxxxxxxx'  # 掘金 token
# lark / feishu config
FEISHU_APP_ID = "cli_xxxxxxxx"  # 飞书应用 app_id
FEISHU_APP_SECRET = "xxxxxxxx"  # 飞书应用 app_secret
FEISHU_GROUP = "量化测试"
# switch
MTV_SWITCH = True
REPORT_SWITCH = True  # 飞书汇报（持仓明细/回测结果等）总开关
IPO = True
ENABLE_FREE_FIVE = True
# mode
MODE = Mode.SIMU
