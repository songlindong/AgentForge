# language: zh-CN
@contract @llm-gateway @p0
功能: 企业级 LLM Gateway 契约
  LLM Gateway 为受信服务提供受控的 OpenAI 兼容访问边界。

  背景:
    假如 Gateway 契约为 contracts/openapi/llm-gateway.openapi.json
    并且 Provider 契约为 contracts/json-schema/llm-provider.schema.json
    并且调用者是已通过认证的 AgentForge 服务

  @security
  场景: 服务不能冒充其他租户
    假如服务身份只被授权访问租户 "tenant_demo"
    当服务发送 X-Tenant-ID "tenant_other"
    那么请求应被拒绝并返回错误码 "TENANT_MISMATCH"
    并且不得向 Provider 发送请求

  @multimodal @security
  场景: 模型请求只能引用受控对象 URI
    假如用户消息包含一个 image_url content part
    当 URL 为 "https://example.com/private-contract.png"
    那么请求应被拒绝并返回错误码 "VALIDATION_FAILED"
    当 URL 为 "agentforge://objects/obj-contract-001"
    那么 Gateway 应在路由前校验租户所有权和对象状态

  @routing
  场景: 图片请求不会被发送给纯文本模型
    假如初始选择的模型只支持 text 模态
    并且一个已授权且支持 image 模态的模型处于健康状态
    当请求包含 image_url content part
    那么 Gateway 应选择已授权且支持 image 模态的模型
    并且不得向纯文本模型发送请求

  @routing @negative
  场景: 没有可用视觉模型时安全失败
    假如所有已授权模型都只支持 text 模态或当前不可用
    当请求包含 image_url content part
    那么 Gateway 应返回错误码 "DEPENDENCY_UNAVAILABLE"
    并且不得向 Provider 发送请求

  @retry @fault-injection
  场景大纲: 只有可重试的 Provider 故障才消耗重试预算
    假如 Provider 返回 <failure>
    当 Gateway 处理该响应
    那么重试决策应为 <decision>
    并且 Provider 调用次数不得超过配置的 max_attempts

    例子:
      | failure               | decision |
      | RATE_LIMITED          | retry    |
      | DEPENDENCY_TIMEOUT    | retry    |
      | DEPENDENCY_UNAVAILABLE | retry   |
      | VALIDATION_FAILED     | no_retry |
      | FORBIDDEN             | no_retry |

  @sse
  场景: 流式响应以终止标记结束
    假如 stream 为 true 并且 Provider 返回有效数据块
    当 Gateway 转发响应
    那么每个数据块都必须符合 ChatCompletionChunk Schema
    并且事件流必须以 data: [DONE] 结束
    并且系统必须记录 Usage、Provider、Model 和 trace 元数据

  @budget
  场景: 超过租户并发或配额时拒绝请求
    假如租户已经达到活跃生成数量上限
    当系统收到新的 Completion 请求
    那么响应状态码应为 429
    并且错误信息应标识可重试的配额或并发限制
    并且系统不得创建无界队列

