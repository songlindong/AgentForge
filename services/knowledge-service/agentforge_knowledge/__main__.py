from __future__ import annotations

import argparse
import os

from .adapters import KafkaEventPublisher
from .errors import KnowledgeError
from .pipeline import OutboxPublisher
from .runtime import (
    RuntimeSettings,
    apply_migration,
    build_repository,
    build_runtime,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AgentForge 金融多模态知识写入服务"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("migrate", help="应用第 7 步 MySQL 幂等迁移")
    serve = subparsers.add_parser("serve", help="启动内部知识写入 API")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    publish = subparsers.add_parser(
        "publish-outbox", help="投递指定租户的待发送事件"
    )
    publish.add_argument("--tenant", required=True)
    publish.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    try:
        settings = RuntimeSettings.from_mapping(os.environ)
        if args.command == "migrate":
            apply_migration(settings)
            print("MySQL 第 7 步迁移已应用")
            return 0
        if args.command == "publish-outbox":
            repository = build_repository(settings)
            publisher = OutboxPublisher(
                repository=repository,
                publisher=KafkaEventPublisher(
                    bootstrap_servers=list(settings.kafka_bootstrap_servers)
                ),
            )
            count = publisher.publish_pending(args.tenant, limit=args.limit)
            print(f"Outbox 已投递: {count}")
            return 0

        import uvicorn

        runtime = build_runtime(settings)
        uvicorn.run(
            runtime.app(),
            host=args.host or settings.api_host,
            port=args.port or settings.api_port,
            access_log=False,
        )
        return 0
    except KnowledgeError as exc:
        print(f"启动失败 [{exc.code}]: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
