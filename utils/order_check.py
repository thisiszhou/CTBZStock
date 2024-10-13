from schema.inner_order import InnerOrder
from loguru import logger


def is_limit_down(order: InnerOrder, price: float):
    check_price_valid(order, price)
    if price <= order.price_min:
        return True
    else:
        return False


def is_limit_up(order: InnerOrder, price: float):
    check_price_valid(order, price)
    if price >= order.price_max:
        return True
    else:
        return False


def check_price_valid(order: InnerOrder, price):
    try:
        assert order.price_min <= price <= order.price_max
    except:
        logger.error(f"check_price_valid function wrong: {order}")





