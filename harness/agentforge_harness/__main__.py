"""AgentForge Harness 统一命令入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import serve
from .fake_llm import make_server as make_fake_llm_server
from .generators import gateway_records, vector_records, write_jsonl
from .mock_mcp import make_server as make_mock_mcp_server
from .replay import ReplayError, replay_all
from .verify import VerifyError, verify_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentForge 金融客服离线 Harness")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("verify", help="校验场景、Fixture 哈希和回放")

    for name, default_port in (
        ("serve-fake-llm", 18081),
        ("serve-mock-mcp", 18082),
    ):
        command = commands.add_parser(name)
        command.add_argument("--host", default="127.0.0.1")
        command.add_argument("--port", type=int, default=default_port)

    replay = commands.add_parser("replay", help="验证黄金事件回放")
    replay.add_argument("--all", action="store_true", required=True)

    gateway = commands.add_parser("generate-gateway")
    gateway.add_argument("--count", type=int, default=10)
    gateway.add_argument("--seed", type=int, default=20260728)
    gateway.add_argument("--tenant-count", type=int, default=2)
    gateway.add_argument("--output", type=Path)

    vectors = commands.add_parser("generate-vectors")
    vectors.add_argument("--count", type=int, default=100)
    vectors.add_argument("--dimension", type=int, default=16)
    vectors.add_argument("--seed", type=int, default=20260728)
    vectors.add_argument("--tenant-count", type=int, default=2)
    vectors.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "verify":
            print(json.dumps(verify_all(), ensure_ascii=False, sort_keys=True))
        elif args.command == "serve-fake-llm":
            serve(make_fake_llm_server(args.host, args.port), "Fake LLM")
        elif args.command == "serve-mock-mcp":
            serve(make_mock_mcp_server(args.host, args.port), "Mock MCP")
        elif args.command == "replay":
            print(f"回放验证通过: {replay_all()} 个风险场景")
        elif args.command == "generate-gateway":
            count = write_jsonl(
                gateway_records(args.count, args.seed, args.tenant_count), args.output
            )
            if args.output:
                print(f"已生成 {count} 条 Gateway 请求: {args.output}")
        elif args.command == "generate-vectors":
            count = write_jsonl(
                vector_records(
                    args.count, args.dimension, args.seed, args.tenant_count
                ),
                args.output,
            )
            if args.output:
                print(f"已生成 {count} 条向量: {args.output}")
        return 0
    except (OSError, ValueError, VerifyError, ReplayError) as exc:
        print(f"Harness 失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
