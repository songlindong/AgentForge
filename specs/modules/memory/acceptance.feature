# language: zh-CN
@contract @memory @security
功能: 分层 Memory 生命周期契约
  Memory 与 Knowledge Base 职责分离，并受到租户、用户、来源和保留策略约束。

  背景:
    假如 Memory 生命周期 Payload 定义在 contracts/json-schema/memory-event.schema.json
    并且 Memory 事件发布到 memory.lifecycle.events

  @isolation
  场景: 不加载其他租户的 Memory
    假如租户 "tenant_demo" 请求加载会话 Memory
    并且一条 Memory 记录属于租户 "tenant_other"
    当 Memory Service 组装上下文
    那么其他租户的记录必须被排除
    并且这次访问尝试必须可以审计

  @retention
  场景: Memory 删除或过期后不再进入上下文
    假如一条语义 Memory 已经过期或用户要求删除
    当系统处理对应的生命周期事件
    那么后续上下文组装必须排除该 Memory
    并且删除或过期操作必须满足幂等要求
    并且事件必须保留来源和保留策略标识

  @privacy
  场景: Memory 事件不携带高敏感明文
    假如一条结构化 Memory 包含敏感金融信息
    当系统发布 memory.lifecycle.events 消息
    那么消息必须包含 content_ref 和 content_digest
    并且消息不得包含原始敏感值

