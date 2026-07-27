# language: zh-CN
@contract @channel @p0
功能: APP/H5 统一消息与 SSE 契约
  渠道网关首先向 H5 提供统一消息契约，后续 APP 复用同一契约。
  租户和用户身份必须以认证上下文为准，不能信任客户端输入。

  背景:
    假如渠道契约为 contracts/openapi/channel-api.openapi.json
    并且统一消息 Schema 为 contracts/json-schema/unified-message.schema.json
    并且调用者是租户 "tenant_demo" 中已通过认证的用户

  @security
  场景: 服务端解析租户身份而不是信任请求字段
    假如一个 H5 请求包含 message_id "msg-001" 和 conversation_id "conv-001"
    并且该请求尝试携带 tenant_id "tenant_other"
    当渠道网关接收该请求
    那么规范化事件中的 tenant_id 应为 "tenant_demo"
    并且客户端提交的 tenant_id 应被忽略或拒绝
    并且不得为租户 "tenant_other" 发布事件

  @idempotency
  场景: 重复消息返回首次接收结果
    假如一条有效 H5 消息的 message_id 为 "msg-002"
    当使用同一个 Idempotency-Key 连续投递两次相同消息
    那么只能发布一条 user.message.received 事件
    并且两次 HTTP 响应必须包含相同的 message_id 和 trace_id
    并且不得创建重复的 Agent Run 或业务副作用

  @idempotency @negative
  场景: 使用相同幂等键提交不同请求体时拒绝请求
    假如 Idempotency-Key 为 "msg-003" 的消息已经被接收
    当第二个请求使用 Idempotency-Key "msg-003" 但携带不同内容
    那么响应状态码应为 409
    并且错误码应为 "IDEMPOTENCY_CONFLICT"
    并且不得发布第二条事件

  @ordering
  场景: 同一会话中的消息保持顺序
    假如消息 "msg-004" 和 "msg-005" 属于会话 "conv-002"
    当两条消息被发布到 Kafka
    那么它们的分区键都应为 "conv-002"
    并且消费者应按照接收顺序处理消息
    并且不同会话可以并行处理

  @sse
  场景: SSE 事件顺序递增并支持恢复
    假如消息 "msg-006" 存在一个正在运行的 Agent Run
    当客户端订阅 /v1/messages/msg-006/events
    那么同一消息的每个 SSE 事件 sequence 必须严格递增
    并且终态事件必须是 response.completed、handoff.required 或 error
    当客户端携带最后收到的 Last-Event-ID 重新连接
    那么已经确认的事件不应重复返回
    并且剩余事件流应继续使用相同的 trace_id

  @cancellation
  场景: 客户端取消操作向下游传播
    假如消息 "msg-007" 正在接收模型流式响应
    当客户端断开连接或调用取消接口
    那么 Agent Run 应进入 cancelling 或 cancelled 路径
    并且 LLM Gateway 应将取消操作传播到 Provider
    并且取消被确认后不得继续生成模型 Token

