# Harness

本目录承载第 6 步完成的可重复验证环境，而不是生产业务逻辑。

## 能力边界

- Fake LLM：OpenAI 风格 JSON/SSE、视觉输入、Tool Call、延迟、429、5xx、超时、断流和非法 JSON。
- Mock MCP：四个虚构贷款工具及正常、依赖失败、超时、拒绝、审批和非法 JSON 场景。
- Fixtures：文本 PDF、扫描 PDF、PNG/JPEG、还款表格、APP/H5 消息、黄金标注和无害安全样例。
- Replay：九类 Agent、Skill、渠道和沙箱风险黄金事件一致性验证。
- Generators：固定 Seed 的 Gateway 请求和流式向量 JSONL 生成器。

这些实现不连接真实模型、Milvus、征信、银行或资金方接口，也不构成生产服务。

## 统一命令

```powershell
python -m harness.agentforge_harness verify
python -m harness.agentforge_harness replay --all
python -m harness.agentforge_harness serve-fake-llm --port 18081
python -m harness.agentforge_harness serve-mock-mcp --port 18082
python -m harness.agentforge_harness generate-gateway --count 10 --seed 20260728 --output tmp/gateway.jsonl
python -m harness.agentforge_harness generate-vectors --count 100 --dimension 16 --seed 20260728 --output tmp/vectors.jsonl
```

两个 HTTP 服务默认且只能监听 Loopback。Fixture 重新生成需要 PDF 工具依赖，日常 `verify` 和 CI 只使用 Python 标准库。
