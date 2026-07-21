<div align="center">

# 【CTBZStock】草台班子量化 
<div>
    <img alt="python" src="https://img.shields.io/badge/python-3.10+-%2300599C?logo=python">
    <img alt="license" src="https://img.shields.io/github/license/thisiszhou/CTBZStock">
    <img alt="stars" src="https://img.shields.io/github/stars/thisiszhou/CTBZStock?style=social">
</div>
 
牛市昙花一现，量化穿越牛熊
  
大A就是一个巨大的草台班子
  
</div>

## 项目介绍
<sub>2026.07.21 最新更新：框架沉淀了两年之后，借助 AI 工具整理代码，开源了回测框架并更新交易代码。</sub><br>
<sub>2024.10.13 首次发布</sub>

CTBZStock 是面向 A 股中低频策略的开源量化框架，覆盖 **历史数据下载 → 本地离线回测 → 模拟实盘 / 实盘定时交易** 完整链路。

项目以小市值策略 Demo 为例，基于掘金量化交易与行情接口二次封装，提供：
- 本地 RocksDB 行情库与离线回测引擎（含手续费、涨跌停、停牌等约束）
- 同一套策略逻辑可分别落地到回测（`strategy/backtrade`）与实盘（`strategy/online`）
- 生产 / 测试环境隔离（`config/cons.py` 中 `MODE`：`SIMU` 模拟实盘 / `LIVE` 实盘）
- 飞书通知、定时任务脚本，便于云服务器上日频自动运行

您可以参考本项目，将离线验证过的策略平滑迁移到模拟实盘与实盘。


## 功能
- **历史数据本地化**：下载日线行情、市值、ST/停牌、TTM 等，落库至 `buffer/db`
- **离线回测**：基于本地数据库的日频回测，输出收益、最大回撤、夏普、Calmar、费用等指标
- **模拟实盘 / 实盘**：掘金定时调度，日频生成订单并下单
- **自动打新**：可开启新股 / 新债申购（`config/cons.py` 中 `IPO` 开关）
- **策略示例**：小市值 Demo（全市场按总市值升序，轮动 Top10）
- **交易执行**：订单管理、涨跌停校验、持仓与资金查询
- **滑点统计**：成交相对开盘价的买卖滑点、个股明细，以及近 N 日完成度 / 滑点汇总（可推送飞书）
- **飞书通知**：交易进展、持仓明细、回测结果推送
- **行情与基本面**：实时股价、天级别基本面；可继续接入掘金 / akshare 等 API 扩展

## 目录结构（核心）
```
CTBZStock/
├── config/                 # 配置（cons_exam.py 为模板，复制为 cons.py）
├── dataset/                # 数据下载、本地库、行情访问
├── system/                 # 离线回测引擎 Simulation
├── strategy/
│   ├── backtrade/          # 回测策略
│   └── online/             # 实盘 / 模拟实盘策略
├── transaction/            # 下单与成交触发
├── main/
│   ├── update_data/        # 数据下载入口
│   ├── back_test/          # 离线回测入口
│   └── mtv/                # 模拟实盘 / 实盘入口
├── tool/                   # Windows 定时任务启动脚本
├── third_part/             # 飞书等第三方封装
└── doc/                    # 配置文档
```

## 快速开始

### 1. 环境与配置
- 系统：Windows / Windows Server（受券商客户端限制）
- Python：3.10+
- 依赖安装：
```bash
pip install -r requirements.txt
```
- 复制配置模板并填写掘金 `STRATEGY_ID`、`TOKEN`、飞书相关项：
```bash
copy config\cons_exam.py config\cons.py
```
- `config/cons.py` 中关键项：
  - `MODE = Mode.SIMU`：模拟实盘；`Mode.LIVE`：实盘
  - `MTV_SWITCH` / `REPORT_SWITCH`：策略调度与飞书汇报开关

更完整的模拟实盘部署步骤见：[模拟实盘配置攻略](doc/模拟实盘配置攻略.md)

### 2. 数据下载入口
需先在掘金侧准备好数据更新用的 strategy / token（写入 `cons.py` 的 `DATA_UPDATE_STRATEGY_ID`、`TOKEN`）。

| 入口 | 说明 |
|------|------|
| `main/update_data/offline_download.py` | 全量 / 长区间历史数据下载，写入 `buffer/db` |
| `main/update_data/online_update.py` | 增量更新（按交易日追更），适合日常定时跑 |
| `tool/download_data.sh` | 增量更新 + 当日回测的组合脚本示例 |

示例：
```bash
cd main/update_data
python offline_download.py   # 首次建库 / 补历史
python online_update.py      # 日常增量
```

### 3. 离线回测入口
回测依赖本地库 `buffer/db`，策略实现见 `strategy/backtrade/small_cap_demo.py`（继承 `system.simulation.Simulation`）。

| 入口 | 说明 |
|------|------|
| `main/back_test/offline_test.py` | 长周期离线回测（可改 `start_year` / `end_year`） |
| `main/back_test/run.py` | 当年至今回测，并可按开关推送飞书摘要 |

示例：
```bash
cd main/back_test
python offline_test.py   # 长周期回测
python run.py            # 当年回测 + 可选飞书通知
```

回测引擎会统计年化收益、最大回撤、夏普、Calmar、交易成本等，并支持涨跌停、停牌、ST、上市不满期等过滤逻辑。

### 4. 模拟实盘 / 实盘入口
实盘策略逻辑见 `strategy/online/small_cap_demo.py`，由定时任务调度执行。

| 入口 | 说明 |
|------|------|
| `main/mtv/cronjob.py` | 模拟实盘 / 实盘主入口（掘金 `MODE_LIVE` 调度） |
| `tool/mtv.sh` | 一键启动上述 cronjob 的 shell 示例 |
| `tool/run_exe.sh` / `tool/shutdown.sh` | 启动 / 关闭掘金客户端（配合 Windows 任务计划） |

示例：
```bash
cd main/mtv
python cronjob.py
```

或通过任务计划调用 `tool/mtv.sh`。运行前请确认：
1. 掘金客户端已登录对应账户  
2. `config/cons.py` 中 `STRATEGY_ID`、`TOKEN`、`MODE` 正确  
3. 模拟与实盘建议使用不同配置 / 账户，避免误操作  

## 策略开发建议
1. 在 `strategy/backtrade/` 编写并离线回测验证  
2. 将选股 / 调仓逻辑同步到 `strategy/online/`  
3. 先用 `MODE = Mode.SIMU` 跑模拟实盘，观察飞书汇报与成交  
4. 确认无误后再切换 `MODE = Mode.LIVE`  

Demo 策略（小市值轮动）已同时提供回测版与实盘版，可作为模板对照修改。

## 声明
- 本项目不构成任何投资建议，不做股票推荐
- 本项目受众为业余量化爱好者，中低频交易，非专业投资，非高频量化
- 模拟实盘和实盘仍存在不少差异，实盘需谨慎，盈亏请自负

## 合作方
- [掘金量化](https://www.myquant.cn/) · [万和证券](https://whzq.com.cn) · [信达证券](https://www.cindasc.com/)

## 相关资料
- [掘金量化 Python API 文档](https://www.myquant.cn/docs2/sdk/python/%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B.html)
- [akshare 股市数据获取 Python 三方库](https://github.com/akfamily/akshare)

## 联系我们
- 共同参与策略开发，贡献开源社区，可联系 QQ 88256630（请备注来意）
