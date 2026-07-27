# Infrastructure

本目录承载本地、测试、性能和生产基础设施定义。

第 5 步已经建立：

- `compose/`：MySQL、Redis、Kafka、MinIO、OpenSearch、etcd 和 Milvus 的固定版本 Compose
- `environments/`：不含生产密钥的 Local/Test 配置模板
- `observability/`：后续 OpenTelemetry、指标、Trace、日志和告警配置
- `scripts/`：后续部署、迁移、备份、恢复和回滚脚本

统一入口位于 `tools/infra.py`。当前仍没有业务服务、完整可观测平台或 Kubernetes 配置。
