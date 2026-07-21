"""RocksDB (rocksdict) + pickle 本地 KV。

存储布局（按年分片）::
    {db_folder}/symbols/       # 代码表
    {db_folder}/{year}_data/   # 该年日线 KV

值：pickle。读取默认 obj(**dict)。
"""

from __future__ import annotations

import os
import pickle
import shutil
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Optional, Tuple, Union

from loguru import logger
from pydantic import BaseModel
from rocksdict import AccessType, Options, Rdict, WriteBatch
from utils.timetool import date2str, offline_str2date

KEY_SYMBOL = "symbol::"
KEY_DAY_DATA = "one_day_info:{}:{}"  # tag, day, code

PICKLE_PROTOCOL = pickle.HIGHEST_PROTOCOL
DEFAULT_BLOCK_CACHE_MB = 64


def split_key(k: str) -> Tuple[str, Optional[str], Optional[str]]:
    tag, day, symbol = k.split(":")
    if day:
        return tag, date2str(offline_str2date(day)), symbol
    return tag, None, symbol


def _encode_key(key: str) -> bytes:
    return key.encode("utf-8")


def _dumps(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump()
    return pickle.dumps(value, protocol=PICKLE_PROTOCOL)


def _loads(raw: bytes, obj: Optional[Callable[..., Any]] = None, *, use_construct: bool = False) -> Any:
    data = pickle.loads(raw)
    if obj is None:
        return data
    if isinstance(data, obj):
        return data
    if isinstance(data, dict):
        if use_construct:
            construct = getattr(obj, "model_construct", None)
            if construct is not None:
                return construct(**data)
        return obj(**data)
    return data


def _open_opts(*, block_cache_mb: int, create: bool) -> Options:
    opts = Options(raw_mode=True)
    if create:
        opts.create_if_missing(True)
    opts.optimize_for_point_lookup(block_cache_mb)
    opts.set_max_open_files(-1)
    opts.set_write_buffer_size(64 * 1024 * 1024)
    opts.set_target_file_size_base(64 * 1024 * 1024)
    opts.set_max_background_jobs(max(os.cpu_count() or 2, 2))
    return opts


class _RocksDict:
    """单目录 RocksDB，dict 风格 get/set；支持批量写入。"""

    def __init__(
        self,
        path: str,
        readonly: bool = False,
        block_cache_mb: int = DEFAULT_BLOCK_CACHE_MB,
        warm: bool = False,
    ):
        os.makedirs(path, exist_ok=True)
        self.path = path
        self._readonly = readonly
        opts = _open_opts(block_cache_mb=block_cache_mb, create=not readonly)
        access = AccessType.read_only() if readonly else AccessType.read_write()
        self._db = Rdict(path, opts, access_type=access)
        if warm:
            self.warm()

    def warm(self):
        t0 = time.perf_counter()
        n = 0
        for _k, _v in self._db.items():
            n += 1
        logger.info(f"RocksDB warm {self.path}: entries={n} cost={time.perf_counter() - t0:.2f}s")

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None

    def __contains__(self, key: str) -> bool:
        return _encode_key(key) in self._db

    def get(self, key: str, default=None):
        raw = self._db.get(_encode_key(key))
        if raw is None:
            return default
        return _loads(raw)

    def __getitem__(self, key: str):
        raw = self._db.get(_encode_key(key))
        if raw is None:
            raise KeyError(key)
        return _loads(raw)

    def __setitem__(self, key: str, value: Any):
        if self._readonly:
            raise RuntimeError(f"RocksDB readonly: {self.path}")
        self._db[_encode_key(key)] = _dumps(value)

    @contextmanager
    def write_batch(self, buffersize: int = 5000) -> Iterator[Callable[[str, Any], None]]:
        if self._readonly:
            raise RuntimeError(f"RocksDB readonly: {self.path}")
        wb = WriteBatch(raw_mode=True)
        n = 0

        def put(key: str, value: Any):
            nonlocal n, wb
            wb.put(_encode_key(key), _dumps(value))
            n += 1
            if n >= buffersize:
                self._db.write(wb)
                wb = WriteBatch(raw_mode=True)
                n = 0

        try:
            yield put
        finally:
            if n > 0:
                self._db.write(wb)

    def keys(self):
        for k in self._db.keys():
            yield k.decode("utf-8")

    def items(self):
        for k, v in self._db.items():
            yield k.decode("utf-8"), _loads(v)

    def __len__(self) -> int:
        n = 0
        for _ in self._db.keys():
            n += 1
        return n


class LocalDb(object):
    """按年分片 RocksDB：symbols/ + {year}_data/。"""

    def __init__(
        self,
        db_folder="buffer/db",
        mkdir=True,
        start_year=None,
        end_year=None,
        readonly: bool = False,
        warm_on_open: bool = False,
        block_cache_mb: int = DEFAULT_BLOCK_CACHE_MB,
        use_construct: bool = False,
        **_ignored,
    ):
        assert start_year is not None
        assert end_year is not None
        if isinstance(start_year, str):
            start_year = int(start_year)
        if isinstance(end_year, str):
            end_year = int(end_year)
        assert end_year >= start_year
        self.start_year = start_year
        self.end_year = end_year
        self.db_folder = db_folder
        self.readonly = readonly
        self.warm_on_open = warm_on_open
        self.block_cache_mb = block_cache_mb
        self.use_construct = use_construct
        if not os.path.exists(db_folder) and mkdir:
            os.makedirs(db_folder, exist_ok=True)
        self.symbol_db: Optional[_RocksDict] = None
        self.dbs: Dict[str, _RocksDict] = {}
        self.load_dbs()

    def _require_symbol_db(self) -> _RocksDict:
        if self.symbol_db is None:
            raise RuntimeError("LocalDb.symbol_db is not initialized")
        return self.symbol_db

    def _year_path(self, year: Union[int, str]) -> str:
        return os.path.join(self.db_folder, f"{year}_data")

    def _symbols_path(self) -> str:
        return os.path.join(self.db_folder, "symbols")

    def load_dbs(self):
        if not os.path.exists(self.db_folder):
            return

        sym_path = self._symbols_path()
        if self.readonly:
            if not os.path.isdir(sym_path):
                raise FileNotFoundError(f"missing RocksDB symbols dir: {sym_path}")
        else:
            os.makedirs(sym_path, exist_ok=True)

        self.symbol_db = _RocksDict(
            sym_path,
            readonly=self.readonly,
            block_cache_mb=min(self.block_cache_mb, 32),
            warm=False,
        )
        logger.info("Load symbols RocksDB finished !")

        for year in range(self.start_year, self.end_year + 1):
            path = self._year_path(year)
            if self.readonly:
                if not os.path.isdir(path):
                    logger.warning(f"skip missing year db: {path}")
                    continue
            else:
                os.makedirs(path, exist_ok=True)
            self.dbs[str(year)] = _RocksDict(
                path,
                readonly=self.readonly,
                block_cache_mb=self.block_cache_mb,
                warm=self.warm_on_open,
            )
            logger.info(f"Load {year} db finished !")
        logger.info("Load dbs !")

    def close(self):
        if self.symbol_db is not None:
            self.symbol_db.close()
            self.symbol_db = None
        for db in self.dbs.values():
            db.close()
        self.dbs.clear()

    @staticmethod
    def _set(db: _RocksDict, key, value):
        db[key] = value

    def update_symbol(self, key: str, value: Dict):
        assert key == KEY_SYMBOL
        symbol_db = self._require_symbol_db()
        existing = symbol_db.get(key, None)
        if not existing:
            symbol_db[key] = value
        else:
            existing.update(value)
            symbol_db[key] = existing

    def set(self, key: str, value):
        tag, day, _symbol = split_key(key)
        if tag == "symbol":
            self._set(self._require_symbol_db(), key, value)
        else:
            if day is None:
                raise ValueError("invalid key: missing day")
            year = day[:4]
            if year not in self.dbs:
                raise ValueError(f"key of year {year} not in self.dbs")
            self._set(self.dbs[year], key, value)

    def get(self, key: str, obj: Optional[Callable[..., Any]] = None):
        if key.startswith("symbol"):
            return self._require_symbol_db().get(key, None)
        parts = key.split(":")
        if len(parts) < 2 or not parts[1]:
            raise ValueError("invalid key: missing day")
        year = parts[1][:4]
        db = self.dbs.get(year)
        if db is None:
            raise ValueError(f"key of year {year} not in self.dbs")
        raw = db._db.get(_encode_key(key))
        if raw is None:
            return None
        return _loads(raw, obj, use_construct=self.use_construct)

    def wash(self, start_day=None, reload=True):
        """对 RocksDB 做 compact。start_day 保留兼容，当前忽略。"""
        _ = start_day
        symbol_db = self._require_symbol_db()
        symbol_db._db.compact_range(None, None)
        logger.info("symbols RocksDB compact finished !")
        for year, db in self.dbs.items():
            db._db.compact_range(None, None)
            logger.info(f"year of {year} data wash finished !")
        if reload:
            self.close()
            self.load_dbs()


def wash_db(db_folder_ob: Union[str, list]):
    """对 RocksDB 目录（或含年分片的文件夹）执行 compact。"""
    paths: list
    if isinstance(db_folder_ob, list):
        paths = list(db_folder_ob)
    else:
        paths = [db_folder_ob]

    for path in paths:
        if not os.path.exists(path):
            logger.warning(f"wash_db skip missing: {path}")
            continue

        if os.path.isfile(path):
            logger.warning(f"wash_db skip file (expect RocksDB dir): {path}")
            continue

        # 若是 LocalDb 根目录（含 symbols / {year}_data），逐个子库 compact
        sub_dirs = []
        names = os.listdir(path)
        if "CURRENT" in names or any(n.startswith("MANIFEST-") for n in names):
            sub_dirs = [path]
        else:
            for name in names:
                p = os.path.join(path, name)
                if os.path.isdir(p):
                    sub_dirs.append(p)

        for db_path in sub_dirs:
            try:
                opts = _open_opts(block_cache_mb=16, create=False)
                db = Rdict(db_path, opts, access_type=AccessType.read_write())
                db.compact_range(None, None)
                db.close()
                logger.info(f"{db_path} wash finished .")
            except Exception as e:
                logger.warning(f"wash_db failed {db_path}: {e}")


def remove_db_folder(db_folder: str):
    if os.path.isdir(db_folder):
        shutil.rmtree(db_folder)