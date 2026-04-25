## 1. Worker 结果与请求韧性

- [x] 1.1 从 `mt5_notion_sync.py` 中提炼结构化运行结果入口，返回退出码、同步统计、账户失败数和错误摘要，保留现有 CLI 退出语义
- [x] 1.2 为 Notion `GET/POST/PATCH` 请求增加共享的有限重试与退避包装，只重试瞬时网络错误、`429` 和可恢复的 `5xx`
- [x] 1.3 为自动运行 profile 增加统一参数覆盖语义，至少支持 `incremental` 与 `reconcile`

## 2. 自动运行 orchestration

- [x] 2.1 新增 Python 自动运行入口，完成 profile 解析、预检、主同步调用和按 profile 的状态文件读写
- [x] 2.2 为自动运行入口实现单实例锁、stale lock 接管和“因锁跳过”结果落盘
- [x] 2.3 为自动运行入口实现独立 health-check 模式，并基于最近成功时间判断 profile 是否 stale
- [x] 2.4 在配置了 webhook 时，为预检失败、同步失败和 stale health-check 发送结构化告警，且不覆盖原始任务结果

## 3. 计划任务集成与回归保护

- [ ] 3.1 新增面向 Windows Task Scheduler 的 PowerShell 薄包装入口 `bin/run_mt5_sync.ps1`
- [ ] 3.2 更新 `.env.example`、`.gitignore` 和 `README.md`，说明 profile、`health-check`、webhook、`state/` 产物与计划任务配置方式
- [ ] 3.3 对齐 Notion 重试退避测试与实现语义，明确 `NOTION_HTTP_RETRY_BACKOFF_SECONDS=0` 表示立即重试，并完成最终回归验证
