# MT5 多账户 Notion 同步

将 MT5 已平仓交易按账户维度同步到 Notion，支持：

- 从 `accounts.json` 读取多个 MT5 账户
- 单次启动 MT5 终端后按顺序轮询登录各账户
- 按“所属账户 + 订单ID”做增量同步与去重
- 可选同步已实现盈亏、`MAE`、`MFE`、持仓时长、交易时段
- 首轮同步时自动兼容 Notion `所属账户` 还没有对应选项的情况
- MT5 终端离线或登录 IPC 异常时自动重连并重试一次
- 同一轮运行内如果 MT5 或网络重试重复返回同一 `所属账户 + 订单ID`，脚本会先在本地拦截，避免因为 Notion 查询延迟而重复创建

## 最新状态

- `2026-04-22` 已完成首轮真实多账户同步检查
- 快速同步模式 `SKIP_MAE_MFE=1` 实跑结果：`created=1 updated=7 duplicate=0 failed=0 account_failures=0`
- 如果要补齐 `MAE/MFE`，重新运行脚本且不要带 `SKIP_MAE_MFE`
- 已实现盈亏会自动从 MT5 平仓成交同步到 Notion 数字字段
- `2026-04-25 22:00` 本机计划任务触发了一次 `incremental` 自动同步，`state/mt5_sync_status.json` 记录结果为 `success`
- 该次自动同步的最新汇总为：`created=1 updated=0 duplicate=7 failed=0 account_failures=0`
- 本机当前保留了一条名为 `MT5 Notion Sync Daily` 的计划任务；如果你看到晚上 22:00 左右自动弹出终端，优先去 Windows Task Scheduler 检查这条任务

## 安装

```bash
python -m pip install -r requirements.txt
```

## 配置

1. 复制 [`.env.example`](/D:/Trading_data_notion/.env.example) 为 `.env`
2. 填写 `NOTION_TOKEN` 和 `DATABASE_ID`
3. 复制 [`accounts.example.json`](/D:/Trading_data_notion/accounts.example.json) 为 `accounts.json`
4. 在 `accounts.json` 中填写你的 MT5 账户列表
5. 确保 Notion 数据库中存在“所属账户”字段，类型为 `select`

主同步脚本会从项目根目录解析 `.env`、`accounts.json`、日志目录和映射文件路径，因此从其他工作目录启动也会使用当前项目配置。

如果你的真实账户文件不叫 `accounts.json`，可以通过 `ACCOUNTS_FILE` 指向其他路径，但默认一键运行仍然读取项目根目录下的 `accounts.json`。

`accounts.example.json` 必须始终保持为示例文件，不要把真实 MT5 凭据写回示例文件。

`.env` 和 `accounts.json` 都属于本地私有配置；如果要分享配置结构，只分享 `*.example.*` 文件。

后续做维护、清理或安全整改时，不要删除、覆盖、重置或改动你本地的 `accounts.json`；除非你明确要求，否则必须完全保持原样。

## accounts.json 格式

```json
[
  {
    "account_name": "Example-Account-A",
    "login": 123456,
    "password": "replace-with-your-mt5-password-a",
    "server": "Your-Server-A"
  },
  {
    "account_name": "Example-Account-B",
    "login": 789012,
    "password": "replace-with-your-mt5-password-b",
    "server": "Your-Server-B"
  }
]
```

`account_name` 会直接写入 Notion 的“所属账户”字段，同时也是去重和增量同步的账户标识。不要随意修改历史账户的 `account_name`。

## Notion 字段要求

默认映射文件仍然读取 `Claude.md` 或 `claude.md`。除原有字段外，多账户同步新增：

- `所属账户`: `select`
- `实现盈亏`: `number`，可选

主脚本会校验 Notion 字段是否存在且类型匹配；如果缺失，会在启动时直接报错。

如果某个账户的 `account_name` 还没有出现在 Notion 的 `所属账户` 选项中，脚本会把该账户视为“首次同步、暂无历史记录”，而不是因为查询失败中断整轮同步。

`实现盈亏` 使用 MT5 平仓成交的净值计算：`profit + commission + swap + fee`。如果你的 Notion 字段名不同，修改 [Claude.md](/D:/Trading_data_notion/Claude.md) 对应的 `realized_pnl` 行即可。

## 运行同步

标准运行：

```bash
python mt5_notion_sync.py
```

快速运行，临时跳过 `MAE/MFE` 回填：

```powershell
$env:SKIP_MAE_MFE='1'
python mt5_notion_sync.py
Remove-Item Env:SKIP_MAE_MFE -ErrorAction SilentlyContinue
```

说明：

- `SKIP_MAE_MFE=1` 只影响当前运行，用于首轮快速同步或排查 MT5 历史拉取过慢的问题
- 后续如果要补齐 `MAE/MFE`，重新运行脚本且不要设置 `SKIP_MAE_MFE`
- 如果要把重复订单上的 `MAE/MFE` 或其他字段补回已有页面，请确保 `UPDATE_EXISTING=1`
- 已实现盈亏不受 `SKIP_MAE_MFE` 影响，正常同步时会始终写入或更新

脚本流程：

1. 加载 `.env` 和 `accounts.json`
2. 连接 Notion
3. 初始化 MT5 终端一次
4. 按账户顺序执行联网检查、登录、增量成交提取、指标计算和 Notion 写入
5. 如果 MT5 终端离线或登录失败，脚本会尝试重启终端并重试一次
6. 所有账户处理完成后执行 `mt5.shutdown()`

## 计划任务自动化

自动化入口分两层：

- PowerShell 薄包装：[`bin/run_mt5_sync.ps1`](/D:/Trading_data_notion/bin/run_mt5_sync.ps1)
- Python orchestration：[`tools/sync_job_runner.py`](/D:/Trading_data_notion/tools/sync_job_runner.py)

推荐优先让 Windows Task Scheduler 调用 PowerShell 包装脚本，它会固定仓库根目录，再把命令转发给 Python runner。

这个仓库提供的是“可被计划任务调用的入口”，不会自行创建、停用或删除 Windows 计划任务；计划任务本身仍然是机器上的本地系统配置。

当前这台机器上已验证的任务行为：

- 任务名是 `MT5 Notion Sync Daily`
- 触发器是 `Daily`，当前配置为每天 `22:00`
- 该任务现在已明确设置为 `WakeToRun=False`，不会为了同步主动唤醒电脑
- 该任务现在也已设置为 `StartWhenAvailable=False`，如果错过 `22:00`，之后开机不会自动补跑
- 因此它只会在电脑当时已经开机且处于可运行状态时执行；如果那一刻电脑休眠、关机或不可运行，本次任务会直接跳过

常用命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\bin\run_mt5_sync.ps1 -Profile incremental
powershell -ExecutionPolicy Bypass -File .\bin\run_mt5_sync.ps1 -Profile reconcile
powershell -ExecutionPolicy Bypass -File .\bin\run_mt5_sync.ps1 -Command health-check -Profile incremental
```

如果你想直接调试 runner，也可以直接执行：

```bash
python tools/sync_job_runner.py run --profile incremental
python tools/sync_job_runner.py run --profile reconcile
python tools/sync_job_runner.py health-check --profile incremental
```

两个 profile 的用途：

- `incremental`：高频增量同步，强制 `SKIP_MAE_MFE=1`，优先让新成交尽快进入 Notion
- `reconcile`：低频修补同步，强制 `UPDATE_EXISTING=1`，适合回填 `MAE/MFE` 和校正已有记录

runner 会在项目根目录下写入本地状态文件：

- `state/mt5_sync.lock`：单实例锁，避免计划任务重叠执行
- `state/mt5_sync_status.json`：按 profile 记录最近一次运行结果和最近一次成功时间

`health-check` 只读取状态文件，不连接 MT5 或 Notion。适合单独配一个计划任务，专门检查“最近一次成功同步是否已经过旧”。
排查“脚本是不是自己跑了”时，先看两处：Windows Task Scheduler 的任务历史，以及 `state/mt5_sync_status.json` 里的最近一次运行时间和结果。

推荐的 Task Scheduler 拆分方式：

1. `incremental`：每 5-15 分钟运行一次
2. `reconcile`：每天运行 1-2 次
3. `health-check`：每 10-15 分钟运行一次

如果配置了 `SYNC_ALERT_WEBHOOK_URL`，runner 会在以下场景发送 JSON POST 告警：

- 预检失败
- 同步失败
- `health-check` 判断 stale

## 增量同步与去重规则

- 每个账户都会先查询 Notion 中该“所属账户”的最新已同步交易时间
- 如果找到了历史记录，则从“最新时间 - `SYNC_LOOKBACK_MINUTES`”开始重扫
- 如果该账户在 Notion 中还没有记录，则退回到默认同步窗口
- 重复判断使用“所属账户 + 订单ID”，因此允许安全地重扫一小段重叠区间
- 同一轮运行内如果 MT5 或网络重试导致同一 `所属账户 + 订单ID` 被重复返回，脚本会先在本地拦截

重复记录处理方式：

- `UPDATE_EXISTING=1`：如果同一 `所属账户 + 订单ID` 已存在，则更新已有页面
- `UPDATE_EXISTING=0`：如果同一 `所属账户 + 订单ID` 已存在，则跳过该重复订单

默认同步窗口优先级：

- `SYNC_THIS_WEEK`
- `SYNC_MONTHS`
- `SYNC_DAYS`
- `SYNC_HOURS`

## 关键环境变量

常用配置如下，完整入口见 [`.env.example`](/D:/Trading_data_notion/.env.example)：

- `NOTION_TOKEN`
- `DATABASE_ID`
- `ACCOUNTS_FILE`
- `MAPPING_FILE`
- `UPDATE_EXISTING`
- `SKIP_MAE_MFE`
- `NOTION_SYNC_DELAY_SECONDS`
- `NOTION_HTTP_TIMEOUT_SECONDS`
- `NOTION_HTTP_MAX_RETRIES`
- `NOTION_HTTP_RETRY_BACKOFF_SECONDS`
- `SYNC_LOOKBACK_MINUTES`
- `ACCOUNT_SWITCH_DELAY_SECONDS`
- `SYNC_HOURS` / `SYNC_DAYS` / `SYNC_MONTHS` / `SYNC_THIS_WEEK`
- `SYNC_ALERT_WEBHOOK_URL`
- `SYNC_HEALTH_STALE_MINUTES_INCREMENTAL`
- `SYNC_HEALTH_STALE_MINUTES_RECONCILE`

说明：

- 主同步脚本默认使用 `accounts.json`，不再依赖 `.env` 中的单账户 MT5 配置
- `UPDATE_EXISTING=1` 更适合需要回填 `MAE/MFE`、交易时段或持仓时长的场景
- `UPDATE_EXISTING=1` 同样适合给已有记录补写或修正“实现盈亏”
- `NOTION_HTTP_RETRY_BACKOFF_SECONDS=0` 表示立即重试，不额外等待退避时间
- `SYNC_ALERT_WEBHOOK_URL` 用于接收自动化失败/陈旧同步告警；发送失败不会覆盖主任务退出码
- `SYNC_HEALTH_STALE_MINUTES_INCREMENTAL` 和 `SYNC_HEALTH_STALE_MINUTES_RECONCILE` 控制 `health-check` 的陈旧阈值
- `MT5_ACCOUNT`、`MT5_PASSWORD`、`MT5_SERVER` 仍保留给 `tools/` 下的单账户诊断脚本使用

## 诊断脚本

常用入口：

- `python tools/test_connection.py`
- `python tools/check_mt5_settings.py`
- `python tools/diagnose_mt5_history.py`
- `python tools/test_notion_connection.py`

这些脚本仍然使用 `.env` 中的单账户 MT5 配置做诊断，不参与多账户轮询。

诊断工具现在默认只报告“是否已配置”和“是否可连接”，不再回显 token 前缀、完整数据库 ID、完整 MT5 登录号或账户余额。

## 测试

项目中已补充多账户配置、账户维度去重、增量窗口、轮询容错和安全脱敏相关回归用例。

当前测试命令：

```bash
python -m unittest discover -s tests -v
```

## 安全建议

- 将 `accounts.json` 加入 `.gitignore`
- 不要把真实 MT5 账号密码提交到仓库，也不要把真实数据写进 `accounts.example.json`
- `.env` 和 `accounts.json` 只用于本地私有配置
- `archive/` 目录下的脚本仅作为历史参考，当前推荐入口始终是根目录下的 `mt5_notion_sync.py`
- 如果你要分享排查材料，先检查历史 `logs/*.log`，旧日志里可能包含安全收口前留下的敏感信息
