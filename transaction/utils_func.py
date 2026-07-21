from loguru import logger
from schema.stock import Tick
import traceback


# 交易服务连接成功后触发
def on_trade_data_connected(context):
    logger.info('server connected.')


# 交易服务断开后触发
def on_trade_data_disconnected(context):
    logger.info('server disconnected.')


# 当发生异常情况，比如断网时、终端服务崩溃时会触发
def on_error(context, code, info):
    logger.info(f'abnormal! code:{code}, info:{info}')


def print_report_price_queue(tick: Tick):
    try:
        logger.info(f"----- {tick.symbol}, price: {tick.price} -----")
        for quote in tick.quotes[:5][::-1]:
            logger.info(f"--- S  {quote.ask_p:.2f}  {int(quote.ask_v/100)}")
        logger.info("-" * 32)
        for quote in tick.quotes[:5]:
            logger.info(f"--- B  {quote.bid_p:.2f}  {int(quote.bid_v/100)}")
    except:
        logger.error(traceback.format_exc())
        logger.error(f"tick info: {tick}")




