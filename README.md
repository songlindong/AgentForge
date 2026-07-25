# AgentForge 金融智能客服

AgentForge 是一个面向金融贷款 APP/H5 双渠道客服业务的企业级 AI 智能客服系统，采用分步骤实施方式建设，并最终部署到 Linux 服务器持续运行。

项目采用 **SDD（规格驱动开发）+ Harness（可重复验证环境）**：先写清需求、边界、接口与验收标准，再实现代码，并用 Fake LLM、Mock MCP、自动化测试、评测和压测证明实现符合规格。

## 当前状态

当前只完成了“第 0 步：项目交接与实施计划”，尚未创建业务代码、安装依赖或启动基础设施。

**当前暂停点：等待你阅读并确认规划；确认后只进入第 1 步。**

## 不可变的五项核心技术目标

金融智能客服是业务落地场景，以下五项是项目从规划、开发到服务器上线始终不能删除、替换或降级的技术主线：

1. Agent Runtime 内核、Agent 编排与 Skill 体系开发
2. 安全沙箱与隔离环境建设
3. 企业级大模型网关（LLM Gateway）开发
4. 高效记忆系统（Memory）与知识库（Knowledge Base）建设
5. 高并发 LLM 网关、百万级 RAG 知识库优化

正式上线不是只把页面和接口部署到服务器。五项能力必须分别完成规格、实现、测试、性能或安全验证，并在目标服务器环境通过发布门禁；任何一项没有验收证据，都不能把项目标记为“上线完成”。

## 先读这些文档

| 文档 | 用途 |
|---|---|
| [docs/project-context.md](docs/project-context.md) | 项目目标、边界、架构和已确认技术栈 |
| [docs/development-roadmap.md](docs/development-roadmap.md) | 从规格到实现的分步实施路线 |
| [docs/progress.md](docs/progress.md) | 当前进度、暂停点和下一步 |
| [AGENTS.md](AGENTS.md) | 约束 Codex 每次只推进一个步骤 |

## 已确认的核心技术栈

- 用户端与运营端：Next.js、TypeScript、Tailwind CSS、shadcn/ui、React Flow
- 渠道接入与核心后端：Go、Hertz、Eino
- Agent 编排与 Skill：Agent Registry、Router、Planner、DAG、Checkpoint、Skill Registry、JSON Schema
- RAG 与评测服务：Python、FastAPI、FlagEmbedding、Cross-Encoder
- 数据层：MySQL、Redis、Kafka、Milvus、OpenSearch、MinIO
- 模型服务：OpenAI 兼容 API、Ollama、vLLM
- 身份与安全：Keycloak、JWT/OAuth2、Casbin、Docker/Kubernetes Sandbox、敏感数据脱敏、操作审计
- 可观测性：OpenTelemetry、Prometheus、Grafana、Jaeger/Tempo、Loki
- 部署：Linux、Docker Compose、Nginx/Caddy、HTTPS、CI/CD；达到扩容条件后再评估 Kubernetes
- SDD：Markdown、OpenAPI、JSON Schema、AsyncAPI、Gherkin、ADR
- Harness：Fake LLM、Mock MCP、Testcontainers、RAG 评测、k6、安全测试

## 固定协作节奏

每个步骤都按以下顺序进行：

1. 先解释本步要解决的问题和关键原理。
2. 写本步规格、非目标和验收标准。
3. 只实现本步最小范围。
4. 运行测试或进行文档验收。
5. 更新 `docs/progress.md`，说明做了什么、为什么这样做、如何验证。
6. 停下，等你确认已看懂本步内容后再开始下一步。

项目不会为了“看起来完整”而一次性堆砌所有组件。先完成可验证的金融客服最小闭环，再补齐 APP/H5 双渠道、运营后台和服务器发布能力；Kubernetes、vLLM、百万向量和微调实验均放在后期阶段。
