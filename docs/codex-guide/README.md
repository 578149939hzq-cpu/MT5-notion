# Codex CLI Chinese Guide

这套文档是给当前仓库补的一份中文 Codex 速查，不替代你的 OpenSpec 工作流。

适合的使用场景：

- 已经会基本终端操作
- 想更熟练地用 Codex CLI 的 slash commands
- 想知道 `AGENTS.md`、`config.toml`、权限和沙箱到底怎么配
- 想直接复制一份模板开始用

建议阅读顺序：

1. [01-slash-commands.md](./01-slash-commands.md)
2. [02-agents-md.md](./02-agents-md.md)
3. [03-config-and-permissions.md](./03-config-and-permissions.md)
4. [04-common-workflows.md](./04-common-workflows.md)
5. [05-manual-sync.md](./05-manual-sync.md)
6. `templates/` 里的模板文件

目录说明：

- `01-slash-commands.md`: 常用 CLI 指令速查
- `02-agents-md.md`: `AGENTS.md` 的作用、优先级、写法
- `03-config-and-permissions.md`: `config.toml`、审批、沙箱、Windows 注意点
- `04-common-workflows.md`: 实战工作流组合
- `05-manual-sync.md`: 手动同步固定命令速查
- `templates/AGENTS.repo.template.md`: 仓库级 `AGENTS.md` 模板
- `templates/AGENTS.subdir.template.md`: 子目录覆盖模板
- `templates/codex-task-prompt.template.md`: 日常提问模板
- `templates/config.toml.sample`: 常见配置样例

和 OpenSpec 的关系：

- OpenSpec 管需求、proposal、design、tasks、归档
- Codex CLI 命令管当前会话怎么跑
- `AGENTS.md` 管 Codex 在这个仓库里长期遵守什么规则
- `config.toml` 管 Codex 默认用什么模型、权限、沙箱、MCP

官方资料来源：

- Quickstart: <https://developers.openai.com/codex/quickstart>
- Slash commands: <https://developers.openai.com/codex/cli/slash-commands>
- Best practices: <https://developers.openai.com/codex/learn/best-practices>
- AGENTS.md: <https://developers.openai.com/codex/guides/agents-md>
- Config basics: <https://developers.openai.com/codex/config-basic>
- Sandboxing: <https://developers.openai.com/codex/concepts/sandboxing>
- Agent approvals & security: <https://developers.openai.com/codex/agent-approvals-security>
