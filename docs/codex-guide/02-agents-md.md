# `AGENTS.md` 中文说明

官方文档：
<https://developers.openai.com/codex/guides/agents-md>

## 一句话理解

`AGENTS.md` 是给 Codex 的长期仓库说明书。

它适合放：

- 仓库结构
- build / test / lint 命令
- 工程约定
- 禁区
- 什么算完成
- 如何验证

它不适合放：

- 某一次任务的临时需求
- 会频繁变化的临时上下文
- 很细碎的“今天只对这个 bug 生效”的规则

## 和 prompt、OpenSpec、config 的区别

| 载体 | 解决什么问题 | 典型内容 |
| --- | --- | --- |
| 当前 prompt | 这次到底要干什么 | “修这个 bug”“只改这个模块” |
| `AGENTS.md` | 这个仓库里长期怎么做 | 命令、规范、禁区、完成标准 |
| OpenSpec | 变更流程和设计决策 | proposal、design、tasks、archive |
| `config.toml` | Codex 默认怎么运行 | 模型、审批、沙箱、MCP、profile |

实战上可以这样分工：

- OpenSpec 管“变更流程”
- `AGENTS.md` 管“仓库约束”
- prompt 管“本次任务”

## Codex 怎么找 `AGENTS.md`

官方规则是分层加载：

1. 全局层：`~/.codex/AGENTS.override.md` 或 `~/.codex/AGENTS.md`
2. 项目层：从项目根目录一路走到当前目录，按层找 `AGENTS.override.md` 或 `AGENTS.md`
3. 离当前工作目录越近，优先级越高

重要结论：

- 仓库根目录的 `AGENTS.md` 适合写全局规则
- 子目录里的 `AGENTS.md` 或 `AGENTS.override.md` 适合写局部规则
- 规则可以分层覆盖，不一定只能有一个文件

## 最常用的创建方式

先在目标目录执行：

```text
/init
```

官方明确把 `/init` 定义为：

- 在当前目录生成 `AGENTS.md` scaffold
- 让你后续手工改成适合仓库的版本

## 推荐写法

一个好用的 `AGENTS.md` 应该短、准、能执行。

推荐包含这几段：

```md
## Repo layout
## Commands
## Working rules
## Done when
```

可直接参考：

- [templates/AGENTS.repo.template.md](./templates/AGENTS.repo.template.md)
- [templates/AGENTS.subdir.template.md](./templates/AGENTS.subdir.template.md)

## 推荐放什么

### 1. 仓库结构

让 Codex 别乱猜目录：

```md
- `src/` 是主代码
- `tests/` 是自动化测试
- `tools/` 是脚本
- `openspec/` 是规格和变更流程，不要随意改归档内容
```

### 2. 命令入口

明确告诉它怎么验证：

```md
- Run tests: `pytest`
- Lint: `ruff check .`
- Format: `ruff format .`
```

### 3. 禁区和约束

例如：

```md
- 不要改 `.env`
- 不要改真实账号配置
- 除非明确要求，不要新增依赖
- 只做最小必要改动
```

### 4. 完成标准

例如：

```md
- 相关测试通过
- 输出改动摘要
- 明确剩余风险
```

## 不推荐的写法

### 过长

`AGENTS.md` 不是团队制度汇编。太长会稀释重点。

### 过空

像“请写高质量代码”“请遵循最佳实践”这种话，几乎没有可执行性。

### 塞满一次性规则

一次性的“今天只改 A 文件，千万别动 B 文件”更适合写在当前 prompt 或 OpenSpec task 里。

## 一个简单判断标准

出现下面任一情况，可以考虑把规则写进 `AGENTS.md`：

- Codex 在这个仓库里反复犯同一种错
- 你每次都要重复同一句提示
- 这是长期有效的工程约束

## 和子目录覆盖配合

如果仓库某个子目录有特殊规则，可以在该目录放一份更具体的文件。

例子：

- 仓库根目录：全局工程约定
- `services/payments/AGENTS.override.md`: 支付服务特例

这样 Codex 在 `services/payments/` 下工作时，会优先吃到更近的规则。

## 和 OpenSpec 的实际组合方式

如果你已经有 OpenSpec 工作流，建议：

- 设计和变更范围仍然放在 OpenSpec change 里
- 把“仓库长期规则”放在 `AGENTS.md`
- 不要把 OpenSpec 的每一条 task 全量复制进 `AGENTS.md`

简单说：

- OpenSpec 讲“这次为什么改、改什么”
- `AGENTS.md` 讲“在这里改代码时一贯怎么改”

资料来源：

- AGENTS.md guide: <https://developers.openai.com/codex/guides/agents-md>
- Best practices: <https://developers.openai.com/codex/learn/best-practices>
- Slash commands (`/init`): <https://developers.openai.com/codex/cli/slash-commands>
