from typing import Tuple, Dict
from schema.stock import Position
import gm.api as gmapi
from loguru import logger


def get_all_positions(context) -> Dict[str, Position]:
    positions: Dict[str, Position] = {
        x['symbol']: Position(**x) for x in context.account().positions() if x['volume'] > 0
    }
    return positions


def get_position(context, symbol):
    position = context.account().position(symbol=symbol, side=1)
    if position is not None:
        return Position(**position)
    return None


def get_cash(context):
    return context.account().cash['available']


def get_all_market_value(context, positions: Dict[str, Position] = None):
    if positions is None:
        positions: Dict[str, Position] = {
            x['symbol']: Position(**x) for x in context.account().positions() if x['volume'] > 0
        }
    return sum([x.market_value for x in positions.values()])
