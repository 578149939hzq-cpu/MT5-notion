# 常见工作流

这页把前面的命令和配置串起来，方便直接照着用。

## 工作流 1：先分析，不急着改

适合：

- 新仓库
- 老项目但你不熟
- 需求还模糊

推荐动作：

1. `/status`
2. `/mention README.md`
3. `/mention openspec`
4. `/plan 先分析当前项目结构和实现入口，不要写代码`

推荐提问：

```text
先分析这个仓库：
- 总结核心目录和启动入口
- 找出和本次需求最相关的文件
- 给出最小改动方案
- 暂时不要写代码
```

## 工作流 2：按 OpenSpec task 执行

适合：

- 你已经有 change / tasks
- 只想让 Codex按任务落地

推荐动作：

1. `/status`
2. `/mention openspec/changes/<change-id>/tasks.md`
3. `/mention` 相关设计和代码入口
4. 直接发任务 prompt

推荐提问：

```text
根据我挂进来的 OpenSpec tasks，只执行当前未完成的第一个任务：
- 先确认影响文件
- 做最小必要改动
- 修改后运行相关验证
- 最后汇报改动、验证结果和剩余风险
```

## 工作流 3：只做代码审查

适合：

- 你已经改完代码
- 想让 Codex 以 review 视角找问题

推荐动作：

1. `/diff`
2. `/review`

补充提问：

```text
只做 review，不要改代码。
重点找：
- 逻辑 bug
- 回归风险
- 缺失测试
- 配置或边界条件问题
```

## 工作流 4：会话太长，准备继续干

适合：

- 长时间排错
- 多轮修改
- 历史上下文过长

推荐动作：

1. `/compact`
2. `/status`
3. 必要时重新 `/mention` 关键文件

说明：

- `/compact` 是保留关键信息、缩短上下文
- 压缩后最好重新挂一遍关键文件，避免上下文漂移

## 工作流 5：试两条方案，但不想丢当前线程

适合：

- A/B 两种修法
- 想保留原思路

推荐动作：

1. 当前线程里 `/fork`
2. 在新线程试方案 B
3. 两边分别看 `/diff`

说明：

- `/fork` 比重新开新会话更适合“保留同一背景”
- `/new` 更适合完全换题

## 工作流 6：准备给仓库写长期规则

适合：

- Codex 在这个仓库里反复犯同样的错
- 你每次都要重复同一句话

推荐动作：

1. `/init`
2. 对照模板改 `AGENTS.md`
3. 提交前自己过一遍是否短、准、可执行

建议只写：

- 命令入口
- 禁区
- 完成标准
- 特别容易踩坑的仓库约束

## 工作流 7：调配置但怕配乱

推荐动作：

1. 先改 `~/.codex/config.toml` 或项目 `.codex/config.toml`
2. 重开会话
3. `/status`
4. `/debug-config`

关注：

- 生效的是哪一层
- 当前模型和权限是不是你预期的
- 项目是不是 trusted

## 推荐的日常最小闭环

如果你每天都在这个仓库里工作，最小闭环可以是：

1. `codex`
2. `/status`
3. `/mention` 关键文档或 task
4. 如果任务复杂，先 `/plan`
5. 执行任务
6. `/diff`
7. `/review`
8. 必要时 `/compact`

## 适合你当前场景的建议

你已经有 OpenSpec 工作流，所以更建议你把 Codex 当作：

- 会话控制器
- 实施助手
- review 助手

而不是让它替代规格流程。

实战上：

- 任务范围用 OpenSpec 约束
- 仓库长期规则用 `AGENTS.md` 约束
- 当前改动过程用 slash commands 控制

资料来源：

- Slash commands: <https://developers.openai.com/codex/cli/slash-commands>
- Best practices: <https://developers.openai.com/codex/learn/best-practices>
- AGENTS.md: <https://developers.openai.com/codex/guides/agents-md>
