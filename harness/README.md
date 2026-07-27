# Harness

本目录承载可重复验证环境，而不是生产业务逻辑。

后续按第 6 步增加：

- Fake LLM 和 Fake Vision Provider
- Mock MCP 与受控业务接口
- Channel、Agent、Skill 和 Checkpoint 场景回放
- 固定 PDF、扫描件、PNG/JPEG、表格和黄金问题
- 故障注入、安全样例、并发和百万向量数据生成器

当前仅声明 `fakes/`、`mocks/`、`fixtures/`、`replay/` 和 `generators/` 边界，不提供实现。

