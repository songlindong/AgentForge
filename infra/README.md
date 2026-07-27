# Infrastructure

本目录承载本地、测试、性能和生产基础设施定义。

当前第 4 步只预留：

- `compose/`：第 5 步开始建立本地 Docker Compose
- `environments/`：不含密钥的环境配置模板
- `observability/`：后续 OpenTelemetry、指标、Trace、日志和告警配置
- `scripts/`：后续部署、迁移、备份、恢复和回滚脚本

当前没有 Compose 文件，不会启动任何基础组件，也不会提前引入 Kubernetes。

