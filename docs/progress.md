# AgentForge 分步实施进度

最后更新：2026-07-27

## 当前状态

**状态：第 5 步“最小本地基础设施”已完成，等待用户确认。**

当前没有正在实现的步骤。下一候选步骤是“第 6 步：金融客服 Harness”，只有用户确认第 5 步后才能开始。

## 已完成

### 第 0 步：金融业务与五项核心目标交接计划

- [x] 确认仓库起始状态为空，仅包含 `.git`。
- [x] 明确 AgentForge 是面向金融贷款 APP/H5 双渠道客服业务的企业级 AI 智能客服系统。
- [x] 整理 APP、H5 双渠道以及贷前咨询、产品推荐、合规问答、还款计划、合同解读等业务场景。
- [x] 明确金融知识通过 RAG 提供带来源回答，利率、额度、征信和审批状态等动态数据必须通过受控 MCP/业务接口获取。
- [x] 明确首个服务器版本只使用虚构、合成或脱敏数据，未经授权不连接真实金融生产接口。
- [x] 将 Linux + Docker Compose + HTTPS、备份、监控、CI/CD 和回滚纳入正式发布步骤。
- [x] 固定 Agent Runtime 内核、Agent 编排与 Skill 体系为不可变核心目标。
- [x] 恢复并固定安全沙箱与隔离环境为独立建设目标，金融回答护栏不能替代沙箱。
- [x] 固定企业级 LLM Gateway 的鉴权、配额、路由、SSE、重试、熔断、降级和计量范围。
- [x] 固定分层 Memory 与金融 Multimodal Knowledge Base 的建设及验收范围。
- [x] 固定高并发 Gateway 与 100 万向量 RAG 的真实压测和优化要求。
- [x] 将正式服务器发布调整到五项目标完成质量与性能验证之后；任何一项失败都不能标记为上线完成。
- [x] 固定关系型数据库为 MySQL 8.0+。
- [x] 固定 SDD + Harness 和一次一步的协作方式。
- [x] 创建项目入口、项目上下文、实施路线和协作约束。
- [x] 未创建业务代码，未安装依赖，未启动基础设施。

### 第 1 步：产品愿景、用户角色、范围与成功标准

- [x] 创建 `specs/product/vision.md`，明确一句话愿景、产品目标、APP/H5 渠道范围、P0/P1/P2 业务范围和发布阶段。
- [x] 明确贷款咨询用户、人工客服、知识运营、Agent/Skill 运营、合规审计、租户/平台管理员和运维角色。
- [x] 固定金融 Knowledge Base、MCP 动态数据和模型禁止行为的产品边界。
- [x] 明确首批 Agent、Skill 及顺序/并行/条件/DAG/审批编排范围。
- [x] 创建 `specs/product/user-stories.md`，定义 P0/P1 用户故事和验收摘要。
- [x] 创建 `specs/product/non-functional-requirements.md`，定义可用性、延迟、容量、RAG、Agent/Skill、Memory、Gateway、沙箱、安全、可观测性和灾备指标。
- [x] 固定 1000 条 SSE 连接、100 个活跃生成请求和 100 万向量的 GA 容量目标。
- [x] 固定跨租户泄漏、严重金融幻觉、未授权 Agent/Skill 调用和严重沙箱失败数量为 0。
- [x] 明确目标服务器资源不足时通过扩容或调整拓扑解决，不能删除发布指标。
- [x] 将第 4 项核心目标扩展为 Memory 与 Multimodal Knowledge Base，五项目标数量不变。
- [x] 固定 P0 支持 PDF/扫描 PDF/PNG/JPEG 的安全处理、OCR、版面分析、表格提取和页级/区域级引用。
- [x] 固定 P1 支持 APP/H5 图片上传、截图问答和合同局部图片解读。
- [x] 固定 P2 只预留 ASR/TTS；视频理解、实时视频客服和图片生成不在范围内。
- [x] 增加多模态用户故事、OCR/表格/引用质量指标、文件安全与沙箱门禁。
- [x] 第 1 步范围内未创建接口契约、业务代码或基础设施。

### 第 2 步：业务架构、安全模型与部署拓扑

- [x] 创建 `specs/architecture/system-context.md`，明确系统边界、外部参与者、信任边界和架构不变量。
- [x] 创建 `specs/architecture/container-view.md`，明确 Channel Gateway、LLM Gateway、Agent Runtime、Skill Registry、Memory、Knowledge、MCP、沙箱和观测容器职责。
- [x] 创建 `specs/architecture/data-flow.md`，明确 APP/H5 消息、多模态文档、动态业务、Agent Run、Kafka 事件、重试、死信和 Trace 数据流。
- [x] 创建 `specs/architecture/security-model.md`，明确身份、租户隔离、Agent/Skill、文件、模型、沙箱、审计和威胁控制。
- [x] 创建 `specs/architecture/deployment-view.md`，明确 Local/Test/Performance/Production 环境、网络边界、Compose 起步、容量 profile、发布、备份和恢复。
- [x] 创建 8 个 ADR，记录语言分工、数据存储、Kafka 语义、Agent/Skill 编排、LLM Gateway、沙箱、多环境部署和多模态入库决策。
- [x] 未创建 Go/Python/Next.js 工程，不安装依赖，不启动 Docker，不购买服务器或域名。

### 第 3 步：统一消息、API、工具和事件契约

- [x] 创建 `contracts/openapi/channel-api.openapi.json`，定义 APP/H5 受控文件上传、统一消息接收、SSE 恢复和取消契约；终端请求不能指定可信 `tenant_id` 或 `user_id`。
- [x] 创建 `contracts/openapi/llm-gateway.openapi.json`，定义内部 OpenAI 兼容 Chat/SSE、服务身份、租户、Run、Step、Trace、幂等和受控图片引用契约。
- [x] 创建 14 个 JSON Schema，覆盖公共类型、错误码、受控文件对象、统一 content parts、统一消息、LLM Provider、Agent Manifest、Skill Manifest、Run/Task/Step/Event、MCP Tool、Memory、Knowledge、多模态处理事件和沙箱任务。
- [x] 固定图片和文件只使用租户内 `agentforge://objects/...` 或对象引用，不允许模型服务访问任意公网文件 URL。
- [x] 固定 Agent/Skill 的版本、权限、租户可见性、依赖、预算、超时、重试、并发、副作用、审批、幂等和验收场景字段。
- [x] 固定 Run 快照包含 Agent、Skill、Tool、Model、Memory Policy 和 Knowledge Version，支持后续确定性回放和 Checkpoint 恢复。
- [x] 创建 `contracts/asyncapi/kafka.asyncapi.json`，定义 12 个 Kafka Channel，覆盖统一消息、Agent、Skill、Memory、文档、Embedding、Knowledge 发布、审计、评测和死信。
- [x] 固定 Kafka 至少一次投递、分区键、事件版本、幂等键、关联/因果 ID、Trace、重试次数和兼容策略。
- [x] 创建 Channel、LLM Gateway、Agent Runtime、Knowledge、MCP、Memory 和 Sandbox 共 7 份简体中文 Gherkin 验收规格；字段名、错误码、接口路径和标签保留标准技术名称。
- [x] 验收场景覆盖租户身份、重复消息、同会话有序、SSE 恢复、取消传播、模型能力路由、有限重试、Skill 授权、预算、审批、Checkpoint、文件安全、引用、动态数据、Memory 隔离和沙箱资源边界。
- [x] 根据用户确认同步第 1、2 步规格页头为“已确认”，并将 8 个 ADR 状态同步为 `Accepted`；未修改其设计内容。
- [x] 未创建 Go/Python/Next.js 工程，未安装依赖，未启动 Docker，也未实现任何业务服务。

#### 第 3 步实际验证

- `ConvertFrom-Json`：17 个 OpenAPI/AsyncAPI/JSON Schema 文件全部通过 JSON 语法解析。
- 自定义 PowerShell `$ref` 检查：17 个文件的外部文件引用和 JSON Pointer 均可解析。
- OpenAPI 顶层检查：2 个文件均为 OpenAPI 3.1.0，且包含有效 Paths。
- AsyncAPI 顶层检查：AsyncAPI 2.6.0，12 个 Channel 均可枚举。
- Gherkin 结构检查：7 个 `acceptance.feature` 均声明 `# language: zh-CN`，并包含功能、场景、假如、当和那么。
- 禁用表述检查：未出现禁止的渠道和背景表述。
- `git diff --check`：通过。
- 当前环境没有预装 `jsonschema`、OpenAPI 或 AsyncAPI 专用 Linter；本步没有为校验临时安装依赖。第 4 步将在工程门禁中提供固定版本的正式规格检查命令。

### 第 4 步：仓库骨架与最小工程门禁

- [x] 用户确认第 3 步后开始第 4 步，没有提前实现第 5 步或任何业务模块。
- [x] 创建 `specs/engineering/repository-foundation.md`，定义仓库骨架的目标、非目标、命令契约、状态、安全不变量、指标、依赖取舍和验收方式。
- [x] 创建 `specs/engineering/repository-foundation.feature`，增加结构、规格失败、离线门禁和能力边界 4 个中文 Gherkin 场景。
- [x] 创建 `services/`，声明 Channel、LLM Gateway、Agent Runtime、Skill Registry、Memory、MCP、Sandbox、Knowledge 和 Document Processor 服务边界。
- [x] 创建 Go Workspace 和最小可编译包，未增加 Go 第三方依赖或业务逻辑。
- [x] 创建 Python 根工作区、Knowledge、Document Processor 和 Harness 的空 `pyproject.toml`，未增加 Python 第三方依赖或业务逻辑。
- [x] 创建 `web/` 私有 Node.js/pnpm 工作区，固定脚本契约，未安装 Next.js、React 或其他 Web 依赖，未创建页面。
- [x] 创建 `harness/` 的 Fake、Mock、Fixture、Replay 和 Generator 边界，未提前实现第 6 步 Harness。
- [x] 创建 `tests/` 的单元、契约、集成、端到端、安全和性能测试分层。
- [x] 创建 `infra/` 的 Compose、环境、可观测性和运维脚本边界；未创建 Compose 栈，未启动任何基础设施。
- [x] 创建 `reports/` 证据目录并配置忽略规则，保留说明但忽略生成报告。
- [x] 固定 Go 1.26.2、Python 3.13.14、Node.js 24.14.0 和 pnpm 11.9.0 的工具版本边界。
- [x] 创建 `tools/check.py` 统一离线门禁以及 PowerShell/Bash 转发脚本，覆盖 `structure`、`specs`、`format`、`static`、`test` 和 `ci`。
- [x] 规格门禁检查 JSON 语法、本地 `$ref`/JSON Pointer、OpenAPI/AsyncAPI/JSON Schema 顶层、中文 Gherkin 结构和禁用表述。
- [x] 门禁只使用 Python/Go/Node 标准工具，不下载依赖，不连接模型或金融接口，不启动 Docker。
- [x] 创建 GitHub Actions 最小质量门禁，并与本地共用 `python tools/check.py ci`。
- [x] 增加 `.editorconfig`、`.gitattributes` 和 `.gitignore`，忽略密钥、缓存、依赖、基础设施本地数据和生成报告。
- [x] 更新根 `README.md`，说明当前状态、目录职责、环境版本和统一检查命令。
- [x] 未实现 Channel、RAG、LLM Gateway、Agent Runtime、Agent/Skill Registry、Memory、MCP 或 Sandbox 业务。

#### 第 4 步实际验证

- 首次 `python tools/check.py ci` 在格式门禁发现两个 Go 文件末尾不符合 `gofmt`；按 `gofmt -d` 结果修正，没有放宽门禁。
- 第二次门禁在 `go vet` 阶段发现 Windows 默认 Go 缓存目录无写权限；将 `GOCACHE` 固定到仓库内已忽略的 `.agentforge-cache/go-build` 后解决，没有申请额外权限。
- 完整 `python tools/check.py ci`：通过；检查 17 个 JSON 契约、8 个中文 Feature 和 38 个场景，并通过结构、格式、静态和 Go/Python/Node 基础测试。
- 门禁执行期间没有安装依赖、访问外部模型/金融接口或启动基础设施。

### 第 5 步：最小本地基础设施

- [x] 用户确认第 4 步后开始第 5 步，没有提前实现第 6 步 Harness 或任何业务模块。
- [x] 创建 `specs/engineering/local-infrastructure.md` 与中文 Gherkin 验收规格，定义目标、非目标、组件版本、配置、网络、健康、持久化、错误语义和边界。
- [x] 创建固定版本的 Compose，包含 MySQL 8.4.7、Redis 8.2.3、Kafka 4.1.1、MinIO、OpenSearch 3.3.2、etcd 3.5.18 和 Milvus 2.6.6，未使用 `latest`。
- [x] 创建 Local/Test 配置模板；两套环境使用不同 Compose 项目名、宿主机端口、本地占位凭证和命名卷，不包含生产密钥或真实金融数据。
- [x] Local MySQL 使用宿主机 `127.0.0.1:3307`，避让开发机已有 MySQL57 的 `3306`；容器内仍使用标准端口 3306。
- [x] 建立 `agentforge-data` 内部数据网络和 `agentforge-local-access` 本机访问网络；组件间只使用内部地址，需要调试的端口只绑定 `127.0.0.1`，etcd 不发布端口。
- [x] 为 7 个常驻组件配置健康检查；MinIO 初始化任务幂等创建 AgentForge 与 Milvus 本地 Bucket，成功后退出。
- [x] 为 MySQL、Redis、Kafka、MinIO、OpenSearch、etcd 和 Milvus 分别配置持久卷；Redis 启用 AOF。
- [x] 创建 `tools/infra.py` 统一控制器以及 PowerShell/Bash 包装入口，支持配置、拉取、启动、等待、状态、Smoke、重启验证、停止和显式确认销毁。
- [x] `restart-verify` 使用随机合成探针验证 7 类组件重启后的数据行为，并在验证后清理探针。
- [x] Smoke 从宿主机逐一验证 MySQL、Redis、Kafka、MinIO API/Console、OpenSearch、Milvus API/Health 共 8 个发布端口真实可达，避免把仅有 Compose 端口声明误判为可访问。
- [x] 普通 `down` 只删除容器与网络，保留 7 个命名卷；卷销毁必须传入环境对应的显式确认文本。
- [x] 将 Compose 模型检查加入 `python tools/check.py ci`，持续校验固定镜像、健康检查、网络、端口、卷和 Local/Test 隔离。
- [x] 未创建金融业务表、Kafka 业务 Topic、正式索引或 Milvus Collection；未实现 Channel、RAG、Gateway、Agent、Skill、Memory、MCP、Sandbox、可观测平台或生产发布。

#### 第 5 步实际验证

- `python tools/infra.py config-all`：通过；Local/Test 各包含 8 个服务、7 个卷，项目名与宿主机端口无冲突。
- 首次拉取固定镜像时 Milvus 大分层在外层命令约 32 分钟后超时；保留已下载分层并用 `docker pull --quiet milvusdb/milvus:v2.6.6` 续传成功，没有改用浮动标签或旧版本。
- 首次启动发现宿主机 MySQL57 已占用 3306；没有停止既有服务，将 AgentForge Local MySQL 宿主机端口调整为 3307 后重新验证。
- 真实运行发现 Docker Desktop 29.4.3 对只连接 `internal: true` 网络的容器不建立宿主机端口映射；通过可清理的临时容器复现后，拆分内部数据网络与本机访问网络，保持所有发布端口只监听 `127.0.0.1`。
- 首次 Smoke 发现 etcd 3.5.18 镜像没有 `/bin/sh`；将 etcd 探针改为直接参数执行 `etcdctl`，没有跳过 etcd 验证。
- `python tools/infra.py up --env local`：通过；MySQL、Redis、Kafka、MinIO、OpenSearch、etcd、Milvus 全部 `healthy`，`minio-init` 退出码为 0。
- `python tools/infra.py smoke --env local`：通过；7 个组件与两个 MinIO Bucket 均可访问，实际宿主机端口只绑定 `127.0.0.1`，etcd 无宿主机端口。
- `python tools/infra.py restart-verify --env local`：通过；7 类合成探针在容器重启后全部可读，并完成清理。
- `python tools/infra.py down --env local`：通过；Local 容器与两张网络全部移除，7 个命名卷全部保留。
- `python tools/infra.py destroy --env local`（未提供确认文本）：按预期拒绝执行，证明普通命令不能误删持久卷。
- 完整 `python tools/check.py ci`：通过；检查 17 个 JSON 契约、9 个中文 Feature、43 个场景，并通过结构、格式、Local/Test Compose 配置、静态和 Go/Python/Node 基础测试。
- `git diff --check`：通过；仅有 Git 对 `.gitignore` 后续可能进行 LF/CRLF 转换的非阻断提示。

## 需要你在继续前确认

阅读以下第 5 步文件后，确认基础设施边界和统一命令是否符合要求：

1. `specs/engineering/local-infrastructure.md`：本步组件、网络、健康、持久化和非目标。
2. `infra/compose/compose.yaml`：固定镜像、健康检查、两张网络、端口和命名卷如何组合。
3. `infra/environments/local.env.example` 与 `test.env.example`：Local/Test 如何隔离。
4. `tools/infra.py`：统一生命周期、Smoke 和持久化验证如何执行。
5. `specs/engineering/local-infrastructure.feature`：本步必须满足的 Given/When/Then 场景。

如果组件版本、端口、网络或数据语义需要调整，应先修改第 5 步，再进入第 6 步。

## 下一步（尚未开始）

### 第 6 步：金融客服 Harness

计划创建：

```text
Fake LLM/视觉响应与 Mock MCP
固定文本 PDF、扫描件、图片、表格和渠道消息
Agent/Skill 回放、安全样例与数据生成器
```

第 6 步会建立确定性的正常、失败、超时、断流、越权和恢复场景，让后续 AI 与业务能力不依赖真实模型随机输出或真实资金方接口。

第 6 步仍不会接入真实模型、真实征信、银行或资金方接口，也不会提前实现第 7 步知识库写入业务。

## 决策记录摘要

| 决策 | 当前结论 | 说明 |
|---|---|---|
| 业务定位 | 企业级金融贷款 APP/H5 双渠道 AI 智能客服 | 围绕金融客服业务闭环完成建设、上线和持续运维 |
| 永久技术主线 | Agent Runtime/Agent 编排/Skill、Sandbox、LLM Gateway、Memory/Multimodal Knowledge Base、高并发与百万级 RAG | 五项不得删除、替换或降级 |
| 多模态范围 | P0 文档多模态、P1 图片问答、P2 语音预留 | 不建设视频理解、实时视频客服和图片生成 |
| 主要渠道 | H5 首先打通，APP 按统一适配契约接入 | APP 与 H5 共用后端业务链路，不扩展其他渠道 |
| 知识与动态数据 | 金融知识走 RAG；实时信息走 MCP/业务接口 | 模型不得编造利率、额度、征信和审批结果 |
| 开发方式 | SDD + Harness | 先规格，后实现，每项能力都可验证 |
| 推进节奏 | 一次一个步骤 | 每步结束必须暂停并等待确认 |
| 关系数据库 | MySQL 8.0+ | 与现有经验一致；租户隔离由应用层 + Harness 保证 |
| 发布目标 | Linux + Docker Compose + HTTPS | 五项目标先通过功能、安全和性能门禁，再部署并在目标服务器复验 |
| 首发数据 | 虚构、合成或脱敏数据 | 未获授权前不连接真实征信、银行或资金方生产接口 |
| 初期模型 | Fake LLM / 外部兼容 API | Ollama、vLLM 和微调逐步引入 |
| 规模顺序 | 小数据正确性基线 → 阶梯扩容 | 正式发布前必须完成并通过约定并发级别和 100 万向量验证 |
| GA 容量目标 | 1000 SSE 连接、100 活跃生成、100 万向量 | 第 2 步必须选择可以支撑目标的部署拓扑 |
| GA 可用性 | ≥ 99.9% | 通过监控数据按月统计 |
| 数据恢复 | RPO ≤ 1 小时，RTO ≤ 2 小时 | 必须通过备份恢复演练验证 |

## 进度更新规则

后续每完成一步，在此追加：

- 完成日期和步骤名称
- 新增/修改的关键文件
- 实际执行的验证命令与结果
- 本步的关键原理与结论
- 遇到的问题和取舍
- 明确的暂停点与下一候选步骤
