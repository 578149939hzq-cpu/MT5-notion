# `config.toml`、审批和沙箱

官方资料：

- Config basics: <https://developers.openai.com/codex/config-basic>
- Sandboxing: <https://developers.openai.com/codex/concepts/sandboxing>
- Agent approvals & security: <https://developers.openai.com/codex/agent-approvals-security>

## 配置文件在哪

官方定义的两层最重要：

- 用户级默认：`~/.codex/config.toml`
- 项目级覆盖：`.codex/config.toml`

CLI、IDE extension、Codex app 共享这些配置层。

## 生效顺序

高优先级覆盖低优先级：

1. CLI flags 和 `--config` 临时覆盖
2. profile
3. 项目里的 `.codex/config.toml`
4. 用户级 `~/.codex/config.toml`
5. 系统级配置
6. 内建默认值

所以：

- 临时试验，用命令行参数
- 仓库习惯，写 `.codex/config.toml`
- 个人长期偏好，写 `~/.codex/config.toml`

## 最常改的几个键

```toml
model = "gpt-5.5"
model_reasoning_effort = "high"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
web_search = "cached"

[windows]
sandbox = "elevated"
```

这些键的含义：

- `model`: 默认模型
- `model_reasoning_effort`: 推理强度
- `approval_policy`: 何时需要审批
- `sandbox_mode`: 沙箱范围
- `web_search`: 网页搜索模式
- `[windows].sandbox`: 原生 Windows 的沙箱模式

## 审批策略怎么理解

官方常见策略有 3 个：

- `untrusted`: 对不在受信任集合内的命令请求审批
- `on-request`: 默认在沙箱内自动做，需要越界时再问
- `never`: 不弹审批

实用理解：

- 想稳一点：`on-request`
- 想更保守：`untrusted`
- 想无人值守：`never`

如果你只是本地正常开发，官方建议的低摩擦默认就是 `workspace-write + on-request`。

## 沙箱模式怎么理解

官方常见模式有 3 个：

- `read-only`
- `workspace-write`
- `danger-full-access`

含义：

- `read-only`: 只能读，改文件或跑命令通常都要审批
- `workspace-write`: 可以在工作区内读写和跑常规本地命令
- `danger-full-access`: 不受沙箱约束，风险最高

## 官方推荐的默认心智模型

官方在 `Defaults and recommendations` 里给出的建议是：

- 版本控制目录：推荐 `Auto`
- `Auto` 本质上是 `workspace-write + on-request`
- 非版本控制目录：更偏向 `read-only`

所以如果你在正常 Git 仓库开发，最常见起点就是：

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"
```

## 常见组合

| 目标 | 配置/参数 | 说明 |
| --- | --- | --- |
| 默认本地开发 | `workspace-write` + `on-request` | 最平衡 |
| 只读分析 | `read-only` + `on-request` | 适合先看代码、先问问题 |
| 只读无人值守 | `read-only` + `never` | 只能读，不会弹窗 |
| 更保守的自动编辑 | `workspace-write` + `untrusted` | 可写，但不轻易自动跑命令 |
| 完全放开 | `danger-full-access` + `never` | 风险最高，不建议常态使用 |

对应 CLI 显式参数：

```bash
codex --sandbox workspace-write --ask-for-approval on-request
codex --sandbox read-only --ask-for-approval on-request
```

## `--full-auto` 是什么

官方说明：

- `--full-auto` 是较低风险的本地自动化预设
- 本质等于 `--sandbox workspace-write --ask-for-approval on-request`

它不是完全无限制。

## `--yolo` 是什么

官方把它定义成高风险别名：

- `--dangerously-bypass-approvals-and-sandbox`
- 别名是 `--yolo`

本质就是：

- 无沙箱
- 无审批

除非你非常清楚风险，否则不要把它当默认模式。

## 可写目录和受保护目录

即使是 `workspace-write`，官方也明确说这些路径通常仍会被保护为只读：

- `.git`
- `.agents`
- `.codex`

这点很重要，因为很多人会误以为 `workspace-write` 就等于“工作区里都能改”。

## 需要多目录写入怎么办

官方建议优先用 writable roots，而不是直接切到 `danger-full-access`。

相关键：

```toml
[sandbox_workspace_write]
writable_roots = ["D:/another/path"]
```

如果只是 Windows 原生 CLI 下临时读一个目录，也可以用：

```text
/sandbox-add-read-dir C:\absolute\path
```

## 命名权限配置

如果你想让不同项目复用同一套权限边界，可以用：

- `default_permissions`
- `[permissions.<name>.filesystem]`
- `[permissions.<name>.network]`

官方还支持对特定路径或 glob 设置 `none`，用于阻止读取敏感文件。

例子：

```toml
default_permissions = "workspace"

[permissions.workspace.filesystem]
":project_roots" = { "." = "write", "**/*.env" = "none" }
glob_scan_max_depth = 3
```

这个模式很适合：

- 仓库可写
- 但本地 `.env` 不想让 Codex 读

## Windows 上要注意什么

`Config basics` 当前官方建议：

```toml
[windows]
sandbox = "elevated"
```

如果没有管理员权限或初始化失败，再退回：

```toml
[windows]
sandbox = "unelevated"
```

## 一个够用的起步配置

```toml
model = "gpt-5.5"
model_reasoning_effort = "high"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
web_search = "cached"

[windows]
sandbox = "elevated"

[features]
multi_agent = true
personality = true
shell_snapshot = true
```

## 什么时候用会话命令，什么时候改配置

| 场景 | 更适合 |
| --- | --- |
| 临时放宽权限一次 | `/permissions` |
| 临时切换模型 | `/model` |
| 长期默认想改 | `config.toml` |
| 配置不生效，查来源 | `/debug-config` |

## 建议

- 默认从 `workspace-write + on-request` 开始
- 先把权限收紧，再按需要放开
- 不要把 `danger-full-access + never` 作为默认配置
- 配置改完后，用 `/status` 和 `/debug-config` 验证

资料来源：

- Config basics: <https://developers.openai.com/codex/config-basic>
- Sandboxing: <https://developers.openai.com/codex/concepts/sandboxing>
- Agent approvals & security: <https://developers.openai.com/codex/agent-approvals-security>
