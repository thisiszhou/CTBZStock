import os
import gm.api as gmapi
from utils.timetool import date2str
from datetime import date
from loguru import logger


def decode_info(info: str):
    if "%" in info:
        return float(info.rstrip("%")) / 100
    else:
        return float(info)


class LocalSaver(object):
    def __init__(self, folder="data"):
        if not os.path.exists(folder):
            os.mkdir(folder)
        self.folder = folder

    def read(self, day: date, file_name="saver.txt"):
        return_dict = dict()
        last_trade_day = gmapi.get_previous_n_trading_dates("SZSE", date2str(day), n=1)[0]
        i = 0
        logger.debug(f"read file: {os.path.join(self.folder, last_trade_day, file_name)}")
        while not os.path.exists(os.path.join(self.folder, last_trade_day, file_name)):
            i += 1
            last_trade_day = gmapi.get_previous_n_trading_dates("SZSE", last_trade_day, n=1)[0]
            if i > 20:
                return return_dict
        with open(os.path.join(self.folder, last_trade_day, file_name), "r") as f:
            data = f.readlines()
        for line in data:
            symbol, info = line.rstrip().split(",")
            return_dict[symbol] = decode_info(info)
        return return_dict

    def write(self, day: date, save_dict, file_name="saver.txt"):
        with open(os.path.join(self.folder, date2str(day), file_name), "w") as f:
            for key, value in save_dict.items():
                if isinstance(value, float):
                    v_str = round(value, 3)
                else:
                    v_str = value
                f.write(f"{key},{v_str}\n")

    def write_list(self, day: date, write_info, file_name):
        with open(os.path.join(self.folder, date2str(day), file_name), "w") as f:
            for line in write_info:
                f.write(",".join([str(x) for x in line]) + "\n")




