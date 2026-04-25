---
name: openspec-apply-change
description: 根据 OpenSpec change 中的 tasks 实施变更。适用于用户要开始实现、继续实现，或按任务推进已有 change。
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.3.0"
---

根据 OpenSpec change 实施任务。

**输入**：可以选择性提供一个 change 名称。如果省略，则检查是否能从对话上下文推断；如果含糊或存在歧义，必须提示用户选择可用 change。

**步骤**

1. **选择 change**

   如果给定了名称，就直接使用。否则：
   - 如果用户在对话里提到某个 change，则尝试从上下文推断
   - 如果当前只有一个活跃 change，则自动选中
   - 如果存在歧义，运行 `openspec list --json` 获取可用 change，并使用 **AskUserQuestion tool** 让用户选择

   始终明确说明：`Using change: <name>`，并告知如何覆盖，例如 `/opsx:apply <other>`。

2. **检查状态，理解当前 schema**
   ```bash
   openspec status --change "<name>" --json
   ```
   解析 JSON，理解：
   - `schemaName`：当前使用的 workflow，例如 `spec-driven`
   - 哪个 artifact 包含 tasks（通常 `spec-driven` 是 `tasks`，其他 schema 以 status 输出为准）

3. **获取 apply 指令**

   ```bash
   openspec instructions apply --change "<name>" --json
   ```

   结果会包含：
   - 上下文文件路径（取决于 schema，可能是 proposal/specs/design/tasks，也可能是 spec/tests/implementation/docs）
   - 进度信息（total、complete、remaining）
   - 任务列表及状态
   - 基于当前状态生成的动态指令

   **状态处理：**
   - 如果 `state: "blocked"`（缺少必要 artifacts），显示提示，并建议使用 openspec-continue-change
   - 如果 `state: "all_done"`，提示已经全部完成，并建议 archive
   - 否则继续实现

4. **读取上下文文件**

   读取 apply instructions 输出中的 `contextFiles`。
   具体文件取决于 schema：
   - **spec-driven**：proposal、specs、design、tasks
   - 其他 schema：以 CLI 输出的 `contextFiles` 为准

5. **显示当前进度**

   显示：
   - 当前使用的 schema
   - 进度，例如：`N/M tasks complete`
   - 剩余任务概览
   - CLI 返回的动态指令

6. **实施任务（循环直到完成或被阻塞）**

   对每个待完成任务：
   - 说明当前正在处理哪个任务
   - 做出所需的代码变更
   - 保持改动最小且聚焦
   - 在 tasks 文件中把任务标记完成：`- [ ]` → `- [x]`
   - 继续下一个任务

   **在以下情况暂停：**
   - 任务定义不清晰 → 先澄清
   - 实现过程中暴露出设计问题 → 建议更新 artifacts
   - 遇到错误或阻塞 → 报告并等待进一步指示
   - 用户中断

7. **完成或暂停时，显示状态**

   显示：
   - 本次会话完成的任务
   - 总体进度，例如：`N/M tasks complete`
   - 如果已全部完成：建议 archive
   - 如果已暂停：说明原因并等待用户进一步指示

**实现过程中的输出**

```
## 正在实现：<change-name>（schema: <schema-name>）

正在处理任务 3/7：<task description>
[...implementation happening...]
✓ 任务完成

正在处理任务 4/7：<task description>
[...implementation happening...]
✓ 任务完成
```

**完成时的输出**

```
## 实现完成

**变更：** <change-name>
**Schema：** <schema-name>
**进度：** 7/7 个任务完成 ✓

### 本次会话完成
- [x] Task 1
- [x] Task 2
...

所有任务均已完成！可以归档这个 change 了。
```

**暂停时的输出（遇到问题）**

```
## 实现已暂停

**变更：** <change-name>
**Schema：** <schema-name>
**进度：** 4/7 个任务完成

### 遇到的问题
<description of the issue>

**可选项：**
1. <option 1>
2. <option 2>
3. 其他处理方式

你想怎么做？
```

**约束**
- 持续推进任务，直到全部完成或明确被阻塞
- 开始实现前，始终先读取上下文文件（来自 apply instructions 输出）
- 如果任务有歧义，先暂停并提问，不要猜
- 如果实现暴露出新的问题，暂停并建议更新 artifacts
- 每个任务的代码改动应保持最小且聚焦
- 每完成一个任务，就立即更新对应复选框
- 遇到错误、阻塞或需求不清晰时暂停，不要臆测
- 使用 CLI 输出里的 `contextFiles`，不要假定固定文件名

**工作流说明**

这个 skill 支持 “对一个 change 执行动作” 的工作流模型：

- **可在任意阶段调用**：在所有 artifacts 完成前（只要 tasks 已存在）、部分实现后、或与其他动作交错执行时都可以调用
- **允许更新 artifacts**：如果实现中发现设计需要调整，可以建议更新 artifacts，而不是把流程锁死成单向阶段
