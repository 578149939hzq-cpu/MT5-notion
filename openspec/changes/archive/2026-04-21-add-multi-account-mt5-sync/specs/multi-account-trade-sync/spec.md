## ADDED Requirements

### Requirement: The sync script MUST load MT5 accounts from an external accounts file
主同步脚本 MUST 从外部 `accounts.json` 配置文件读取 MT5 账户列表，并校验每个账户都包含 `account_name`、`login`、`password` 和 `server`。

#### Scenario: Valid account configuration is accepted
- **WHEN** 用户提供的 `accounts.json` 是一个数组，且每个对象都包含必需字段
- **THEN** 脚本 MUST 成功加载全部账户配置
- **AND** 每个账户 MUST 保留稳定的 `account_name` 供后续日志、去重和 Notion 写入使用

#### Scenario: Invalid account configuration stops the run before sync
- **WHEN** `accounts.json` 缺失、为空、不是数组，或任一账户缺少必需字段
- **THEN** 脚本 MUST 在开始同步前报错退出
- **AND** 脚本 MUST NOT 进入 MT5 账户轮询流程

### Requirement: The MT5 terminal MUST support sequential multi-account polling
脚本 MUST 在一次运行中初始化 MT5 终端一次，并按配置顺序逐个登录账户执行同步，全部处理完成后再统一关闭终端。

#### Scenario: Accounts are processed in order with isolated failures
- **WHEN** 脚本开始处理一个包含多个账户的配置文件
- **THEN** 脚本 MUST 按 `accounts.json` 中的顺序逐个处理账户
- **AND** 单个账户登录失败或账户级同步异常 MUST 只影响当前账户
- **AND** 脚本 MUST 继续处理后续账户

#### Scenario: The terminal is shut down after polling completes
- **WHEN** 全部账户都已处理完成或被跳过
- **THEN** 脚本 MUST 调用 MT5 终端关闭逻辑一次

### Requirement: Incremental sync MUST be scoped per account
系统 MUST 以账户维度执行增量同步，并基于该账户在 Notion 中最近一次已同步记录来确定抓取起点；如果该账户没有历史记录，则 MUST 回退到默认同步时间窗。

#### Scenario: Existing account records define the next sync window
- **WHEN** Notion 中已经存在某个 `account_name` 的历史交易记录
- **THEN** 脚本 MUST 使用该账户最新已同步交易时间作为增量基准
- **AND** 脚本 MUST 从该时间之前的一个安全回看缓冲开始重新抓取

#### Scenario: New accounts fall back to the default sync window
- **WHEN** Notion 中不存在某个 `account_name` 的历史交易记录
- **THEN** 脚本 MUST 使用当前默认同步窗口抓取该账户最近成交记录

### Requirement: Notion records MUST include account identity and account-scoped deduplication
每一笔同步到 Notion 的交易 MUST 包含“所属账户”字段，且重复判断 MUST 基于 `account_name + ticket` 的组合，而不是只基于 `ticket`。

#### Scenario: Trade creation includes the account field
- **WHEN** 脚本为某笔交易创建 Notion 页面
- **THEN** 页面属性 MUST 包含与 `account_name` 对应的“所属账户”

#### Scenario: Duplicate detection does not collide across accounts
- **WHEN** 两个不同账户存在相同的 `ticket`
- **THEN** 系统 MUST 将它们视为两笔不同交易
- **AND** 只有在 `account_name` 与 `ticket` 同时匹配时，系统才可以判定为重复记录

### Requirement: Account switching MUST enforce connectivity checks and pacing
在账户切换过程中，脚本 MUST 在登录前检查 MT5 终端联网状态，并在两个账户之间加入短暂延迟，降低登录切换失败概率。

#### Scenario: Disconnected terminal prevents the current account from syncing
- **WHEN** 脚本准备登录某个账户前发现 MT5 终端未连接到互联网
- **THEN** 脚本 MUST 记录该账户的错误
- **AND** 脚本 MUST 跳过该账户的同步尝试

#### Scenario: A delay is inserted between account attempts
- **WHEN** 当前账户处理结束且后面仍有待处理账户
- **THEN** 脚本 MUST 在进入下一个账户前等待一个已配置的短暂延迟
