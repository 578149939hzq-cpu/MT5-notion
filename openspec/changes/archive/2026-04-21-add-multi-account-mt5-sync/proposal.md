## 背景与原因

当前 `mt5_notion_sync.py` 已能将单个 MT5 账户的平仓交易同步到 Notion，并计算 `MAE`、`MFE`、持仓时长与交易时段。但它依赖手动登录或 `.env` 中的单组账户配置，无法在同一次运行中轮询多个交易账户，也无法在 Notion 中区分不同账户来源。

这已经成为继续扩展自动化的主要瓶颈。多账户场景下，脚本需要从仓库外部配置读取账户列表，自动完成 MT5 账户切换，并在每个账户维度执行增量同步、异常隔离和结果归档，否则只能靠人工逐个登录，容易漏同步、误判重复记录，且难以维护。

## 变更内容

- 新增 `accounts.json` 账户配置读取能力，支持从外部 JSON 加载多个 MT5 账户的 `account_name`、`login`、`password`、`server`。
- 将主同步流程重构为“初始化终端一次 + 多账户轮询登录 + 每账户独立拉取成交记录 + 每账户独立写入 Notion”的执行模型。
- 在交易数据模型和 Notion 写入逻辑中新增“所属账户”字段，使用 `account_name` 区分数据来源。
- 为多账户同步增加登录失败跳过、终端联网状态检查、账户切换延迟和逐账户日志记录。
- 保留 Notion 凭据继续从 `.env` 读取，并在文档中明确要求将 `accounts.json` 加入 `.gitignore`。
- 更新测试和项目文档，覆盖多账户配置、账户去重键、轮询流程和新增字段映射。

## 能力范围

### 新增能力
- `multi-account-trade-sync`: 支持从外部账户配置加载多个 MT5 账户，自动轮询登录并将各账户交易按账户维度增量同步到 Notion。

### 修改能力

## 影响评估

受影响的核心代码包括 [`mt5_notion_sync.py`](D:\ClaudeCode\mt5_notion_sync.py) 的 MT5 连接层、交易提取层、Notion 去重与写入层，以及主流程编排。文档层面需要更新 [`README.md`](D:\ClaudeCode\README.md)、[`.env.example`](D:\ClaudeCode\.env.example) 和 [`.gitignore`](D:\ClaudeCode\.gitignore)（如不存在则新增）。测试层面需要扩展 [`tests/test_mt5_notion_sync.py`](D:\ClaudeCode\tests\test_mt5_notion_sync.py) 和必要的新用例，确保多账户轮询、账户标识与增量同步逻辑可回归验证。
