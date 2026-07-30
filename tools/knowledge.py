#!/usr/bin/env python3
"""Operate and verify the step 7 local/test knowledge ingestion runtime."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = {
    "local": ROOT / "infra/environments/local.env.example",
    "test": ROOT / "infra/environments/test.env.example",
}


class KnowledgeToolError(RuntimeError):
    pass


def read_environment(name: str) -> dict[str, str]:
    values: dict[str, str] = {"AGENTFORGE_PROFILE": name}
    path = ENVIRONMENTS[name]
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise KnowledgeToolError(f"环境文件格式无效: {path}:{line_number}")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def run(arguments: list[str], *, environment: dict[str, str]) -> None:
    current = os.environ.copy()
    current.update(environment)
    result = subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        env=current,
        check=False,
    )
    if result.returncode != 0:
        raise KnowledgeToolError(
            f"命令失败 ({result.returncode}): {' '.join(arguments)}"
        )


def execute(command: str, environment_name: str, tenant: str | None) -> None:
    environment = read_environment(environment_name)
    if command == "migrate":
        run(["-m", "agentforge_knowledge", "migrate"], environment=environment)
        return
    if command == "serve":
        run(["-m", "agentforge_knowledge", "serve"], environment=environment)
        return
    if command == "publish-outbox":
        if tenant is None:
            raise KnowledgeToolError("publish-outbox 必须提供 --tenant")
        run(
            [
                "-m",
                "agentforge_knowledge",
                "publish-outbox",
                "--tenant",
                tenant,
            ],
            environment=environment,
        )
        return

    run(["-m", "agentforge_knowledge", "migrate"], environment=environment)
    environment["AGENTFORGE_RUN_KNOWLEDGE_INTEGRATION"] = "1"
    environment["AGENTFORGE_INTEGRATION_RUN_ID"] = uuid.uuid4().hex[:12]
    run(
        [
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests/integration/knowledge",
            "-p",
            "test_*.py",
            "-v",
        ],
        environment=environment,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AgentForge 第 7 步知识写入运行与联调入口"
    )
    parser.add_argument(
        "command",
        choices=("migrate", "serve", "publish-outbox", "verify"),
    )
    parser.add_argument("--env", choices=tuple(ENVIRONMENTS), default="local")
    parser.add_argument("--tenant")
    args = parser.parse_args()
    try:
        execute(args.command, args.env, args.tenant)
    except KnowledgeToolError as exc:
        print(f"知识写入工具失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
