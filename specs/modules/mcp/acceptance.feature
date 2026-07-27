# language: zh-CN
@contract @mcp @security
功能: MCP Tool 调用契约
  动态利率、额度、征信和审批状态只能来自经过授权的 Tool。

  背景:
    假如 MCP Tool Schema 为 contracts/json-schema/mcp-tool.schema.json
    并且所有 Tool 调用都必须经过 MCP Tool Gateway

  @authorization
  场景: 动态金融查询必须具有授权决策
    假如一个 Skill 请求查询当前贷款利率
    当调用请求中不存在 authorization_decision_id
    那么调用应被拒绝并返回错误码 "TOOL_FORBIDDEN"
    并且模型不得编造一个替代数值

  @freshness
  场景: 过期动态结果不能作为当前结果展示
    假如一个 Tool Result 已经超过 fresh_until 时间
    当 Agent 校验该结果
    那么系统应重新请求经过授权的最新结果或拒绝回答
    并且不得使用旧 Memory 替代当前利率或审批状态

  @retry @idempotency
  场景: Tool 超时遵守 Manifest 策略
    假如一个只读 Tool 配置了超时和重试策略
    当外部服务调用超时
    那么系统只能应用 Manifest 中允许的重试策略
    并且每次尝试都必须使用相同的调用幂等键
    并且超过重试预算后应返回明确失败结果或转人工

  @audit
  场景: Tool 调用可以审计但不泄漏敏感值
    假如一个 Tool 调用返回敏感响应
    当系统写入审计事件
    那么审计记录必须包含 Actor、Tenant、Tool Version、Decision、Status、Purpose 和 trace_id
    并且应保存摘要或受控引用而不是原始凭证或完整敏感数据

