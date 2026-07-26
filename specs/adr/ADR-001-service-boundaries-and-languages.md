# ADR-001：服务边界与语言分工

状态：Proposed  
日期：2026-07-26

## 背景

AgentForge 同时需要高并发网关、可恢复 Agent Runtime、金融 RAG、多模态文档处理和生产运维。单一语言难以同时兼顾 Go 的并发服务能力和 Python 的文档/模型生态。

## 决策

- Go 负责 Channel Gateway、LLM Gateway、Agent Runtime、Skill Registry、MCP Gateway、Sandbox Controller 和主要管理 API。
- Python/FastAPI 负责 Document Processor、OCR/版面/表格、Embedding、重排、RAG 评测和模型实验。
- Next.js/TypeScript 负责 H5、运营、客服和审计界面。
- Go/Python 跨服务使用版本化 HTTP/JSON 契约和 Kafka 事件；不通过共享数据库表实现隐式耦合。

## 备选方案

- 全部使用 Python：文档生态好，但高并发 Gateway 和 Runtime 统一调度成本更高。
- 全部使用 Go：服务一致，但 OCR、版面和评测生态需要大量自研。
- 全部使用 TypeScript：不符合核心后端和 AI 服务的职责目标。

## 后果

- 必须维护跨语言 Schema、超时、错误码和版本兼容。
- Go/Python 服务都必须可用 Fake/Mock 替代进行测试。
- 第 3 步使用 OpenAPI、JSON Schema 和 AsyncAPI 固定跨语言契约。
