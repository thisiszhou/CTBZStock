<div align="center">

# 【CTBZStock】草台班子量化 
<div>
    <img alt="python" src="https://img.shields.io/badge/python-3.8+-%2300599C?logo=python">
    <img alt="license" src="https://img.shields.io/github/license/thisiszhou/CTBZStock">
    <img alt="stars" src="https://img.shields.io/github/stars/thisiszhou/CTBZStock?style=social">
</div>
 
牛市昙花一现，量化穿越牛熊
  
大A就是一个巨大的草台班子
  
</div>

## 项目介绍
此项目基于券商交易、查询接口进行二次开发，以小市值量化策略为示例，进行A股量化模拟实盘与量化实盘（无回测功能），并提供生产、测试环境隔离方案。
您可以参考此项目，将您离线回测好的策略，轻松开启实盘。

## 功能
- 模拟实盘定期执行策略
- 实盘定期执行策略
- 飞书实时通知交易进展
- 获取实时股价数据
- 获取天级别基本面数据
- 支持接入更多掘金量化API、第三方数据API，自由开发

## 配置教程
- 由于券商客户端限制，本项目仅支持windows、windows server（支持windows云服务器）
- [模拟实盘配置攻略](doc/模拟实盘配置攻略.md)

## 实战成绩
- 本人实盘的策略与项目中DEMO差异很大，请勿以下述结果当作DEMO的实际收益。结果贴在这里仅当作分享，鼓励自己坚持。  

|   年份 |  沪深300  |  本账户收益  |最大回撤 |夏普率|备注
|-----:|:-------:|:-------:|:----:|:------:|:------:|
| 2024 | 14.68%  |  55.41% |46.51%| 1.19 |夏普率符合预期，但是最大回撤太大，太考验心脏



## 声明
- 本项目不构成任何投资建议，不做股票推荐
- 本项目受众为业余量化爱好者，中低频交易，非专业投资，非高频量化
- 模拟实盘和实盘仍存在不少差异，实盘需谨慎，盈亏请自负

## 合作方
- [掘金量化](https://www.myquant.cn/)(模拟实盘、实盘都需要注册掘金量化账号)
- [万和证券](whzq.com.cn)(仅实盘需要开户，模拟实盘不需要)

## 相关资料
- [掘金量化python api文档](https://www.myquant.cn/docs2/sdk/python/%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B.html)
- [akshare 股市数据获取python三方库](https://github.com/akfamily/akshare)

## 联系我们
- 参与讨论可加入QQ群 123155600   (验证消息填写 github 用户名，需要STAR本项目才可入群)
- 共同参与策略开发，贡献开源社区，可联系QQ 88256630 (请备注来意)