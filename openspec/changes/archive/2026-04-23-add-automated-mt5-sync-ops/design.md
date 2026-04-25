## 背景

当前仓库已经不只是“需要一个自动化运行层”，而是已经拥有了自动化运行层的大部分核心实现：

- `mt5_notion_sync.run_sync()` 已提供结构化运行结果
- `NotionSync._request()` 已提供瞬时错误有限重试
- `tools/sync_job_runner.py` 已提供 run / `health-check`、预检、锁、状态文件和 webhook 告警
- `tests/test_sync_job_runner.py` 已覆盖预检失败、锁跳过、stale lock 接管和 stale health-check 告警

因此，这份设计文档需要从“设计一个未来方案”收敛为“确认当前方案、说明仍需补齐的收尾项”。

```text
Windows Task Scheduler
        |
        v
bin/run_mt5_sync.ps1
        |
        v
tools/sync_job_runner.py
  - profile selection
  - preflight
  - lock acquire/release
  - state read/write
  - health evaluation
  - optional alert webhook
        |
        v
mt5_notion_sync.run_sync()
  - MT5 login / polling
  - Notion sync
  - bounded HTTP retry
```

上面的链路里，目前已经缺的主要是最上层的 `bin/run_mt5_sync.ps1` 包装脚本，以及围绕这条链路的文档/配置说明。

## 目标 / 非目标

**目标：**
- 为 Windows 计划任务补齐稳定的一键入口，固定工作目录与运行参数。
- 把已经存在的自动化能力整理为清晰的使用契约，包括 `incremental` / `reconcile` profile、状态文件位置和 `health-check` 入口。
- 完成文档、配置样例和忽略规则收口，让这套能力能被真实部署，而不是只停留在 Python 脚本层。
- 明确并记录 Notion 重试退避语义，消除测试与实现之间的分歧。

**非目标：**
- 不把同步程序改造成常驻 daemon、Windows Service 或托盘进程。
- 不重写 MT5 成交提取逻辑、MAE/MFE 计算逻辑或 Notion 字段映射模型。
- 不引入数据库、消息队列或外部任务编排系统。
- 不借这次收尾去做大规模模块拆分或结构性重构。

## 设计决策

1. 保持“PowerShell 薄包装 + Python orchestration”二层入口不变。
   Python runner 已经是事实上的核心入口，因此这次不再调整 orchestration 的职责边界。`bin/run_mt5_sync.ps1` 只负责为 Task Scheduler 固定仓库根目录、Python 解释器和 profile / `health-check` 参数，避免把锁、状态和重试逻辑散落在 PowerShell 中。

2. 把现有结构化 `run_sync()` 视为稳定接口，而不是继续讨论是否需要它。
   这一点已经在代码里实现，并且是 runner 写状态文件的基础约束。当前设计只需要说明：CLI 继续保留 `main()` 退出码语义，而自动化层依赖 `run_sync()` 的结构化结果。

3. 继续以 `incremental` 和 `reconcile` 作为唯一受支持的自动运行 profile。
   - `incremental`：高频增量同步，优先快速入库
   - `reconcile`：低频修补同步，优先校正与回填

   文档需要把两者用途讲清楚，避免用户在 Task Scheduler 里自行拼装一套偏离实现的参数组合。

4. 锁、状态和健康检查的现有文件约定继续保留。
   `state/mt5_sync.lock` 与 `state/mt5_sync_status.json` 已经是 runner 的事实约定；这次应补齐 `.gitignore` 和 README，而不是再引入新的状态存储方案。

5. Notion 重试语义以“有界重试 + 可为零的退避”为准。
   当前实现对 `Timeout`、连接错误、`429` 和可恢复的 `5xx` 做有限重试，这个方向不变。需要补记的一条关键决策是：
   - `NOTION_HTTP_RETRY_BACKOFF_SECONDS=0` 表示立即重试
   - 不要求显式调用 `sleep(0)`

   也就是说，测试应该断言“发生过重试”，而不是断言“即使零退避也必须调用一次 sleep”。

6. webhook 继续保持为单一、可选、非阻断型告警出口。
   告警发送失败只记录 warning，不覆盖同步结果。这一点已经在 runner 中成立，本次只需要把外部契约讲清楚。

## 风险 / 权衡

- `mt5_notion_sync.py` 仍然是单文件核心 worker，内部职责偏重的问题还在，但这不是本次收尾要解决的范围。
- 自动化能力已经先于文档落地，当前最大风险不是“功能不存在”，而是“用户无法按正确方式使用已有功能”。
- 如果不显式记录零退避语义，测试和实现会继续相互拉扯，降低后续维护信心。

## 迁移计划

1. 新增 `bin/run_mt5_sync.ps1`，把现有 runner 暴露给 Windows Task Scheduler。
2. 扩展 `.env.example`，补充 webhook、stale threshold 与计划任务相关示例变量。
3. 更新 `.gitignore`，忽略 `state/` 运行产物。
4. 更新 README，说明 profile、`health-check`、状态文件和 Task Scheduler 配置方式。
5. 对齐 Notion 重试测试与实现语义，并完成最终回归验证。

## 待确认问题

- 暂无新的架构级待确认项；本次以收尾交付为主。
