#!/usr/bin/env python3
"""Docker Compose lifecycle and persistence verification for step 5."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "infra/compose/compose.yaml"
ENVIRONMENT_FILES = {
    "local": ROOT / "infra/environments/local.env.example",
    "test": ROOT / "infra/environments/test.env.example",
}
EXPECTED_IMAGES = {
    "mysql": "mysql:8.4.7",
    "redis": "redis:8.2.3-alpine",
    "kafka": "apache/kafka:4.1.1",
    "minio": "minio/minio:RELEASE.2025-09-07T16-13-09Z",
    "minio-init": "minio/mc:RELEASE.2025-08-13T08-35-41Z",
    "opensearch": "opensearchproject/opensearch:3.3.2",
    "etcd": "quay.io/coreos/etcd:v3.5.18",
    "milvus": "milvusdb/milvus:v2.6.6",
}
HEALTHY_SERVICES = (
    "mysql",
    "redis",
    "kafka",
    "minio",
    "opensearch",
    "etcd",
    "milvus",
)
PERSISTENT_SERVICES = HEALTHY_SERVICES
PERSISTENT_VOLUMES = {
    "mysql-data",
    "redis-data",
    "kafka-data",
    "minio-data",
    "opensearch-data",
    "etcd-data",
    "milvus-data",
}
PUBLISHED_PORT_VARIABLES = (
    "MYSQL_PORT",
    "REDIS_PORT",
    "KAFKA_PORT",
    "MINIO_API_PORT",
    "MINIO_CONSOLE_PORT",
    "OPENSEARCH_PORT",
    "MILVUS_PORT",
    "MILVUS_HEALTH_PORT",
)


class InfrastructureError(RuntimeError):
    """A local infrastructure failure with an actionable message."""


def docker_environment() -> dict[str, str]:
    environment = os.environ.copy()
    docker_config = ROOT / ".agentforge-cache" / "docker-config"
    docker_config.mkdir(parents=True, exist_ok=True)
    environment.setdefault("DOCKER_CONFIG", str(docker_config))
    return environment


def run(
    command: list[str],
    *,
    capture: bool = True,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=docker_environment(),
            check=False,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise InfrastructureError(f"缺少命令: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise InfrastructureError(f"命令超时: {' '.join(command[:3])}") from exc

    if check and result.returncode != 0:
        details = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part and part.strip()
        )
        suffix = f"\n{details}" if details else ""
        raise InfrastructureError(
            f"命令失败 ({result.returncode}): {' '.join(command[:4])}{suffix}"
        )
    return result


def read_environment(name: str) -> dict[str, str]:
    path = ENVIRONMENT_FILES[name]
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise InfrastructureError(f"环境文件格式无效: {path}:{line_number}")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def compose_base(name: str) -> list[str]:
    environment = read_environment(name)
    return [
        "docker",
        "compose",
        "--project-name",
        environment["COMPOSE_PROJECT_NAME"],
        "--env-file",
        str(ENVIRONMENT_FILES[name]),
        "--file",
        str(COMPOSE_FILE),
    ]


def compose(
    name: str,
    arguments: list[str],
    *,
    capture: bool = True,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    return run(
        [*compose_base(name), *arguments],
        capture=capture,
        check=check,
        timeout=timeout,
    )


def compose_model(name: str) -> dict[str, Any]:
    result = compose(name, ["config", "--format", "json"])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise InfrastructureError(f"{name} Compose JSON 无法解析") from exc


def published_ports(model: dict[str, Any]) -> set[int]:
    ports: set[int] = set()
    for service in model.get("services", {}).values():
        for port in service.get("ports", []):
            if port.get("host_ip") != "127.0.0.1":
                raise InfrastructureError(
                    f"发现非本机端口绑定: {service.get('image')} -> {port}"
                )
            ports.add(int(port["published"]))
    return ports


def validate_model(name: str, model: dict[str, Any]) -> None:
    environment = read_environment(name)
    if model.get("name") != environment["COMPOSE_PROJECT_NAME"]:
        raise InfrastructureError(f"{name} Compose 项目名不匹配")

    services = model.get("services", {})
    if set(services) != set(EXPECTED_IMAGES):
        raise InfrastructureError(
            f"{name} 服务集合不匹配: {sorted(services)}"
        )
    for service_name, expected_image in EXPECTED_IMAGES.items():
        service = services[service_name]
        image = service.get("image", "")
        if image != expected_image or image.endswith(":latest"):
            raise InfrastructureError(
                f"{service_name} 镜像不符合固定版本: {image}"
            )
        if service_name in HEALTHY_SERVICES and not service.get("healthcheck"):
            raise InfrastructureError(f"{service_name} 缺少健康检查")

    if services["etcd"].get("ports"):
        raise InfrastructureError("etcd 不得发布宿主机端口")
    published_ports(model)

    networks = model.get("networks", {})
    data_network = networks.get("agentforge-data", {})
    access_network = networks.get("agentforge-local-access", {})
    if set(networks) != {"agentforge-data", "agentforge-local-access"}:
        raise InfrastructureError("Compose 网络集合不符合数据面与本机访问面设计")
    if not data_network.get("internal") or access_network.get("internal"):
        raise InfrastructureError("数据网络必须 internal，本机访问网络不得 internal")

    for service_name, service in services.items():
        service_networks = set(service.get("networks", {}))
        if "agentforge-data" not in service_networks:
            raise InfrastructureError(f"{service_name} 未连接内部数据网络")
        if service.get("ports") and "agentforge-local-access" not in service_networks:
            raise InfrastructureError(f"{service_name} 发布端口但未连接本机访问网络")
    for internal_only in ("etcd", "minio-init"):
        if "agentforge-local-access" in services[internal_only].get("networks", {}):
            raise InfrastructureError(f"{internal_only} 不得连接本机访问网络")

    volumes = set(model.get("volumes", {}))
    if volumes != PERSISTENT_VOLUMES:
        raise InfrastructureError(f"持久卷集合不匹配: {sorted(volumes)}")


def validate_configurations(name: str | None = None) -> None:
    selected = (name,) if name else tuple(ENVIRONMENT_FILES)
    models: dict[str, dict[str, Any]] = {}
    for environment_name in selected:
        model = compose_model(environment_name)
        validate_model(environment_name, model)
        models[environment_name] = model
        print(
            f"[{environment_name}] Compose 配置通过: "
            f"{len(model['services'])} 个服务、{len(model['volumes'])} 个卷",
            flush=True,
        )

    if name is None:
        local = models["local"]
        test = models["test"]
        if local["name"] == test["name"]:
            raise InfrastructureError("Local/Test Compose 项目名不得相同")
        overlap = published_ports(local) & published_ports(test)
        if overlap:
            raise InfrastructureError(f"Local/Test 端口冲突: {sorted(overlap)}")
        print("[isolation] Local/Test 项目名和宿主机端口完全隔离", flush=True)


def ensure_daemon() -> None:
    if not shutil.which("docker"):
        raise InfrastructureError("未安装 Docker CLI")
    result = run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        check=False,
        timeout=20,
    )
    if result.returncode != 0:
        raise InfrastructureError("Docker daemon 未运行，请先启动 Docker Desktop/Engine")
    print(f"Docker daemon: {result.stdout.strip()}", flush=True)


def container_state(name: str, service: str) -> dict[str, Any] | None:
    identifier = compose(name, ["ps", "--all", "--quiet", service]).stdout.strip()
    if not identifier:
        return None
    result = run(["docker", "inspect", "--format", "{{json .State}}", identifier])
    return json.loads(result.stdout)


def state_summary(name: str) -> dict[str, str]:
    summary: dict[str, str] = {}
    for service in (*HEALTHY_SERVICES, "minio-init"):
        state = container_state(name, service)
        if state is None:
            summary[service] = "absent"
            continue
        health = state.get("Health", {}).get("Status")
        summary[service] = health or state.get("Status", "unknown")
    return summary


def print_failure_context(name: str) -> None:
    status = compose(name, ["ps", "--all"], check=False)
    logs = compose(name, ["logs", "--tail", "60"], check=False)
    print(status.stdout, file=sys.stderr)
    print(logs.stdout, file=sys.stderr)
    print(logs.stderr, file=sys.stderr)


def wait_for_health(name: str, timeout_seconds: int = 600) -> None:
    ensure_daemon()
    deadline = time.monotonic() + timeout_seconds
    previous: dict[str, str] | None = None
    while time.monotonic() < deadline:
        summary = state_summary(name)
        if summary != previous:
            print(
                "[health] " + ", ".join(f"{key}={value}" for key, value in summary.items()),
                flush=True,
            )
            previous = summary

        unhealthy = [
            service
            for service in HEALTHY_SERVICES
            if summary.get(service) in {"unhealthy", "exited", "dead"}
        ]
        init_failed = summary.get("minio-init") == "exited" and (
            container_state(name, "minio-init") or {}
        ).get("ExitCode") != 0
        if unhealthy or init_failed:
            print_failure_context(name)
            raise InfrastructureError(
                f"服务健康失败: {', '.join(unhealthy) or 'minio-init'}"
            )

        all_healthy = all(summary.get(service) == "healthy" for service in HEALTHY_SERVICES)
        init_state = container_state(name, "minio-init")
        init_complete = bool(
            init_state
            and init_state.get("Status") == "exited"
            and init_state.get("ExitCode") == 0
        )
        if all_healthy and init_complete:
            print("全部常驻服务健康，MinIO 初始化成功", flush=True)
            return
        time.sleep(5)

    print_failure_context(name)
    raise InfrastructureError(f"等待健康超时: {timeout_seconds}s")


def compose_exec(name: str, service: str, script: str) -> str:
    return compose(
        name,
        ["exec", "--no-TTY", service, "/bin/sh", "-ec", script],
    ).stdout.strip()


def compose_exec_args(name: str, service: str, arguments: list[str]) -> str:
    return compose(
        name,
        ["exec", "--no-TTY", service, *arguments],
    ).stdout.strip()


def minio_client(name: str, script: str) -> str:
    return compose(
        name,
        [
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "/bin/sh",
            "minio-init",
            "-ec",
            script,
        ],
    ).stdout.strip()


def http_request(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    expect_json: bool = False,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise InfrastructureError(f"HTTP 探针失败: {method} {url}: {exc}") from exc
    if expect_json:
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise InfrastructureError(f"HTTP 探针未返回 JSON: {url}") from exc
    return body


def verify_host_ports(environment: dict[str, str]) -> None:
    for variable in PUBLISHED_PORT_VARIABLES:
        port = int(environment[variable])
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=5):
                pass
        except OSError as exc:
            raise InfrastructureError(
                f"宿主机端口不可达: {variable}=127.0.0.1:{port}: {exc}"
            ) from exc
    print("全部宿主机调试端口可达", flush=True)


def smoke(name: str) -> None:
    wait_for_health(name)
    environment = read_environment(name)
    verify_host_ports(environment)
    compose_exec(
        name,
        "mysql",
        'MYSQL_PWD="$MYSQL_PASSWORD" mysql -u"$MYSQL_USER" -D"$MYSQL_DATABASE" -Nse "SELECT 1" | grep 1',
    )
    compose_exec(
        name,
        "redis",
        'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli ping | grep PONG',
    )
    compose_exec(
        name,
        "kafka",
        "/opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server 127.0.0.1:9092 >/dev/null",
    )
    compose_exec_args(name, "etcd", ["etcdctl", "endpoint", "health"])

    minio_client(
        name,
        'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && '
        'mc stat "local/$AGENTFORGE_BUCKET" >/dev/null && mc stat "local/$MILVUS_BUCKET" >/dev/null',
    )
    http_request(
        "GET",
        f"http://127.0.0.1:{environment['MINIO_API_PORT']}/minio/health/ready",
    )
    cluster = http_request(
        "GET",
        f"http://127.0.0.1:{environment['OPENSEARCH_PORT']}/_cluster/health",
        expect_json=True,
    )
    if cluster.get("status") not in {"yellow", "green"}:
        raise InfrastructureError(f"OpenSearch 状态无效: {cluster.get('status')}")
    http_request(
        "GET",
        f"http://127.0.0.1:{environment['MILVUS_HEALTH_PORT']}/healthz",
    )
    print("基础设施 Smoke 检查通过", flush=True)


def milvus_json(name: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    environment = read_environment(name)
    result = http_request(
        "POST",
        f"http://127.0.0.1:{environment['MILVUS_PORT']}{path}",
        payload,
        expect_json=True,
    )
    if result.get("code", 0) != 0:
        raise InfrastructureError(f"Milvus REST 探针失败: {result}")
    return result


def restart_verify(name: str) -> None:
    smoke(name)
    environment = read_environment(name)
    token = secrets.token_hex(8)
    kafka_topic = f"agentforge.infrastructure.probe.{int(time.time())}"
    minio_object = f"infrastructure-probe/{token}.txt"
    opensearch_index = f"agentforge-infrastructure-probe-{token}"
    etcd_key = f"/agentforge/infrastructure/probe/{token}"
    milvus_collection = f"agentforge_infra_probe_{token}"

    compose_exec(
        name,
        "mysql",
        'MYSQL_PWD="$MYSQL_PASSWORD" mysql -u"$MYSQL_USER" -D"$MYSQL_DATABASE" -e '
        '"CREATE TABLE IF NOT EXISTS agentforge_infrastructure_probe '
        '(probe_key VARCHAR(64) PRIMARY KEY, probe_value VARCHAR(64) NOT NULL); '
        f"REPLACE INTO agentforge_infrastructure_probe VALUES ('{token}', '{token}');\"",
    )
    compose_exec(
        name,
        "redis",
        f'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli SET "agentforge:infrastructure:probe:{token}" "{token}" >/dev/null',
    )
    compose_exec(
        name,
        "kafka",
        f'/opt/kafka/bin/kafka-topics.sh --bootstrap-server 127.0.0.1:9092 --create --if-not-exists --topic "{kafka_topic}" --partitions 1 --replication-factor 1 >/dev/null && '
        f'printf "%s\\n" "{token}" | /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server 127.0.0.1:9092 --topic "{kafka_topic}" >/dev/null',
    )
    minio_client(
        name,
        'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && '
        f'printf "%s" "{token}" | mc pipe "local/$AGENTFORGE_BUCKET/{minio_object}" >/dev/null',
    )
    http_request(
        "PUT",
        f"http://127.0.0.1:{environment['OPENSEARCH_PORT']}/{opensearch_index}/_doc/1?refresh=true",
        {"probe": token},
        expect_json=True,
    )
    compose_exec_args(name, "etcd", ["etcdctl", "put", etcd_key, token])
    milvus_json(
        name,
        "/v2/vectordb/collections/create",
        {
            "collectionName": milvus_collection,
            "dimension": 4,
            "metricType": "COSINE",
            "primaryFieldName": "id",
            "vectorFieldName": "vector",
            "idType": "Int64",
            "autoId": False,
            "enableDynamicField": True,
        },
    )
    milvus_json(
        name,
        "/v2/vectordb/entities/insert",
        {
            "collectionName": milvus_collection,
            "data": [{"id": 1, "vector": [0.1, 0.2, 0.3, 0.4], "probe": token}],
        },
    )

    print("已写入 7 类合成持久化探针，开始重启数据组件", flush=True)
    compose(name, ["restart", *PERSISTENT_SERVICES], capture=False, timeout=300)
    wait_for_health(name)

    try:
        mysql_value = compose_exec(
            name,
            "mysql",
            'MYSQL_PWD="$MYSQL_PASSWORD" mysql -u"$MYSQL_USER" -D"$MYSQL_DATABASE" -Nse '
            f'"SELECT probe_value FROM agentforge_infrastructure_probe WHERE probe_key=\'{token}\';"',
        )
        if token not in mysql_value:
            raise InfrastructureError("MySQL 持久化探针丢失")

        redis_value = compose_exec(
            name,
            "redis",
            f'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli GET "agentforge:infrastructure:probe:{token}"',
        )
        if token not in redis_value:
            raise InfrastructureError("Redis 持久化探针丢失")

        kafka_value = compose_exec(
            name,
            "kafka",
            f'/opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server 127.0.0.1:9092 --topic "{kafka_topic}" --from-beginning --max-messages 1 --timeout-ms 15000',
        )
        if token not in kafka_value:
            raise InfrastructureError("Kafka 持久化探针丢失")

        minio_value = minio_client(
            name,
            'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && '
            f'mc cat "local/$AGENTFORGE_BUCKET/{minio_object}"',
        )
        if token not in minio_value:
            raise InfrastructureError("MinIO 持久化探针丢失")

        opensearch = http_request(
            "GET",
            f"http://127.0.0.1:{environment['OPENSEARCH_PORT']}/{opensearch_index}/_doc/1",
            expect_json=True,
        )
        if opensearch.get("_source", {}).get("probe") != token:
            raise InfrastructureError("OpenSearch 持久化探针丢失")

        etcd_value = compose_exec_args(
            name, "etcd", ["etcdctl", "get", etcd_key, "--print-value-only"]
        )
        if token not in etcd_value:
            raise InfrastructureError("etcd 持久化探针丢失")

        milvus_result = milvus_json(
            name,
            "/v2/vectordb/entities/query",
            {
                "collectionName": milvus_collection,
                "filter": "id == 1",
                "outputFields": ["id", "probe"],
            },
        )
        if token not in json.dumps(milvus_result, ensure_ascii=False):
            raise InfrastructureError("Milvus 持久化探针丢失")

        print("MySQL、Redis、Kafka、MinIO、OpenSearch、etcd、Milvus 持久化验证通过", flush=True)
    finally:
        cleanup_commands = [
            lambda: compose_exec(
                name,
                "mysql",
                'MYSQL_PWD="$MYSQL_PASSWORD" mysql -u"$MYSQL_USER" -D"$MYSQL_DATABASE" -e '
                '"DROP TABLE IF EXISTS agentforge_infrastructure_probe;"',
            ),
            lambda: compose_exec(
                name,
                "redis",
                f'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli DEL "agentforge:infrastructure:probe:{token}" >/dev/null',
            ),
            lambda: compose_exec(
                name,
                "kafka",
                f'/opt/kafka/bin/kafka-topics.sh --bootstrap-server 127.0.0.1:9092 --delete --topic "{kafka_topic}" >/dev/null',
            ),
            lambda: minio_client(
                name,
                'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && '
                f'mc rm "local/$AGENTFORGE_BUCKET/{minio_object}" >/dev/null',
            ),
            lambda: http_request(
                "DELETE",
                f"http://127.0.0.1:{environment['OPENSEARCH_PORT']}/{opensearch_index}",
                expect_json=True,
            ),
            lambda: compose_exec_args(name, "etcd", ["etcdctl", "del", etcd_key]),
            lambda: milvus_json(
                name,
                "/v2/vectordb/collections/drop",
                {"collectionName": milvus_collection},
            ),
        ]
        for cleanup in cleanup_commands:
            try:
                cleanup()
            except Exception as exc:  # cleanup must not hide the original failure
                print(f"清理探针时出现非致命错误: {exc}", file=sys.stderr)


def destroy(name: str, confirmation: str | None) -> None:
    expected = f"destroy-agentforge-{name}-data"
    if confirmation != expected:
        raise InfrastructureError(f"销毁卷必须传入 --confirm {expected}")
    ensure_daemon()
    compose(name, ["down", "--volumes", "--remove-orphans"], capture=False)


def execute(command: str, name: str, confirmation: str | None) -> None:
    if command == "config":
        validate_configurations(name)
    elif command == "config-all":
        validate_configurations()
    elif command == "pull":
        ensure_daemon()
        compose(name, ["pull"], capture=False, timeout=1800)
    elif command == "up":
        validate_configurations(name)
        ensure_daemon()
        compose(name, ["up", "--detach", "--remove-orphans"], capture=False, timeout=1800)
        wait_for_health(name)
    elif command == "wait":
        wait_for_health(name)
    elif command == "status":
        ensure_daemon()
        compose(name, ["ps", "--all"], capture=False)
    elif command == "smoke":
        smoke(name)
    elif command == "restart-verify":
        restart_verify(name)
    elif command == "down":
        ensure_daemon()
        compose(name, ["down", "--remove-orphans"], capture=False)
    elif command == "destroy":
        destroy(name, confirmation)
    else:
        raise InfrastructureError(f"未知命令: {command}")


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentForge 本地基础设施控制器")
    parser.add_argument(
        "command",
        choices=(
            "config",
            "config-all",
            "pull",
            "up",
            "wait",
            "status",
            "smoke",
            "restart-verify",
            "down",
            "destroy",
        ),
    )
    parser.add_argument("--env", choices=tuple(ENVIRONMENT_FILES), default="local")
    parser.add_argument("--confirm")
    args = parser.parse_args()
    try:
        execute(args.command, args.env, args.confirm)
    except InfrastructureError as exc:
        print(f"基础设施命令失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
