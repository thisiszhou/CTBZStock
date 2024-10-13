from enum import IntEnum


class Mode(IntEnum):
    LIVE = 1  # 实盘
    SIMU = 2  # 模拟实盘


class OrderSide(IntEnum):
    OrderSide_Unknown = 0
    OrderSide_Buy = 1  # 买入
    OrderSide_Sell = 2  # 卖出


class OrderType(IntEnum):
    OrderType_Unknown = 0
    OrderType_Limit = 1  # 限价委托
    OrderType_Market = 2  # 市价委托
    OrderType_Stop = 3  # 止损止盈委托  （还不支持）


class OrderRejectReason(IntEnum):
    OrderRejectReason_Unknown = 0  # 未知原因
    OrderRejectReason_RiskRuleCheckFailed = 1  # 不符合风控规则
    OrderRejectReason_NoEnoughCash = 2  # 资金不足
    OrderRejectReason_NoEnoughPosition = 3  # 仓位不足
    OrderRejectReason_IllegalAccountId = 4  # 非法账户ID
    OrderRejectReason_IllegalStrategyId = 5  # 非法策略ID
    OrderRejectReason_IllegalSymbol = 6  # 非法交易标的
    OrderRejectReason_IllegalVolume = 7  # 非法委托量
    OrderRejectReason_IllegalPrice = 8  # 非法委托价
    OrderRejectReason_AccountDisabled = 10  # 交易账号被禁止交易
    OrderRejectReason_AccountDisconnected = 11  # 交易账号未连接
    OrderRejectReason_AccountLoggedout = 12  # 交易账号未登录
    OrderRejectReason_NotInTradingSession = 13  # 非交易时段
    OrderRejectReason_OrderTypeNotSupported = 14  # 委托类型不支持
    OrderRejectReason_Throttle = 15  # 流控限制


class CancelOrderRejectReason(IntEnum):
    CancelOrderRejectReason_OrderFinalized = 101  # 委托已完成
    CancelOrderRejectReason_UnknownOrder = 102  # 未知委托
    CancelOrderRejectReason_BrokerOption = 103  # 柜台设置
    CancelOrderRejectReason_AlreadyInPendingCancel = 104  # 委托撤销中


class PositionEffect(IntEnum):
    PositionEffect_Unknown = 0
    PositionEffect_Open = 1  # 开仓
    PositionEffect_Close = 2  # 平仓, 具体语义取决于对应的交易所


class OrderStatus(IntEnum):
    Unknown = 0
    New = 1  # 已报
    PartiallyFilled = 2  # 部成
    Filled = 3  # 已成
    Canceled = 5  # 已撤
    PendingCancel = 6  # 待撤
    Rejected = 8  # 已拒绝
    Suspended = 9  # 挂起 （无效）
    PendingNew = 10  # 待报
    Expired = 12  # 已过期


class ExecType(IntEnum):
    ExecType_Unknown = 0
    ExecType_New = 1  # 已报
    ExecType_Canceled = 5  # 已撤销
    ExecType_PendingCancel = 6  # 待撤销
    ExecType_Rejected = 8  # 已拒绝
    ExecType_Suspended = 9  # 挂起
    ExecType_PendingNew = 10  # 待报
    ExecType_Expired = 12  # 过期
    ExecType_Trade = 15  # 成交
    ExecType_OrderStatus = 18  # 委托状态
    ExecType_CancelRejected = 19  # 撤单被拒绝





