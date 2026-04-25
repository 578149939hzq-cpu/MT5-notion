## ADDED Requirements

### Requirement: Shareable repository files must not contain live credentials
仓库中允许被分享、提交或作为示例保留的配置文件 MUST 只包含占位符或假数据，而不能包含真实 MT5 或 Notion 凭据。

#### Scenario: Example account file is safe to share
- **WHEN** 用户打开或复制 `accounts.example.json`
- **THEN** 该文件 MUST 只包含示例性的 `account_name`、`login`、`password` 与 `server`
- **AND** 这些值 MUST NOT 可直接用于登录真实账户

#### Scenario: Archived scripts do not preserve hardcoded production identifiers
- **WHEN** 用户浏览 `archive/` 目录中的历史脚本
- **THEN** 这些脚本 MUST NOT 携带硬编码的生产数据库标识或其他敏感配置值

### Requirement: Runtime logs must minimize sensitive exposure
主同步脚本的默认日志 MUST 提供足够的排查信息，但 MUST NOT 回显完整敏感标识。

#### Scenario: Account progress is logged without raw MT5 identifiers
- **WHEN** 主同步脚本初始化 MT5、切换账户或完成账户级同步
- **THEN** 日志 MUST 能标识当前处理的逻辑账户
- **AND** 日志 MUST NOT 输出完整 MT5 登录号、账户余额或终端数据路径

#### Scenario: Configuration errors do not echo secret-like values
- **WHEN** 主同步脚本发现缺少 Notion 或 MT5 配置
- **THEN** 错误信息 MAY 指向缺少的环境变量名称或配置文件位置
- **AND** 错误信息 MUST NOT 打印 token、密码或完整数据库标识

### Requirement: Diagnostic tools must report status without echoing secrets
诊断工具 MUST 帮助用户判断配置是否存在、客户端是否可连接，但 MUST NOT 通过终端输出回显敏感值本身。

#### Scenario: Notion diagnostics confirm configuration without printing identifiers
- **WHEN** 用户运行 Notion 相关诊断工具
- **THEN** 工具 MUST 报告 `NOTION_TOKEN` 与 `DATABASE_ID` 是否已配置
- **AND** 工具 MUST NOT 打印完整 token、token 前缀或完整数据库 ID

#### Scenario: MT5 diagnostics fail safely when credentials are missing
- **WHEN** 用户运行需要 MT5 登录配置的诊断工具但本地环境变量缺失
- **THEN** 工具 MUST 明确指出缺少哪些环境变量
- **AND** 工具 MUST 安全退出，而不是尝试使用默认值或历史残留配置

### Requirement: Documentation must distinguish private local config from shareable examples
项目文档 MUST 清楚区分本地私有配置与允许进入仓库的示例文件，降低误提交和误分享风险。

#### Scenario: README explains the local-private workflow
- **WHEN** 用户根据 README 配置项目
- **THEN** 文档 MUST 指引用户从示例文件复制出本地私有配置
- **AND** 文档 MUST 明确说明 `.env` 与 `accounts.json` 不应提交
- **AND** 文档 SHOULD 提醒用户历史日志可能包含旧敏感信息，不应直接分享
