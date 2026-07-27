# Tests

测试按风险和反馈速度分层：

| 目录 | 用途 |
|---|---|
| `unit/` | 单个函数、状态机或策略的快速测试 |
| `contract/` | OpenAPI、Schema、AsyncAPI、Agent/Skill/MCP 契约测试 |
| `integration/` | 跨服务与真实基础组件的集成测试 |
| `e2e/` | APP/H5 到回答、引用、工具和转人工的端到端测试 |
| `security/` | 租户越权、文件攻击、提示注入和沙箱隔离测试 |
| `performance/` | k6、SSE 并发、Gateway 与百万向量实验 |

第 4 步只创建分层边界；业务测试将在对应实施步骤逐步加入。

