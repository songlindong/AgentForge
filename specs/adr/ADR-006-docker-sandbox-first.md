# ADR-006：Docker 沙箱优先

状态：Accepted
日期：2026-07-26

## 背景

OCR、文档解析、规则脚本和高风险本地任务都可能处理不可信输入，需要隔离文件、网络、进程和资源。

## 决策

第一版使用 Docker 临时容器和 Go Sandbox Controller，默认：

- non-root
- 只读根文件系统
- 无网络
- CPU/内存/PID/时长限制
- 镜像白名单
- 不挂载敏感宿主机目录
- 禁止 Docker Socket
- 任务结束销毁容器、进程和临时数据

后续根据安全和容量报告评估 Kubernetes Job、seccomp、AppArmor/SELinux 或 gVisor。

## 后果

沙箱必须拥有独立攻击测试、资源监控、审计和清理验证。不能把普通进程或容器启动误认为已经完成安全隔离。
