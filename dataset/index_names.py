"""指数名称：新名与历史 buffer 旧名映射。"""


# 查询时按顺序尝试（新名优先，再回调旧 buffer 中的名）
INDEX_NAME_CANDIDATES: dict[str, tuple[str, ...]] = {
    "head300_main": ("head300_main", "top300"),
    "tail400_main": ("tail400_main", "last400"),
    "head300_all": ("head300_all", "alltop300"),
    "tail400_all": ("tail400_all",),
    "top300": ("head300_main", "top300"),
    "last400": ("tail400_main", "last400"),
    "alltop300": ("head300_all", "alltop300"),
}


def index_name_lookup_candidates(index_name: str) -> tuple[str, ...]:
    return INDEX_NAME_CANDIDATES.get(index_name, (index_name,))
