# Python 依赖管理

AgentForge 使用服务级 pyproject.toml 声明直接依赖，使用
requirements/step7.lock.txt 固定第 7 步验收环境解析出的完整依赖版本，
并将运行环境隔离在仓库内已忽略的 .venv。

Windows 初始化命令：

```powershell
python -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements\\step7.lock.txt
.\\.venv\\Scripts\\python.exe -m pip install --no-build-isolation --no-deps -e services\\document-processor
.\\.venv\\Scripts\\python.exe -m pip install --no-build-isolation --no-deps -e services\\knowledge-service
```

声明版本、锁定版本与实际安装版本必须一致。查看 pypdf：

```powershell
Get-Content services\\document-processor\\pyproject.toml
Select-String -Path requirements\\step7.lock.txt -Pattern "^pypdf=="
.\\.venv\\Scripts\\python.exe -m pip show pypdf
```

锁文件不包含 AgentForge 两个本地可编辑包；它们通过最后两条命令安装。
