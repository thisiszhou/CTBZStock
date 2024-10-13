from loguru import logger


# 交易服务连接成功后触发
def on_trade_data_connected(context):
    logger.info('server connected.')


# 交易服务断开后触发
def on_trade_data_disconnected(context):
    logger.info('server disconnected.')


# 当发生异常情况，比如断网时、终端服务崩溃时会触发
def on_error(context, code, info):
    logger.info(f'abnormal! code:{code}, info:{info}')


