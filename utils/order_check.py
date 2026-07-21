from schema.inner_order import InnerOrder
from loguru import logger


def is_limit_down(price_min, price: float):
    if price <= price_min:
        return True
    else:
        return False


def is_limit_up(price_max, price: float):
    if price >= price_max:
        return True
    else:
        return False







