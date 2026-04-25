## 字段映射（脚本读取）

脚本会读取这个表格来决定把 MT5 数据写到 Notion 的哪个属性里。

修改第二列的 Notion 属性名即可适配你自己的数据库字段（列名必须完全一致，区分大小写与空格）。

| key | Notion 属性名 | 说明 |
|---|---|---|
| symbol | 交易标的 | Title |
| direction | 方向 | Select（多/空） |
| time_utc8 | 交易日期 | Date（UTC+8，含时间） |
| entry_price | 入场价格 | Number |
| exit_price | 实际出场 | Number |
| sl | 止损 | Number |
| tp | 止盈 | Number |
| volume | 仓位 | Number |
| ticket | 订单ID | Number（用于去重） |
| duration_hours | 持仓时长(小时) | Number（可选，保留两位小数） |
| session | 交易时段 | Select（可选：亚洲盘/伦敦盘/纽约盘/其他） |
| realized_pnl | 实现盈亏 | Number（可选，净已实现盈亏 = profit + commission + swap + fee） |
| mae | MAE | Number（可选，最大浮亏点数） |
| mfe | MFE | Number（可选，最大浮盈点数） |
