"""验证 Agent、Skill、Channel 与 Sandbox 黄金事件的一致性。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPLAY_DIRECTORY = Path(__file__).resolve().parents[1] / "replay" / "scenarios"
REQUIRED_RISKS = {
    "disabled-skill": "disabled_skill",
    "incompatible-skill-version": "incompatible_skill_version",
    "tenant-skill-denied": "tenant_skill_denied",
    "required-dependency-failure": "required_dependency_failure",
    "budget-exhausted": "budget_exhausted",
    "checkpoint-recovery": "checkpoint_recovery",
    "duplicate-channel-message": "duplicate_channel_message",
    "sandbox-resource-exhausted": "sandbox_resource_exhausted",
    "sandbox-policy-denied": "sandbox_policy_denied",
}


class ReplayError(RuntimeError):
    pass


def load_scenarios(directory: Path = REPLAY_DIRECTORY) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReplayError(f"回放文件无法解析: {path.name}: {exc}") from exc
        if not isinstance(value, dict):
            raise ReplayError(f"回放文件顶层必须是 Object: {path.name}")
        value["_source"] = path.name
        scenarios.append(value)
    return scenarios


def validate_scenario(scenario: dict[str, Any]) -> None:
    source = scenario.get("_source", "<memory>")
    scenario_id = scenario.get("scenario_id")
    risk = scenario.get("risk")
    if scenario_id not in REQUIRED_RISKS:
        raise ReplayError(f"{source}: 未注册 scenario_id: {scenario_id}")
    if REQUIRED_RISKS[scenario_id] != risk:
        raise ReplayError(f"{source}: risk 与 scenario_id 不匹配")
    context = scenario.get("context")
    events = scenario.get("events")
    expected = scenario.get("expected")
    snapshot = scenario.get("snapshot")
    if not isinstance(context, dict) or not isinstance(expected, dict):
        raise ReplayError(f"{source}: 缺少 context 或 expected")
    if not isinstance(snapshot, dict) or not all(
        key in snapshot for key in ("agent", "skills", "model", "knowledge_version")
    ):
        raise ReplayError(f"{source}: 版本快照不完整")
    if not isinstance(events, list) or not events:
        raise ReplayError(f"{source}: events 必须是非空数组")
    tenant_id = context.get("tenant_id")
    trace_id = context.get("trace_id")
    if not isinstance(tenant_id, str) or not tenant_id:
        raise ReplayError(f"{source}: tenant_id 无效")
    if not isinstance(trace_id, str) or len(trace_id) != 32:
        raise ReplayError(f"{source}: trace_id 无效")
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ReplayError(f"{source}: event[{index}] 不是 Object")
        if event.get("sequence") != index:
            raise ReplayError(f"{source}: sequence 必须从 0 连续递增")
        if event.get("tenant_id") != tenant_id:
            raise ReplayError(f"{source}: event[{index}] tenant_id 不一致")
        if event.get("trace_id") != trace_id:
            raise ReplayError(f"{source}: event[{index}] trace_id 不一致")
    last = events[-1]
    if last.get("status") != expected.get("terminal_status"):
        raise ReplayError(f"{source}: 最终状态与 expected 不一致")
    expected_code = expected.get("error_code")
    if expected_code is not None and last.get("error_code") != expected_code:
        raise ReplayError(f"{source}: 最终错误码与 expected 不一致")

    if risk == "checkpoint_recovery":
        side_effects = [
            event.get("idempotency_key")
            for event in events
            if event.get("event_type") == "side_effect_completed"
        ]
        if not side_effects or len(side_effects) != len(set(side_effects)):
            raise ReplayError(f"{source}: Checkpoint 回放重复了幂等副作用")
        if any(event.get("replayed") is True for event in events):
            raise ReplayError(f"{source}: 已完成副作用不得标记为再次执行")
    elif risk == "duplicate_channel_message":
        accepted = sum(
            event.get("event_type") == "message_accepted" for event in events
        )
        if accepted != expected.get("accepted_count") or accepted != 1:
            raise ReplayError(f"{source}: 重复消息必须只接受一次")
    elif risk == "sandbox_resource_exhausted":
        if expected.get("cleanup_verified") is not True:
            raise ReplayError(f"{source}: 资源耗尽后必须验证清理")


def replay_all(directory: Path = REPLAY_DIRECTORY) -> int:
    scenarios = load_scenarios(directory)
    found = {scenario.get("scenario_id") for scenario in scenarios}
    missing = set(REQUIRED_RISKS) - found
    extra = found - set(REQUIRED_RISKS)
    if missing or extra or len(scenarios) != len(REQUIRED_RISKS):
        raise ReplayError(
            f"回放覆盖不完整: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    for scenario in scenarios:
        validate_scenario(scenario)
    return len(scenarios)
