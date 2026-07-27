# ADR-007：Docker Compose 起步并保留扩容路径

状态：Accepted
日期：2026-07-26

## 背景

系统需要先在可控环境完成 APP/H5、Agent、RAG、沙箱和 Gateway 闭环，同时保留 1000 SSE、100 活跃生成和百万向量的扩容路径。

## 决策

- Local/Test 使用 Docker Compose 和固定版本。
- 初始生产使用 Linux + Docker Compose + Nginx/Caddy + HTTPS。
- 性能环境允许把应用、数据、模型和沙箱拆到不同节点。
- 达到多实例、高可用或弹性扩缩容条件后，通过新的 ADR 评估 Kubernetes。
- 生产发布必须经过性能门禁、备份恢复、灰度/滚动和回滚。

## 后果

Compose 不是高可用方案；如果目标容量或 RTO/RPO 不能满足，必须扩容或调整拓扑，不能降低产品规格。
