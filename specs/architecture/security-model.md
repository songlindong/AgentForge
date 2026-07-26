# AgentForge 安全模型与信任边界

状态：第 2 步架构规格基线，待确认  
版本：0.1.0  
更新日期：2026-07-26

## 1. 保护目标

- 防止跨租户数据泄漏。
- 防止用户、文档、模型或工具结果注入恶意指令。
- 防止未经授权的 Agent、Skill、MCP 或沙箱调用。
- 防止原始金融文件、个人敏感信息和凭证泄漏。
- 防止不可信文件和代码影响宿主机或其他任务。
- 保证高风险操作可确认、可追踪、可回滚或转人工。
- 保证部署、备份、恢复、发布和回滚可审计。

## 2. 资产分类

| 资产 | 敏感级别 | 保护要求 |
|---|---|---|
| 产品、政策、合同和 FAQ | 中/高 | 租户隔离、版本、发布审核、引用追踪 |
| OCR/版面/表格结果 | 高 | 原文件关联、区域定位、脱敏、租户隔离 |
| 用户会话和 Memory | 高 | 最小读取、删除/过期、租户/用户隔离 |
| 利率、额度、征信、审批结果 | 极高 | 授权工具实时获取、最小暴露、完整审计 |
| Agent/Skill/模型配置 | 高 | 版本、审批、权限、灰度、回滚 |
| MCP 凭证和模型密钥 | 极高 | Secret 管理、不可写日志、最小权限 |
| Run/Task/Trace/审计事件 | 高 | 追加写、访问控制、脱敏、保留策略 |
| 沙箱任务和文件 | 高 | 资源/网络/文件隔离、任务销毁 |

## 3. 信任区域

```text
Zone 0：不可信输入
  APP/H5 文本、图片、文件、用户 Prompt、外部回调

Zone 1：边缘接入
  Nginx/Caddy、Channel Gateway、限流、TLS、认证入口

Zone 2：受控应用平面
  Agent Runtime、Skill Registry、LLM Gateway、Memory、Knowledge、MCP Gateway

Zone 3：高敏数据平面
  MySQL、Redis、Kafka、Milvus、OpenSearch、MinIO、审计

Zone 4：隔离执行平面
  OCR/文档解析沙箱、代码/规则沙箱、临时任务容器

Zone 5：外部依赖
  身份提供商、模型服务、金融业务系统、对象外部接口
```

跨区域访问必须经过明确的身份、租户、权限、Schema、网络和审计检查。

## 4. 身份和访问控制

### 4.1 身份认证

- 用户和后台人员通过 Keycloak/OIDC/OAuth2 登录。
- APP/H5 使用短期 Access Token 和可撤销 Refresh Token。
- 服务间调用使用服务身份，不共享用户 Token。
- 外部业务接口使用独立凭证和最小权限。

### 4.2 授权

- Casbin 负责 RBAC、资源和工具策略。
- `tenant_id` 从经过验证的身份和服务端策略获得，不能信任请求体中的值。
- 授权判断同时考虑主体、租户、资源、Skill、工具、数据敏感级别和操作类型。
- 高风险工具需要人工审批或二次确认。

### 4.3 权限检查点

```text
入口认证
→ 租户解析
→ Agent/Skill 解析
→ Memory/RAG 数据过滤
→ MCP 工具授权
→ 沙箱任务授权
→ 输出字段过滤
→ 审计写入
```

## 5. 多租户隔离

所有业务表、缓存、事件、索引、对象和审计都必须携带或可推导 `tenant_id`。

强制规则：

- MySQL Repository 查询必须显式带 `tenant_id`。
- Redis Key 使用租户前缀。
- Kafka 事件包含租户字段，消费者不能使用外部租户值覆盖身份租户。
- Milvus 和 OpenSearch 查询必须进行租户过滤。
- MinIO 使用租户前缀和私有 Bucket，签名 URL 短期有效。
- Memory、Skill、Agent、缓存、Trace 和导出文件都必须进行租户隔离。
- 任何跨租户测试成功读取或修改数据都视为发布阻断问题。

## 6. Agent、Skill 和 Prompt 安全

- Agent 只能绑定已发布、租户可见、权限允许和版本兼容的 Skill。
- Skill Manifest、Schema、依赖和实现类型必须通过校验。
- 用户输入、RAG 文档、工具结果和图片 OCR 文本都视为不可信内容。
- 系统规则、租户策略和 Skill 权限不能被用户或文档内容覆盖。
- Tool/Skill 输出进入模型上下文前必须标记来源、可信级别和租户。
- Agent 编排设置步数、时间、Token、费用、并发和深度上限。
- 运行中不允许动态加载未经注册的 Prompt、Skill 或工具。
- Agent、Skill、Model、Memory 和 Knowledge 版本写入 Run 快照，保证回放一致。

## 7. 文件和多模态安全

文件进入 OCR 或模型链路前必须：

1. 检查扩展名、MIME 和文件魔数。
2. 限制文件大小、页数、像素、压缩比例和解压后大小。
3. 执行恶意文件扫描和 PDF/图片解析器安全检查。
4. 清理 EXIF 和不需要的元数据。
5. 放入租户隔离的私有对象存储。
6. 在默认禁网、非 root、只读文件系统的沙箱中解析。
7. 保存页码、区域坐标、来源对象和提取模型版本。
8. OCR 结果在进入 Prompt 前执行 Prompt Injection 检查。

## 8. 沙箱模型

第一版使用 Docker 临时容器：

- non-root
- 只读根文件系统
- 默认无网络
- 禁止 Docker Socket
- CPU、内存、PID 和时长限制
- 受控临时目录
- 镜像白名单
- 不挂载宿主机敏感目录
- 任务结束销毁容器、进程和临时数据
- 沙箱资源和退出状态进入 Trace/审计

后续是否采用 Kubernetes Job、seccomp、AppArmor/SELinux 或 gVisor，由安全与容量报告决定。

## 9. 模型和外部系统安全

- LLM Gateway 不把外部响应视为天然可信。
- 模型输出必须经过 Schema、引用、有据性和合规检查。
- 实时金融数据必须带工具来源和时间戳。
- 外部业务系统调用必须设置超时、重试、熔断、幂等和最小字段返回。
- 外部网络访问默认拒绝，只允许配置的域名/服务。
- 模型和业务凭证不能出现在 Prompt、日志、Trace 或普通数据库字段中。

## 10. 审计与隐私

审计事件至少记录：

```text
event_id, tenant_id, actor_id, actor_type, action, resource_type,
resource_id, agent_id, skill_id, tool_id, decision, reason,
trace_id, created_at
```

日志和 Trace 不记录完整身份证号、手机号、银行卡号、征信原文、模型密钥或完整文件内容。高敏原文只通过受控引用查看。

## 11. 关键威胁和控制

| 威胁 | 控制 |
|---|---|
| 跨租户查询 | 服务端 tenant_id、Repository 检查、索引过滤、恶意测试 |
| Prompt Injection | 内容分区、来源标记、工具策略、输出检查、拒答/转人工 |
| 恶意 PDF/图片 | 魔数检查、恶意扫描、沙箱解析、资源限制 |
| Skill 越权 | Registry、Manifest、Casbin、版本和运行时权限 |
| 工具重复副作用 | 幂等键、审批、状态机、补偿和审计 |
| 模型编造动态数据 | 强制 MCP、来源校验、失败拒答 |
| 沙箱逃逸 | non-root、禁网、只读、无 Socket、资源限制、攻击测试 |
| 凭证泄漏 | Secret 管理、最小权限、日志脱敏、轮换 |
| 生产误发布 | CI 门禁、灰度、健康检查、回滚和审批 |

## 12. 安全不变量

- 跨租户泄漏数量为 0。
- 未授权 Agent/Skill/MCP/Sandbox 调用数量为 0。
- 严重沙箱逃逸测试失败数量为 0。
- 严重金融幻觉数量为 0。
- 高风险操作审计覆盖率为 100%。
- 生产密钥进入 Git、日志或 Trace 的数量为 0。
