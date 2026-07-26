# ADR-005：企业级 LLM Gateway

状态：Proposed  
日期：2026-07-26

## 背景

Agent、Skill 和 APP/H5 不应绑定单一模型供应商。系统需要统一协议、模型路由、限流、计量、故障处理和文本/图片能力路由。

## 决策

- 对上提供 OpenAI 兼容 Chat/SSE 接口。
- Provider 适配 OpenAI 兼容 API、Ollama、vLLM 和后续模型服务。
- 根据任务类型、上下文长度、模态能力、租户权限、健康状态、延迟和成本路由。
- 实现鉴权、租户配额、并发限制、有限重试、熔断、Fallback、SSE 取消和 Token/费用计量。
- 多模态请求使用受控 content parts 和内部对象引用，不允许模型服务任意访问公网文件地址。

## 后果

Gateway 需要独立于 Agent Runtime 进行契约、故障注入、并发、取消传播和计量测试；模型供应商自身 SLA 与系统开销分开统计。
