# 手动同步速查

这页只解决一个问题：

- 你平时手动跑同步时，固定该用哪条命令

## 以后优先用这 3 个脚本

都在 `bin/` 里：

- [sync_incremental.ps1](/D:/Trading_data_notion/bin/sync_incremental.ps1)
- [sync_reconcile.ps1](/D:/Trading_data_notion/bin/sync_reconcile.ps1)
- [sync_health_check.ps1](/D:/Trading_data_notion/bin/sync_health_check.ps1)

## 1. 快速增量同步

适合：

- 日常手动跑一次
- 优先把新成交尽快同步进 Notion
- 暂时不做 `MAE/MFE` 回填

命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\bin\sync_incremental.ps1
```

它实际等价于：

```powershell
powershell -ExecutionPolicy Bypass -File .\bin\run_mt5_sync.ps1 -Profile incremental
```

代码里这个 profile 的含义是：

- `skip_mae_mfe = true`

也就是更偏“快”。

## 2. 修补/补算同步

适合：

- 需要回填 `MAE/MFE`
- 需要更新已存在记录
- 想做一次更完整的修补

命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\bin\sync_reconcile.ps1
```

它实际等价于：

```powershell
powershell -ExecutionPolicy Bypass -File .\bin\run_mt5_sync.ps1 -Profile reconcile
```

代码里这个 profile 的含义是：

- `skip_mae_mfe = false`
- `update_existing = true`

也就是更偏“补齐和修正已有数据”。

## 3. 只做健康检查

适合：

- 只想看最近一次成功同步是否过旧
- 不想连接 MT5
- 不想连接 Notion

命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\bin\sync_health_check.ps1
```

或者检查 `reconcile`：

```powershell
powershell -ExecutionPolicy Bypass -File .\bin\sync_health_check.ps1 -Profile reconcile
```

这个命令只读状态文件，不会真正跑同步。

## 你平时怎么选

### 日常默认

```powershell
powershell -ExecutionPolicy Bypass -File .\bin\sync_incremental.ps1
```

### 发现有记录不完整、想补齐

```powershell
powershell -ExecutionPolicy Bypass -File .\bin\sync_reconcile.ps1
```

### 不确定最近有没有跑成功

```powershell
powershell -ExecutionPolicy Bypass -File .\bin\sync_health_check.ps1
```

## 如果你已经在仓库根目录的 PowerShell 里

也可以直接：

```powershell
.\bin\sync_incremental.ps1
.\bin\sync_reconcile.ps1
.\bin\sync_health_check.ps1
```

如果本机执行策略拦截，再用上面的 `powershell -ExecutionPolicy Bypass -File ...` 形式。

## 这些脚本不会做什么

- 不会自动创建计划任务
- 不会把手动模式改成后台常驻模式
- 不会移除现有自动化设计

它们只是把你手动常用的 3 个入口单独拆出来，减少记忆负担。

## 相关文件

- 包装入口：[run_mt5_sync.ps1](/D:/Trading_data_notion/bin/run_mt5_sync.ps1)
- Runner：[sync_job_runner.py](/D:/Trading_data_notion/tools/sync_job_runner.py)
- 旧的完整说明：[README.md](/D:/Trading_data_notion/README.md)
