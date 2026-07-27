# Services

本目录承载 AgentForge 后端服务。当前第 4 步只建立职责边界，没有业务实现。

| 目录 | 语言 | 后续职责 |
|---|---|---|
| `channel-gateway/` | Go | APP/H5 身份映射、统一消息、幂等、SSE 与回传 |
| `llm-gateway/` | Go | 模型鉴权、配额、路由、流式、重试、熔断、降级和计量 |
| `agent-runtime/` | Go | Run、Router、Planner、Orchestrator、Scheduler、Checkpoint 和回放 |
| `skill-registry/` | Go | Agent/Skill Manifest、版本、权限、依赖、发布和回滚 |
| `memory-service/` | Go | 分层 Memory、删除、过期和上下文组装 |
| `mcp-gateway/` | Go | 受控工具授权、超时、重试、幂等和审计 |
| `sandbox-controller/` | Go | 临时隔离任务创建、限制、监控和销毁 |
| `knowledge-service/` | Python | 多模态知识写入、检索、重排、引用和评测接口 |
| `document-processor/` | Python | 文件安全处理、OCR、版面和表格提取 |

存在目录不等于服务已经实现。每个服务开始编码前，仍须完成对应步骤的 SDD 规格和验收场景。

