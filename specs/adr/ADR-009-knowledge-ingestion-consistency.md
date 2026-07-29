# ADR-009：知识入库一致性、发布门禁与测试 Provider

状态：Accepted  
日期：2026-07-28

## 背景

知识入库跨越 MySQL、MinIO、Kafka、OpenSearch 与 Milvus，无法依赖一个覆盖全部组件的分布式事务。Kafka 至少一次投递、Consumer 重启和单侧索引失败都可能产生重复副作用或半发布版本。第 7 步还需要在不连接付费 OCR 与 Embedding 服务时验证真实文件和真实存储结构。

## 决策

1. MySQL 是任务状态、版本和发布状态的唯一真相源。
2. 业务状态变化与 Outbox 事件在同一 MySQL 事务提交；独立 Publisher 负责把 Outbox 投递到 Kafka。
3. Consumer 使用 tenant_id、consumer_name 与 event_id 的 Inbox 唯一键去重。
4. 文档、片段、对象键和索引主键由输入与版本确定性生成，所有外部写入采用 Upsert。
5. OpenSearch 与 Milvus 使用共享逻辑索引，记录中强制包含 tenant_id；所有查询和删除必须带租户过滤。
6. 只有 MySQL 片段数、OpenSearch 写入数和 Milvus 写入数一致，且模型与索引版本匹配时，才能创建不可变的 Knowledge Version。
7. 定义 DocumentSandboxPort、OCRProviderPort、EmbeddingProviderPort。Local/Test 可使用固定 Harness OCR 和确定性非零 Hash Embedding，输出必须标记 test_model=true。
8. Production Profile 禁止测试 Provider、禁止进程内解析实现，并在缺少恶意文件扫描或隔离执行实现时 Fail Closed。

## 被否决方案

### 跨组件双写后直接发 Kafka

应用进程在数据库提交后、消息发送前退出会丢事件；先发消息后提交又会让 Consumer 看到不存在的状态。

### 依赖 Kafka 恰好一次解决全部一致性

Kafka 事务不能覆盖 MinIO、MySQL、OpenSearch 和 Milvus，外部副作用仍需幂等和发布门禁。

### 每个租户创建独立索引

大量小租户会造成索引和 Collection 数量膨胀。共享索引加服务端强制租户字段更适合当前阶段，并由跨租户 Harness 验证。

### 用全零向量代替 Embedding

全零向量无法验证归一化、维度和索引写入约束。确定性 Hash Embedding 只验证流程，不作为检索质量或生产模型。

## 后果

- 需要 Outbox Publisher、Inbox 去重、索引对账和失败重试任务。
- 删除和替换采用版本化补偿，不依赖跨组件回滚。
- 测试结果可重复，但不能据此声明真实 OCR、Embedding 质量或生产沙箱已经完成。
- 第 8 步必须用黄金集比较真实 Provider；第 15 步必须把不可信解析接入正式隔离环境。
