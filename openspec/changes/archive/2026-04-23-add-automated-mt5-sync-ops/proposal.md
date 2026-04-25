## 背景与原因

这个 change 启动时，仓库的主要缺口是“同步 worker 已能跑，但还没有适合长期无人值守的自动化运行层”。随着实现推进，核心能力实际上已经基本落地：

- `mt5_notion_sync.py` 已提供结构化 `run_sync()` 结果，能够返回退出码、摘要、账户失败数和起止时间
- `tools/sync_job_runner.py` 已具备 profile 解析、预检、单实例锁、状态文件、health-check 和可选 webhook 告警
- Notion 请求已经有针对瞬时错误的有限重试
- 自动化相关回归测试已经覆盖了大部分主路径

当前真正剩下的不是“从零设计自动化运行层”，而是把这套能力收口成可交付、可使用、可维护的入口：补齐计划任务包装脚本、完善示例配置与文档，并解决一处测试与实现的重试语义分歧。

## 变更内容

- 保留现有 Python orchestration 方案，继续以 `tools/sync_job_runner.py` 作为自动化运行核心入口。
- 补齐面向 Windows Task Scheduler 的薄包装脚本 `bin/run_mt5_sync.ps1`，把仓库根目录、Python 解释器与 profile / `health-check` 参数固定下来。
- 更新 README、示例配置和本地状态文件约定，使用户能够直接配置 `incremental` / `reconcile` 两类计划任务，以及独立的健康检查任务。
- 将 Notion 重试语义明确为：`NOTION_HTTP_RETRY_BACKOFF_SECONDS=0` 表示“立即重试”，而不是强制调用 `sleep(0)`；测试需要与这一语义对齐。
- 将本次 change 的任务描述从“构建自动化核心”收敛为“完成包装、文档和验证收口”，避免 artifacts 与仓库现实继续偏离。

## 能力范围

### 新增能力
- `mt5-sync-automation`: 提供适用于计划任务的自动执行入口、单实例保护、运行状态记录、健康检查和失败告警语义。

### 修改能力
<!-- 当前无；本次主要是把已实现能力补齐交付外壳与文档。 -->

## 影响评估

受影响内容将主要集中在自动化运行的交付外壳，而不是再引入一轮新的核心架构变更。预计涉及：

- 计划任务包装脚本 `bin/run_mt5_sync.ps1`
- 项目配置样例 `.env.example`
- 本地运行产物忽略规则 `.gitignore`
- 项目使用文档 `README.md`
- 与重试语义相关的测试说明或断言

对外依赖的边界保持不变：仍然依赖 Windows Task Scheduler、本地文件系统、MT5 终端和 Notion API。变化点在于这些依赖会被更加明确地编排、记录和说明。
