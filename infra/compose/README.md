# Compose

`compose.yaml` 定义第 5 步 Local/Test 共用的数据基础设施模型。环境差异只通过 `infra/environments/*.env.example` 注入，避免维护两份逐渐漂移的 Compose。

不要直接执行裸 `docker compose up`。使用根目录统一入口：

```powershell
python tools/infra.py config --env local
python tools/infra.py up --env local
python tools/infra.py wait --env local
python tools/infra.py down --env local
```

普通 `down` 保留命名卷。清空数据必须使用专门的显式销毁命令并完成确认。
