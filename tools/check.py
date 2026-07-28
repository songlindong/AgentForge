#!/usr/bin/env python3
"""Offline repository quality gate for the AgentForge foundation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
from typing import Any, Iterable
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".feature",
    ".go",
    ".json",
    ".md",
    ".mjs",
    ".mod",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".tsx",
    ".ts",
    ".work",
    ".yaml",
    ".yml",
}
REQUIRED_DIRECTORIES = (
    "contracts",
    "docs",
    "specs",
    "services",
    "web",
    "harness",
    "tests",
    "infra",
    "reports",
    "tools",
)
REQUIRED_FILES = (
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    ".go-version",
    ".python-version",
    ".nvmrc",
    "go.work",
    "pyproject.toml",
    "services/go.mod",
    "services/knowledge-service/pyproject.toml",
    "services/document-processor/pyproject.toml",
    "harness/pyproject.toml",
    "infra/compose/compose.yaml",
    "infra/environments/local.env.example",
    "infra/environments/test.env.example",
    "tools/infra.py",
    "web/package.json",
    "web/pnpm-workspace.yaml",
)
BANNED_EXPRESSIONS = tuple(
    value.encode("ascii").decode("unicode_escape")
    for value in (
        r"\u5b66\u4e60",
        r"\u7b80\u5386",
        r"\u9762\u8bd5",
        r"\u7ecf\u5386",
        r"\u6f14\u793a",
        r"\u5fae\u4fe1",
    )
)


class GateError(RuntimeError):
    """A user-actionable quality-gate failure."""


def run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    capture: bool = True,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process_environment = os.environ.copy()
    if environment:
        process_environment.update(environment)
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=process_environment,
        )
    except FileNotFoundError as exc:
        raise GateError(f"缺少命令: {command[0]}") from exc

    if result.returncode != 0:
        details = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        suffix = f"\n{details}" if details else ""
        raise GateError(f"命令失败 ({result.returncode}): {' '.join(command)}{suffix}")
    return result


def repository_files() -> list[Path]:
    result = run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    )
    return sorted(
        (ROOT / item).resolve()
        for item in result.stdout.split("\0")
        if item and (ROOT / item).is_file()
    )


def ensure_within_repository(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise GateError(f"引用越出仓库边界: {path}") from exc
    return resolved


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"JSON 无法解析: {path.relative_to(ROOT)}: {exc}") from exc


def resolve_pointer(document: Any, pointer: str, source: Path) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise GateError(f"JSON Pointer 格式无效: {source.relative_to(ROOT)}#{pointer}")

    current = document
    for raw_token in pointer[1:].split("/"):
        token = unquote(raw_token).replace("~1", "/").replace("~0", "~")
        try:
            if isinstance(current, list):
                current = current[int(token)]
            else:
                current = current[token]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise GateError(
                f"JSON Pointer 不存在: {source.relative_to(ROOT)}#{pointer}"
            ) from exc
    return current


def iter_references(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        reference = value.get("$ref")
        if isinstance(reference, str):
            yield reference
        for child in value.values():
            yield from iter_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_references(child)


def validate_references(path: Path, document: Any, cache: dict[Path, Any]) -> None:
    for reference in iter_references(document):
        parsed = urlparse(reference)
        if parsed.scheme or parsed.netloc:
            raise GateError(
                f"不允许远程 $ref: {path.relative_to(ROOT)} -> {reference}"
            )

        target_path = path if parsed.path == "" else path.parent / unquote(parsed.path)
        target_path = ensure_within_repository(target_path)
        if not target_path.is_file():
            raise GateError(
                f"$ref 文件不存在: {path.relative_to(ROOT)} -> {reference}"
            )
        target_document = cache.setdefault(target_path, load_json(target_path))
        resolve_pointer(target_document, parsed.fragment, target_path)


def check_structure() -> None:
    missing = [name for name in REQUIRED_DIRECTORIES if not (ROOT / name).is_dir()]
    missing.extend(name for name in REQUIRED_FILES if not (ROOT / name).is_file())
    if missing:
        raise GateError("缺少工程边界:\n- " + "\n- ".join(missing))

    web_manifest = load_json(ROOT / "web/package.json")
    if web_manifest.get("private") is not True:
        raise GateError("web/package.json 必须声明 private=true")
    if web_manifest.get("dependencies") or web_manifest.get("devDependencies"):
        raise GateError("第 4 步 Web 空工程不得引入业务依赖")

    python_projects = (
        ROOT / "pyproject.toml",
        ROOT / "services/knowledge-service/pyproject.toml",
        ROOT / "services/document-processor/pyproject.toml",
        ROOT / "harness/pyproject.toml",
    )
    for project_path in python_projects:
        with project_path.open("rb") as stream:
            python_project = tomllib.load(stream)
        if python_project.get("project", {}).get("dependencies") != []:
            raise GateError(
                f"第 4 步 Python 空工程不得引入业务依赖: "
                f"{project_path.relative_to(ROOT)}"
            )

    print("[structure] 仓库目录、版本和空工程边界检查通过")


def check_specs() -> None:
    json_files = sorted((ROOT / "contracts").rglob("*.json"))
    if not json_files:
        raise GateError("contracts/ 中没有 JSON 契约")

    cache: dict[Path, Any] = {}
    for path in json_files:
        document = cache.setdefault(path.resolve(), load_json(path))
        validate_references(path.resolve(), document, cache)

        if path.name.endswith(".openapi.json"):
            if document.get("openapi") != "3.1.0" or not document.get("paths"):
                raise GateError(f"OpenAPI 顶层无效: {path.relative_to(ROOT)}")
        elif path.name.endswith(".asyncapi.json"):
            if document.get("asyncapi") != "2.6.0" or not document.get("channels"):
                raise GateError(f"AsyncAPI 顶层无效: {path.relative_to(ROOT)}")
        elif path.name.endswith(".schema.json"):
            schema_uri = document.get("$schema", "")
            if "json-schema.org/draft/2020-12/schema" not in schema_uri:
                raise GateError(f"JSON Schema Draft 无效: {path.relative_to(ROOT)}")

    features = sorted((ROOT / "specs").rglob("*.feature"))
    if not features:
        raise GateError("specs/ 中没有 Gherkin Feature")
    required_keywords = ("功能:", "场景", "假如", "当", "那么")
    scenario_count = 0
    for path in features:
        content = path.read_text(encoding="utf-8")
        if not content.startswith("# language: zh-CN"):
            raise GateError(f"Feature 未声明简体中文: {path.relative_to(ROOT)}")
        missing = [keyword for keyword in required_keywords if keyword not in content]
        if missing:
            raise GateError(
                f"Feature 结构不完整: {path.relative_to(ROOT)}: {', '.join(missing)}"
            )
        scenario_count += sum(
            line.lstrip().startswith(("场景:", "场景大纲:"))
            for line in content.splitlines()
        )

    for path in repository_files():
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        content = path.read_text(encoding="utf-8")
        for expression in BANNED_EXPRESSIONS:
            if expression in content:
                raise GateError(
                    f"发现仓库禁用表述: {path.relative_to(ROOT)}"
                )

    print(
        f"[specs] {len(json_files)} 个 JSON 契约、{len(features)} 个 Feature、"
        f"{scenario_count} 个场景检查通过"
    )


def check_format() -> None:
    failures: list[str] = []
    for path in repository_files():
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
            ".editorconfig",
            ".gitattributes",
            ".gitignore",
            ".nvmrc",
        }:
            continue
        try:
            data = path.read_bytes()
            data.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            failures.append(f"{path.relative_to(ROOT)}: 不是有效 UTF-8 ({exc})")
            continue
        if data and not data.endswith(b"\n"):
            failures.append(f"{path.relative_to(ROOT)}: 文件末尾缺少换行")
        if path.suffix.lower() != ".md":
            for line_number, line in enumerate(data.splitlines(), start=1):
                if line.endswith((b" ", b"\t")):
                    failures.append(
                        f"{path.relative_to(ROOT)}:{line_number}: 行尾存在空白"
                    )

    go_files = [str(path) for path in (ROOT / "services").rglob("*.go")]
    if go_files:
        result = run(["gofmt", "-l", *go_files])
        failures.extend(
            f"{Path(line).relative_to(ROOT)}: 未通过 gofmt"
            for line in result.stdout.splitlines()
            if line.strip()
        )
    if failures:
        raise GateError("格式检查失败:\n- " + "\n- ".join(failures))
    print("[format] UTF-8、文件结尾和 Go 格式检查通过")


def node_command() -> str:
    configured = os.environ.get("AGENTFORGE_NODE")
    if configured:
        return configured
    executable = shutil.which("node")
    if not executable:
        raise GateError("缺少 Node.js；可通过 AGENTFORGE_NODE 指定可执行文件")
    return executable


def go_environment() -> dict[str, str]:
    cache = ROOT / ".agentforge-cache" / "go-build"
    cache.mkdir(parents=True, exist_ok=True)
    return {"GOCACHE": str(cache)}


def expected_version(filename: str) -> str:
    return (ROOT / filename).read_text(encoding="utf-8").strip()


def check_runtime_versions() -> None:
    expected_python = expected_version(".python-version")
    current_python = ".".join(str(value) for value in sys.version_info[:3])
    if current_python != expected_python:
        raise GateError(
            f"Python 版本不匹配: 需要 {expected_python}，当前 {current_python}"
        )

    expected_go = expected_version(".go-version")
    go_version = run(["go", "version"]).stdout.split()
    current_go = go_version[2].removeprefix("go") if len(go_version) >= 3 else "unknown"
    if current_go != expected_go:
        raise GateError(f"Go 版本不匹配: 需要 {expected_go}，当前 {current_go}")


def check_static() -> None:
    check_runtime_versions()
    python_files = [
        "tools/check.py",
        "tools/infra.py",
        *(
            str(path.relative_to(ROOT))
            for path in sorted((ROOT / "harness").rglob("*.py"))
        ),
    ]
    run([sys.executable, "-m", "py_compile", *python_files])
    run(
        ["go", "vet", "./..."],
        cwd=ROOT / "services",
        environment=go_environment(),
    )
    run([node_command(), "web/scripts/check-foundation.mjs"])
    print("[static] Python 语法、go vet 和 Web 元数据检查通过")


def check_infrastructure() -> None:
    run([sys.executable, "tools/infra.py", "config-all"])
    print("[infrastructure] Local/Test Compose 配置检查通过")


def check_harness() -> None:
    run([sys.executable, "-m", "harness.agentforge_harness", "verify"])
    run(
        [
            sys.executable,
            "-m",
            "harness.agentforge_harness",
            "replay",
            "--all",
        ]
    )
    print("[harness] Fake、Mock、Fixture 与 9 个风险回放检查通过")


def check_tests() -> None:
    run(
        ["go", "test", "./..."],
        cwd=ROOT / "services",
        environment=go_environment(),
    )
    run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "harness/tests",
            "-p",
            "test_*.py",
        ]
    )
    run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tools/tests",
            "-p",
            "test_*.py",
        ]
    )
    run([node_command(), "--test", "web/tests/foundation.test.mjs"])
    print("[test] Go、门禁工具、Harness 和 Web 基础测试通过")


CHECKS = {
    "structure": check_structure,
    "specs": check_specs,
    "format": check_format,
    "infrastructure": check_infrastructure,
    "static": check_static,
    "harness": check_harness,
    "test": check_tests,
}


def execute(command: str) -> None:
    selected = list(CHECKS) if command == "ci" else [command]
    for name in selected:
        print(f"==> {name}")
        CHECKS[name]()
    print(f"门禁完成: {command}")


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentForge 离线工程门禁")
    parser.add_argument("command", choices=[*CHECKS, "ci"])
    args = parser.parse_args()
    try:
        execute(args.command)
    except GateError as exc:
        print(f"门禁失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
