## ADDED Requirements

### Requirement: The automation entrypoint MUST support named sync profiles
自动化运行入口 MUST 支持命名 profile，并对不同 profile 应用稳定、可复现的同步参数组合。

#### Scenario: Incremental profile favors fast high-frequency syncing
- **WHEN** 计划任务以 `incremental` profile 调用自动化入口
- **THEN** 系统 MUST 以适合高频增量同步的参数运行主同步 worker
- **AND** 该 profile MUST 跳过 `MAE/MFE` 回填以降低单轮耗时

#### Scenario: Reconcile profile favors backfill and repair
- **WHEN** 计划任务以 `reconcile` profile 调用自动化入口
- **THEN** 系统 MUST 以适合修补已有记录的参数运行主同步 worker
- **AND** 该 profile MUST 允许更新已有 Notion 页面并执行 `MAE/MFE` 回填

### Requirement: The automation entrypoint MUST fail fast on preflight errors
自动化运行入口 MUST 在调用主同步 worker 之前完成最基本的预检，并在关键前置条件不满足时立即失败。

#### Scenario: Missing local configuration stops the run before MT5 syncing
- **WHEN** 仓库根目录下缺少 `.env`、账户文件或其他自动运行所需的本地配置
- **THEN** 自动化入口 MUST 在启动主同步 worker 之前退出失败
- **AND** 失败原因 MUST 写入结构化运行状态

#### Scenario: Invalid automation profile is rejected
- **WHEN** 调用方传入未定义的 profile 名称
- **THEN** 自动化入口 MUST 拒绝执行该次同步
- **AND** 系统 MUST 返回非零退出码

### Requirement: The automation entrypoint MUST enforce a single active sync run
自动化运行入口 MUST 提供单实例保护，避免多个计划任务实例并发执行同一套 MT5 -> Notion 同步流程。

#### Scenario: A second scheduler invocation sees an active lock
- **WHEN** 新的自动化运行开始时发现锁文件存在且对应进程仍在运行
- **THEN** 新的运行 MUST 放弃获取锁并立即结束
- **AND** 系统 MUST 将该次结果记录为因锁跳过

#### Scenario: A stale lock is reclaimed
- **WHEN** 自动化入口发现锁文件存在但对应进程已经不存在
- **THEN** 系统 MUST 将该锁视为 stale lock
- **AND** 系统 MUST 接管锁并继续本次运行

### Requirement: Automation runs MUST persist structured run state per profile
每次自动化运行结束后，系统 MUST 将结果写入仓库相对路径的结构化状态文件，并按 profile 记录最近状态。

#### Scenario: Successful sync updates profile state
- **WHEN** 某个 profile 的自动化同步成功完成
- **THEN** 状态文件 MUST 记录该 profile 最近一次开始时间、结束时间和成功时间
- **AND** 状态文件 MUST 记录该次同步的结果统计摘要

#### Scenario: Failed sync keeps the last success timestamp
- **WHEN** 某个 profile 的自动化同步失败
- **THEN** 状态文件 MUST 记录本次失败的结束时间、退出码和失败原因摘要
- **AND** 系统 MUST 保留该 profile 之前最近一次成功同步的时间

### Requirement: The automation layer MUST support offline health checks for stale sync detection
自动化层 MUST 支持不连接 MT5 和 Notion 的健康检查模式，并根据状态文件判断同步是否已经陈旧。

#### Scenario: Health check passes when the latest success is fresh enough
- **WHEN** health-check 模式读取到某个 profile 的 `last_success_at` 仍在配置阈值内
- **THEN** 系统 MUST 返回健康状态
- **AND** health-check MUST NOT 启动主同步 worker

#### Scenario: Health check fails when sync success is stale
- **WHEN** health-check 模式发现某个 profile 的最近成功时间超过配置阈值
- **THEN** 系统 MUST 将该 profile 判定为 stale
- **AND** 系统 MUST 返回非零退出码

### Requirement: Automation runs MUST retry transient Notion failures before failing
自动化运行过程中，系统 MUST 对瞬时 Notion / 网络错误执行有限次数的重试与退避，再决定整轮失败。

#### Scenario: Temporary Notion throttling is retried
- **WHEN** Notion API 返回 `429` 或可恢复的 `5xx` 状态码
- **THEN** 系统 MUST 按配置的重试次数和退避策略重新发起请求
- **AND** 只有在重试耗尽后才可将该请求记为失败

#### Scenario: Permanent authorization errors fail immediately
- **WHEN** Notion API 返回鉴权或配置类错误，例如 `401` 或 `403`
- **THEN** 系统 MUST 不对该请求执行瞬时重试
- **AND** 系统 MUST 直接将该次运行标记为失败并暴露原因

### Requirement: The automation layer MUST support optional alert delivery
自动化层 MUST 在配置了告警 webhook 时，为失败和陈旧同步提供可机器消费的告警事件。

#### Scenario: Failed sync triggers an alert when configured
- **WHEN** 自动化同步失败且配置了告警 webhook
- **THEN** 系统 MUST 向 webhook 发送包含 profile、失败类型和最近成功时间的结构化事件
- **AND** 告警发送失败 MUST NOT 覆盖原始同步失败结果

#### Scenario: Stale health check triggers an alert when configured
- **WHEN** health-check 将某个 profile 判定为 stale 且配置了告警 webhook
- **THEN** 系统 MUST 发送该 profile 已陈旧的告警事件
- **AND** 事件中 MUST 包含健康阈值和最近成功时间
