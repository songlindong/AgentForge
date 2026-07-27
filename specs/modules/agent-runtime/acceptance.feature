# language: zh-CN
@contract @agent-runtime @p0
功能: Agent Runtime、Agent Manifest、Skill Manifest 与 Run 契约
  Runtime 只能调度已发布、租户可见、权限允许并且版本兼容的能力。

  背景:
    假如 Agent Manifest Schema 为 contracts/json-schema/agent-manifest.schema.json
    并且 Skill Manifest Schema 为 contracts/json-schema/skill-manifest.schema.json
    并且 Run Schema 为 contracts/json-schema/run.schema.json
    并且 Kafka 契约为 contracts/asyncapi/kafka.asyncapi.json

  @registry @security
  场景: Agent 不能调用未注册的 Skill
    假如一个 Agent Manifest 引用了 Skill "loan.product.search" 版本 "^1.0.0"
    并且 Skill Registry 中不存在对当前租户可见的已发布兼容版本
    当 Router 解析 Agent Plan
    那么 Plan 应被拒绝并返回错误码 "SKILL_NOT_FOUND"
    并且不得调用 Skill Executor 或外部 Tool

  @registry @security
  场景: 不解析已禁用或版本不兼容的 Skill
    假如 Skill "loan.rate.lookup" 版本 "1.1.0" 已被禁用
    并且 Skill "loan.rate.lookup" 版本 "2.0.0" 不满足约束 "^1.0.0"
    当 Runtime 解析 Skill Binding
    那么应返回 "SKILL_VERSION_INCOMPATIBLE" 或 "SKILL_FORBIDDEN"
    并且 Run 不得静默降级到未注册实现

  @snapshot @replay
  场景: Run 固定确定性回放所需的全部版本
    假如 Runtime 启动 Run "run-001"
    当 Plan 通过校验
    那么 Run Snapshot 必须包含 Agent、全部 Skill、Model、Memory Policy 和 Knowledge Version
    并且每个 Agent、Skill 和 Tool 事件都必须包含 trace_id
    并且回放必须使用 Snapshot 而不是 Registry 中的最新状态

  @orchestration
  场景: 有边界地执行顺序、并行和条件节点
    假如一个 Plan 包含顺序、并行和条件节点
    当 Orchestrator 调度该 Plan
    那么系统必须遵守节点依赖关系
    并且并行度不得超过 max_parallelism
    并且条件为 false 的分支必须被跳过且不得执行对应 Skill
    并且包含循环或节点数超过 max_steps 的 Plan 不得通过校验

  @approval
  场景: 不可逆 Skill 等待人工审批
    假如一个 Skill 的 side_effect 为 "irreversible_write"
    并且 Approval Policy 为 "always"
    当 Scheduler 到达该 Skill 节点
    那么 Run 应进入 waiting_approval
    并且审批前不得发起 MCP 调用
    当经过授权的操作人员批准该任务
    那么 Skill 可以使用其幂等键执行一次

  @budget @negative
  场景: 预算耗尽后 Run 不能继续执行
    假如一个 Run 已达到 max_steps 或 deadline
    当一个待处理 Task 进入 ready 状态
    那么该 Task 不得执行
    并且 Run 应进入 failed 或 handoff 并返回错误码 "BUDGET_EXCEEDED"

  @recovery
  场景: 服务重启后从有效 Checkpoint 恢复租约过期的 Task
    假如一个 Task 已保存 Checkpoint 并且 Worker Lease 已过期
    当恢复 Worker 扫描该 Run
    那么系统应从最新有效 Checkpoint 恢复
    并且不得重复执行已经完成的幂等副作用

