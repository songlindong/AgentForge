# AgentForge 金融智能客服

AgentForge 是一个面向金融贷款 APP/H5 双渠道客服业务的企业级 AI 智能客服系统，采用分步骤实施方式建设，并最终部署到 Linux 服务器持续运行。

项目采用 **SDD（规格驱动开发）+ Harness（可重复验证环境）**：先写清需求、边界、接口与验收标准，再实现代码，并用 Fake LLM、Mock MCP、自动化测试、评测和压测证明实现符合规格。

## 当前状态

当前已完成“第 7 步：金融多模态知识库写入闭环”。系统已经能在 Local
环境处理 PDF、扫描 PDF、PNG/JPEG，把元数据、OCR/区域、表格、片段和任务
写入 MySQL，把原文件写入 MinIO，把关键词与向量分别写入 OpenSearch 和
Milvus，并通过 Transactional Outbox 向 Kafka 投递阶段事件。

当前只完成了知识库的可追溯写入，不包含第 8 步混合检索、重排、问答和
质量评测；也仍未实现 Channel、LLM Gateway、Agent Runtime、Skill、
Memory、MCP 或正式 Sandbox。Local/Test 使用的固定 OCR、Hash Embedding、
测试扫描器和进程内解析边界不能用于生产。

**当前暂停点：等待你阅读并确认第 7 步；确认后才把第 8 步设为当前步骤。**

## 不可变的五项核心技术目标

金融智能客服是业务落地场景，以下五项是项目从规划、开发到服务器上线始终不能删除、替换或降级的技术主线：

1. Agent Runtime 内核、Agent 编排与 Skill 体系开发
2. 安全沙箱与隔离环境建设
3. 企业级大模型网关（LLM Gateway）开发
4. 高效记忆系统（Memory）与多模态知识库（Multimodal Knowledge Base）建设
5. 高并发 LLM 网关、百万级 RAG 知识库优化

正式上线不是只把页面和接口部署到服务器。五项能力必须分别完成规格、实现、测试、性能或安全验证，并在目标服务器环境通过发布门禁；任何一项没有验收证据，都不能把项目标记为“上线完成”。

## 先读这些文档

| 文档 | 用途 |
|---|---|
| [docs/project-context.md](docs/project-context.md) | 项目目标、边界、架构和已确认技术栈 |
| [docs/development-roadmap.md](docs/development-roadmap.md) | 从规格到实现的分步实施路线 |
| [docs/progress.md](docs/progress.md) | 当前进度、暂停点和下一步 |
| [AGENTS.md](AGENTS.md) | 约束 Codex 每次只推进一个步骤 |
| [specs/product/vision.md](specs/product/vision.md) | 产品愿景、业务范围、发布阶段和成功定义 |
| [specs/product/user-stories.md](specs/product/user-stories.md) | 用户角色、P0/P1 用户故事和验收摘要 |
| [specs/product/non-functional-requirements.md](specs/product/non-functional-requirements.md) | 性能、质量、安全、容量、恢复和上线指标 |
| [specs/architecture/](specs/architecture/) | 系统上下文、容器、数据流、安全和部署架构 |
| [specs/adr/](specs/adr/) | 关键架构决策记录 |
| [specs/engineering/repository-foundation.md](specs/engineering/repository-foundation.md) | 第 4 步仓库骨架、统一命令和门禁规格 |
| [specs/engineering/local-infrastructure.md](specs/engineering/local-infrastructure.md) | 第 5 步本地基础设施、网络、健康和持久化规格 |
| [specs/engineering/financial-customer-service-harness.md](specs/engineering/financial-customer-service-harness.md) | 第 6 步 Fake、Mock、Fixture、Replay 和 Generator 规格 |
| [specs/engineering/multimodal-knowledge-ingestion.md](specs/engineering/multimodal-knowledge-ingestion.md) | 第 7 步多模态安全写入、幂等、四存储和发布门禁规格 |

## 工程目录

| 目录 | 职责 |
|---|---|
| `services/` | Go/Python 后端服务边界 |
| `web/` | H5 与运营端 Web 工作区边界 |
| `harness/` | Fake、Mock、Fixture、回放和数据生成器边界 |
| `tests/` | 单元、契约、集成、端到端、安全和性能测试分层 |
| `infra/` | Compose、环境、可观测性和运维脚本边界 |
| `reports/` | 可复现验证证据的输出边界 |
| `tools/` | 仓库级离线门禁工具，不包含业务逻辑 |

目录存在只表示职责位置已经确定，不表示相关业务能力已经实现。

## 环境与统一检查

本步固定的工具版本为：

- Go `1.26.2`
- Python `3.13.14`
- Node.js `24.14.0`
- pnpm `11.9.0`

Python 服务依赖使用服务级 `pyproject.toml` 声明，并由
`requirements/step7.lock.txt` 固定完整版本。按 `requirements/README.md`
创建 `.venv` 后执行完整门禁：

```powershell
.\.venv\Scripts\python.exe tools/check.py ci
```

也可以分别执行：

```powershell
.\.venv\Scripts\python.exe tools/check.py structure
.\.venv\Scripts\python.exe tools/check.py specs
.\.venv\Scripts\python.exe tools/check.py format
.\.venv\Scripts\python.exe tools/check.py infrastructure
.\.venv\Scripts\python.exe tools/check.py static
.\.venv\Scripts\python.exe tools/check.py harness
.\.venv\Scripts\python.exe tools/check.py test
```

Windows 可以使用 `tools/check.ps1`，Linux/macOS 可以使用 `tools/check.sh`。包装脚本只转发到同一 Python 入口。工程门禁不安装依赖、不访问模型或金融接口；其中 `infrastructure` 只解析 Compose 配置，不启动 Docker 容器。

## 本地基础设施

确保 Docker Desktop/Engine 已启动后，使用统一入口管理 Local 环境：

```powershell
python tools/infra.py up --env local
python tools/infra.py status --env local
python tools/infra.py smoke --env local
python tools/infra.py restart-verify --env local
python tools/infra.py down --env local
```

Local MySQL 在宿主机使用 `127.0.0.1:3307`；Local MinIO 使用
`127.0.0.1:29000/29001`，用于避让开发机已有的 `9000/9001` 服务。
容器内仍使用标准端口。其他端口与数据删除规则见第 5 步规格。普通
`down` 保留命名卷，不能用它代替显式数据销毁。

## 第 7 步知识写入

```powershell
.\.venv\Scripts\python.exe tools/knowledge.py migrate --env local
.\.venv\Scripts\python.exe tools/knowledge.py verify --env local
.\.venv\Scripts\python.exe tools/knowledge.py serve --env local
```

`verify` 显式连接 Local 的 MySQL、MinIO、Kafka、OpenSearch 和 Milvus，
使用固定文本 PDF、扫描 PDF、PNG、JPEG 以及故障注入任务验证四存储写入、
双索引发布门禁、幂等重试、Inbox/Outbox 和租户隔离。普通 CI 中该真实
存储测试默认跳过，避免把“Docker 未启动”误判为代码失败。

## 金融客服 Harness

日常离线验证不需要启动 Docker 或连接真实模型：

```powershell
python -m harness.agentforge_harness verify
python -m harness.agentforge_harness replay --all
python -m unittest discover -s harness/tests -p "test_*.py"
```

Fake LLM 与 Mock MCP 的本机服务入口、场景范围和生成器参数见
`harness/README.md`。Harness 通过只证明测试环境和黄金数据可用；第 7 步
Local 知识写入已实现，但不表示 Gateway、Agent、Skill、Memory、MCP、
正式 Sandbox 或生产 Knowledge 能力已经完成。

## 已确认的核心技术栈

- 用户端与运营端：Next.js、TypeScript、Tailwind CSS、shadcn/ui、React Flow
- 渠道接入与核心后端：Go、Hertz、Eino
- Agent 编排与 Skill：Agent Registry、Router、Planner、DAG、Checkpoint、Skill Registry、JSON Schema
- RAG 与评测服务：Python、FastAPI、FlagEmbedding、Cross-Encoder
- 多模态文档处理：Docling、PyMuPDF、PaddleOCR、版面分析与表格提取
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
