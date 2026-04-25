# 常用 Slash Commands

这份表只保留真正高频的命令。完整清单见官方：
<https://developers.openai.com/codex/cli/slash-commands>

## 先记住这 10 个

| 命令 | 作用 | 什么时候用 | 常见写法 |
| --- | --- | --- | --- |
| `/status` | 看当前会话配置 | 进仓库后先确认模型、权限、可写目录 | `/status` |
| `/permissions` | 调整权限和审批 | 想临时放宽或收紧权限 | `/permissions` |
| `/plan` | 先出计划再动手 | 复杂任务、改动大、需求还不清楚 | `/plan` |
| `/mention` | 显式挂入文件或目录 | 不想让 Codex 猜文件位置 | `/mention src/app.py` |
| `/diff` | 看 Git diff | 改完后检查改动范围 | `/diff` |
| `/review` | 审查当前工作区 | 想让 Codex 从 review 视角找问题 | `/review` |
| `/compact` | 压缩长上下文 | 聊很久后避免上下文膨胀 | `/compact` |
| `/fork` | 分叉当前线程 | 想试另一条方案，但不丢当前思路 | `/fork` |
| `/resume` | 恢复旧会话 | 隔一段时间继续同一任务 | `/resume` |
| `/init` | 生成 `AGENTS.md` 骨架 | 新仓库准备长期规则 | `/init` |

## 会话控制

| 命令 | 作用 | 说明 |
| --- | --- | --- |
| `/status` | 查看当前会话状态 | 能看到 active model、approval policy、writable roots、context 使用情况 |
| `/model` | 切换模型 | 切模型后，建议再跑一次 `/status` 确认 |
| `/fast` | 打开或关闭 Fast mode | 适合速度优先的会话 |
| `/personality` | 调整输出风格 | 不改变任务本身，只改变表达风格 |
| `/plan` | 进入 Plan mode | 复杂任务先计划，通常比直接让它写代码更稳 |
| `/new` | 在同一个 CLI 会话里开新对话 | 不退出终端，但清空聊天上下文 |
| `/clear` | 清屏并开始新对话 | 和 `/new` 类似，但连界面一起清 |
| `/resume` | 恢复历史会话 | 适合断点续做 |
| `/fork` | 复制当前会话为新线程 | 适合试不同策略 |

## 文件和代码审查

| 命令 | 作用 | 说明 |
| --- | --- | --- |
| `/mention` | 把文件或目录挂入当前对话 | 明确上下文，减少“猜错文件” |
| `/diff` | 展示 Git diff | 包括未跟踪文件 |
| `/review` | 让 Codex 审查工作树 | 官方定位就是 review 当前改动 |
| `/copy` | 复制上一条已完成输出 | 等价于快速拷贝结果 |
| `/compact` | 压缩历史上下文 | 长对话必备 |

## 权限、环境和工具

| 命令 | 作用 | 说明 |
| --- | --- | --- |
| `/permissions` | 切换审批/权限模式 | 中途觉得太保守或太激进时用 |
| `/debug-config` | 看 config 层级和生效来源 | 配置不生效时非常有用 |
| `/mcp` | 列出可用 MCP 工具 | 看当前会话能调用哪些外部工具 |
| `/apps` | 浏览可用 apps/connectors | 需要连接外部系统时用 |
| `/plugins` | 浏览可用插件 | 看安装状态、开关状态 |
| `/statusline` | 配置底部状态栏 | 偏 UI 定制 |
| `/title` | 配置终端标题 | 偏 UI 定制 |

## 线程和后台任务

| 命令 | 作用 | 说明 |
| --- | --- | --- |
| `/agent` | 切换 agent thread | 在多 agent 场景里切线程 |
| `/ps` | 查看后台终端 | 适合看长跑命令进度 |
| `/stop` | 停掉后台终端 | 中止当前 session 的后台任务 |

## 登录、退出和诊断

| 命令 | 作用 | 说明 |
| --- | --- | --- |
| `/feedback` | 提交日志和诊断 | 报问题给维护方 |
| `/logout` | 清理登录状态 | 共享机器上很有用 |
| `/quit` `/exit` | 退出 CLI | 两者等价 |

## Windows 特有命令

| 命令 | 作用 | 说明 |
| --- | --- | --- |
| `/sandbox-add-read-dir C:\\path` | 给沙箱额外读权限 | 只在原生 Windows CLI 下可用 |

## 常见组合

### 进仓库后的最小动作

```text
/status
```

看 4 件事：

- 当前模型
- 当前 approval policy
- 当前 sandbox mode
- 当前 writable roots

### 复杂任务

```text
/plan 为这个改动先列一份执行计划，只做分析，不写代码
```

然后再决定是否继续。

### 精准指定上下文

```text
/mention openspec
/mention README.md
/mention tools/sync_job_runner.py
```

比直接说“看看这个项目”更稳定。

### 改完代码后的收尾

```text
/diff
/review
```

推荐顺序：

1. 先 `/diff` 看改了什么
2. 再 `/review` 让 Codex 找风险、回归和缺测试

### 会话太长

```text
/compact
```

官方明确把它当作“释放上下文”的工具。

## 容易混淆的几组命令

### `/new` vs `/clear`

- `/new`: 新对话，但不强制清理当前终端显示
- `/clear`: 清屏并开始新对话

### `/fork` vs `/resume`

- `/fork`: 复制当前线程，适合“现在立刻分支”
- `/resume`: 打开之前保存的旧会话

### `/permissions` vs `config.toml`

- `/permissions`: 只改当前会话
- `config.toml`: 改默认行为，后续会话也沿用

## 官方要点

- Slash command 是“键盘优先”的 CLI 控制方式
- 任务运行中也可以先输入 slash command，再按 `Tab` 排队到下一轮执行
- `/approvals` 还是兼容别名，但官方现在主推 `/permissions`

资料来源：

- Slash commands: <https://developers.openai.com/codex/cli/slash-commands>
