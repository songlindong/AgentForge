# AgentForge 分步实施进度

最后更新：2026-07-26

## 当前状态

**状态：第 2 步“业务架构、安全模型与部署拓扑”已完成，等待用户确认。**

当前没有正在实现的业务步骤。下一候选步骤是“第 3 步：统一消息、API、工具和事件契约”，只有用户确认第 2 步后才能开始。

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

## 需要你在继续前确认

阅读以下第 2 步架构规格后，确认服务边界、数据流、安全模型和部署假设是否符合要求：

1. `specs/architecture/system-context.md`：系统边界、参与者、核心上下文和信任边界。
2. `specs/architecture/container-view.md`：容器职责、Agent Runtime 内部组件和调用边界。
3. `specs/architecture/data-flow.md`：消息、文档、动态数据、Run 恢复、Kafka 和 Trace 流程。
4. `specs/architecture/security-model.md`：身份、租户、文件、Agent/Skill、沙箱和审计控制。
5. `specs/architecture/deployment-view.md`：环境、网络、容量、发布、备份和恢复拓扑。
6. `specs/adr/`：8 个关键架构取舍。

如果服务边界、数据流或部署假设需要调整，应先修改第 2 步规格，再进入第 3 步。

## 下一步（尚未开始）

### 第 3 步：统一消息、API、工具和事件契约

计划只创建：

```text
contracts/openapi/
contracts/json-schema/
contracts/asyncapi/
specs/modules/*/acceptance.feature
```

本步会讲清：

- 统一消息、Chat/SSE、文件对象引用、LLM Provider、Agent/Skill、Memory、MCP 和 Kafka 事件字段。
- OpenAPI、JSON Schema、AsyncAPI 和 Gherkin 分别解决什么问题。
- 幂等键、版本、错误码、重试、超时和兼容策略如何表达。

本步不会创建 Go/Python/Next.js 工程，也不会启动 Docker。

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
