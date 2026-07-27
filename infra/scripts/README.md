# Infrastructure Scripts

- `local.ps1`：Windows 包装入口。
- `local.sh`：Linux/macOS 包装入口。

两个脚本只转发到 `tools/infra.py`，不维护重复逻辑。生产部署、迁移、备份、恢复和回滚脚本仍在后续步骤实现。
