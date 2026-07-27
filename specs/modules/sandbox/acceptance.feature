# language: zh-CN
@contract @sandbox @security
功能: 安全沙箱任务契约
  不可信文档解析和高风险计算必须运行在临时受限环境中。

  背景:
    假如沙箱契约为 contracts/json-schema/sandbox-task.schema.json

  @isolation
  场景: 沙箱任务必须具备基础隔离不变量
    假如为租户 "tenant_demo" 创建一个沙箱任务
    当系统校验任务请求
    那么 run_as_user 必须为非 root 用户
    并且 read_only_rootfs 必须为 true
    并且 docker_socket_mounted 必须为 false
    并且 cleanup_policy 必须为 destroy_task_and_temporary_data

  @network
  场景: 默认禁止网络访问
    假如一个文档解析任务没有获得网络例外授权
    当该任务启动
    那么 network mode 必须为 deny
    并且任务不能访问任意外部地址

  @resources
  场景: 资源耗尽和超时受到限制
    假如一个任务超过 CPU、内存、PID、磁盘或超时限制
    当 Sandbox Controller 执行资源限制
    那么任务必须在 kill grace period 内被终止
    并且结果必须记录资源使用量和 cleanup_verified
    并且任务结束后不得残留进程或临时输出

