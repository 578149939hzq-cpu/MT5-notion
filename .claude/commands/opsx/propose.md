---
name: "OPSX: Propose"
description: 提出新的 change - 一次性创建并生成所有产物
category: Workflow
tags: [workflow, artifacts, experimental]
---

提出一个新的 change，一次性创建 change 并生成所有产物。

我会创建一个 change，并生成以下产物：
- proposal.md（做什么、为什么做）
- design.md（怎么做）
- tasks.md（实现步骤）

准备开始实现时，运行 `/opsx:apply`

---

**输入**：`/opsx:propose` 后面的参数可以是 change 名称（kebab-case），也可以是用户想要构建内容的描述。

**步骤**

1. **如果没有提供输入，先询问用户想构建什么**

   使用 **AskUserQuestion tool**（开放式问题，不带预设选项）提问：
   > "你想处理哪个 change？请描述你想构建或修复的内容。"

   根据用户描述推导一个 kebab-case 名称，例如 `"add user authentication"` → `add-user-auth`。

   **重要**：在明确用户要构建什么之前，不要继续。

2. **创建 change 目录**
   ```bash
   openspec new change "<name>"
   ```
   这会在 `openspec/changes/<name>/` 下创建脚手架，并包含 `.openspec.yaml`。

3. **获取产物构建顺序**
   ```bash
   openspec status --change "<name>" --json
   ```
   解析 JSON，获取：
   - `applyRequires`：进入实现前必须完成的 artifact ID 数组，例如 `["tasks"]`
   - `artifacts`：所有 artifact 的列表，以及它们的状态和依赖关系

4. **按顺序创建产物，直到达到 apply-ready**

   使用 **TodoWrite tool** 跟踪产物创建进度。

   按依赖顺序循环处理 artifact，优先处理没有未完成依赖的 artifact：

   a. **对于每个状态为 `ready` 的 artifact（依赖已满足）**：
      - 获取说明：
        ```bash
        openspec instructions <artifact-id> --change "<name>" --json
        ```
      - 返回的 instructions JSON 包含：
        - `context`：项目背景（对你是约束，不要写进输出）
        - `rules`：该 artifact 的规则（对你是约束，不要写进输出）
        - `template`：输出文件应遵循的结构
        - `instruction`：该 artifact 类型的具体指导
        - `outputPath`：文件写入路径
        - `dependencies`：可供参考的已完成依赖产物
      - 读取已完成的依赖文件，获取上下文
      - 使用 `template` 作为结构创建 artifact 文件
      - 将 `context` 和 `rules` 作为约束应用，但不要把它们原样复制进文件
      - 简要显示进度：`已创建 <artifact-id>`

   b. **持续执行，直到所有 `applyRequires` 产物都完成**
      - 每创建完一个 artifact，都重新运行：
        ```bash
        openspec status --change "<name>" --json
        ```
      - 检查 `applyRequires` 中的每个 artifact ID 是否都在 `artifacts` 数组里显示为 `status: "done"`
      - 一旦全部完成，就停止

   c. **如果某个 artifact 需要用户补充信息**（上下文不清晰）：
      - 使用 **AskUserQuestion tool** 进一步澄清
      - 然后继续创建

5. **显示最终状态**
   ```bash
   openspec status --change "<name>"
   ```

**输出**

所有产物完成后，总结：
- change 名称和路径
- 已创建的 artifact 列表及其简述
- 当前状态：`所有产物已创建完成！已准备好开始实现。`
- 提示：`运行 /opsx:apply 开始实现。`

**产物创建指南**

- 每个 artifact 都遵循 `openspec instructions` 返回的 `instruction` 字段
- schema 决定每个 artifact 应包含什么内容，严格按 schema 来
- 创建新 artifact 前，先读取依赖产物获取上下文
- 使用 `template` 作为输出文件结构，并填充各个部分
- **重要**：`context` 和 `rules` 是给你的约束，不是文件内容
  - 不要把 `<context>`、`<rules>`、`<project_context>` 这类块原样复制进 artifact
  - 它们用于指导你写作，但不应该出现在最终输出里

**约束**
- 创建实现所需的全部 artifacts（以 schema 的 `apply.requires` 为准）
- 创建新 artifact 前始终先读取依赖产物
- 如果上下文严重不清楚，向用户提问，但优先做合理判断保持推进
- 如果同名 change 已存在，询问用户是继续该 change 还是创建新 change
- 每写完一个 artifact，确认对应文件已经存在，再继续下一个
