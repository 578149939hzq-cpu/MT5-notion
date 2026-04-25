## ADDED Requirements

### Requirement: Sync outcomes must be reported accurately
主同步流程 MUST 明确区分新建成功、更新成功、重复跳过和同步失败，且批量汇总 MUST 分别统计这些结果。

#### Scenario: Failed requests are not reported as duplicates
- **WHEN** 单笔交易在写入或更新 Notion 时发生请求错误
- **THEN** 该交易 MUST 被记录为失败
- **AND** 批量汇总 MUST 增加失败计数
- **AND** 该交易 MUST NOT 被统计为重复跳过

#### Scenario: Duplicate records remain distinguishable
- **WHEN** 同步流程发现交易票据已经存在且未启用更新
- **THEN** 该交易 MUST 被记录为重复跳过
- **AND** 批量汇总 MUST 保留独立的重复计数

### Requirement: Repository-relative configuration must be stable
主同步脚本和受支持的诊断工具 MUST 基于项目根目录解析 `.env`、字段映射文件和日志输出目录，而不是依赖启动时的当前工作目录。

#### Scenario: Running from another working directory still uses project files
- **WHEN** 用户从非仓库根目录启动主同步脚本
- **THEN** 脚本 MUST 仍然读取项目根目录下的 `.env`
- **AND** 字段映射文件 MUST 相对于项目根目录解析
- **AND** 日志 MUST 写入项目根目录下的 `logs/`

### Requirement: Diagnostic tools must not embed credentials
仓库中的受支持诊断工具 MUST 通过环境变量读取 MT5 登录配置，且在配置缺失时给出明确提示并安全退出。

#### Scenario: Missing MT5 credentials in diagnostics
- **WHEN** 用户运行需要 MT5 登录配置的诊断工具且环境变量缺失
- **THEN** 工具 MUST 输出缺少配置的说明
- **AND** 工具 MUST NOT 使用硬编码凭据尝试连接

### Requirement: The project must provide regression coverage for critical sync logic
项目 MUST 提供可执行的自动化测试，覆盖关键纯逻辑与同步结果统计行为。

#### Scenario: Developers run regression tests
- **WHEN** 开发者执行项目文档中声明的测试命令
- **THEN** 测试集 MUST 验证路径解析、同步结果统计和关键数据格式化逻辑
