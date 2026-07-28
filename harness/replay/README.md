# Replay

`scenarios/` 保存 Agent、Skill、渠道和沙箱的九类黄金事件。Runner 只检查版本快照、连续 sequence、租户、Trace、错误码、最终状态和幂等副作用，不实现真正的 Agent 调度器。
