# ADR-004：Agent 编排与 Skill Registry

状态：Proposed  
日期：2026-07-26

## 背景

金融客服需要产品检索、合同解读、还款试算和合规检查等能力。直接让模型自由调用工具会产生越权、不可回放和不可控成本。

## 决策

- Agent Runtime 提供 Run Context、Router、Planner、Orchestrator、Scheduler、Checkpoint 和 Replay。
- Agent 通过 Skill Registry 发现能力，不能调用未注册的工具或 Prompt。
- Skill 使用 Manifest、输入/输出 Schema、版本、依赖、权限、租户可见性、超时、重试、并发和副作用等级。
- 编排支持顺序、并行、条件、DAG、人工审批、取消和恢复。
- P0 采用有边界的受控编排，不允许无限循环或无预算的自主 Multi-Agent。
- Agent、Skill、Model、Memory、Knowledge 和 Tool 版本写入 Run 快照。

## 后果

需要建设 Skill 生命周期、兼容性检查、灰度、回滚、契约测试和编排回放；第 3、11、12 步分别落地契约和实现。
