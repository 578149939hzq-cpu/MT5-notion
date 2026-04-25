---
name: openspec-archive-change
description: 归档已完成的 OpenSpec change。适用于实现已经完成，用户希望收尾并归档变更的场景。
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.3.0"
---

归档实验工作流中的已完成 change。

**输入**：可以选择性提供一个 change 名称。如果省略，则检查是否能从对话上下文推断；如果含糊或存在歧义，必须提示用户选择可用 change。

**步骤**

1. **如果没有提供 change 名称，先提示用户选择**

   运行 `openspec list --json` 获取可用 change，并使用 **AskUserQuestion tool** 让用户选择。

   只展示活跃的 change（不包括已归档的）。
   如果可用，也展示每个 change 所使用的 schema。

   **重要**：不要猜测，也不要自动选择 change。始终让用户自己选。

2. **检查 artifact 完成状态**

   运行：
   ```bash
   openspec status --change "<name>" --json
   ```
   解析 JSON，理解：
   - `schemaName`：当前使用的 workflow
   - `artifacts`：artifact 列表及其状态（`done` 或其他）

   **如果存在未完成 artifact：**
   - 显示警告，并列出未完成 artifact
   - 使用 **AskUserQuestion tool** 确认用户是否仍要继续
   - 若用户确认，则继续

3. **检查 task 完成状态**

   读取 tasks 文件（通常是 `tasks.md`），检查是否仍有未完成任务。

   统计 `- [ ]`（未完成）与 `- [x]`（已完成）的任务数量。

   **如果发现未完成任务：**
   - 显示警告，说明未完成任务数量
   - 使用 **AskUserQuestion tool** 确认用户是否仍要继续
   - 若用户确认，则继续

   **如果没有 tasks 文件：** 直接继续，不显示任务相关警告。

4. **评估 delta spec 的同步状态**

   检查 `openspec/changes/<name>/specs/` 下是否存在 delta specs。如果没有，则直接继续，不需要 sync 提示。

   **如果存在 delta specs：**
   - 将每个 delta spec 与对应主 spec `openspec/specs/<capability>/spec.md` 做对比
   - 判断将会应用哪些变化（新增、修改、移除、重命名）
   - 在提示用户之前，先显示一份合并摘要

   **可选项：**
   - 如果存在需要同步的变更：`"Sync now (recommended)"`, `"Archive without syncing"`
   - 如果已经同步：`"Archive now"`, `"Sync anyway"`, `"Cancel"`

   如果用户选择 sync，使用 Task tool（`subagent_type: "general-purpose"`，prompt: `"Use Skill tool to invoke openspec-sync-specs for change '<name>'. Delta spec analysis: <include the analyzed delta spec summary>"`）。
   无论用户是否选择 sync，之后都继续归档流程。

5. **执行归档**

   如果归档目录不存在，则创建：
   ```bash
   mkdir -p openspec/changes/archive
   ```

   使用当前日期生成目标名称：`YYYY-MM-DD-<change-name>`

   **检查目标是否已存在：**
   - 如果已存在：报错，并建议重命名已有归档或改天再归档
   - 如果不存在：将 change 目录移动到 archive

   ```bash
   mv openspec/changes/<name> openspec/changes/archive/YYYY-MM-DD-<name>
   ```

6. **显示摘要**

   展示归档结果摘要，包括：
   - change 名称
   - 使用的 schema
   - 归档位置
   - specs 是否已同步（如适用）
   - 是否存在警告（例如未完成 artifact / task）

**成功时的输出**

```
## 归档完成

**变更：** <change-name>
**Schema：** <schema-name>
**归档位置：** openspec/changes/archive/YYYY-MM-DD-<name>/
**Specs：** ✓ 已同步到主 specs（或 "No delta specs" / "Sync skipped"）

所有 artifacts 均已完成。所有 tasks 均已完成。
```

**约束**
- 如果未提供 change 名称，始终要求用户选择
- 使用 `openspec status --json` 的 artifact 图来判断完成状态
- 对警告不做强阻塞，只负责提示并确认
- 移动目录时保留 `.openspec.yaml`（因为整个目录一起移动）
- 清楚说明实际发生了什么
- 如果用户请求 sync，按 openspec-sync-specs 的方式执行（agent-driven）
- 如果存在 delta specs，必须先做 sync 评估并给出合并摘要，再提示用户
