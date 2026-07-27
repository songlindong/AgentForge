# language: zh-CN
@infrastructure @compose @p0
功能: 最小本地数据基础设施
  后续金融客服服务必须使用固定、隔离、可健康检查且可持久化的本地数据组件。

  背景:
    假如 Compose 文件为 infra/compose/compose.yaml
    并且 Local 环境文件为 infra/environments/local.env.example

  @configuration @security
  场景: 数据组件使用固定镜像和本机端口
    当系统解析 Local Compose 配置
    那么所有镜像必须使用明确版本且不得使用 latest
    并且所有宿主机数据端口必须绑定 127.0.0.1
    并且 etcd 不得发布宿主机端口

  @health
  场景: 必需组件全部达到健康状态
    假如 Docker daemon 正在运行
    当启动 Local Compose 并等待健康
    那么 MySQL、Redis、Kafka、MinIO、OpenSearch、etcd 和 Milvus 必须健康
    并且 MinIO 初始化任务必须成功退出

  @persistence
  场景: 普通重启不会丢失合成探针数据
    假如各数据组件已经写入合成持久化探针
    当重启对应容器并重新等待健康
    那么所有受验证的探针数据必须仍然存在
    并且验证后必须清理探针数据

  @environment @isolation
  场景: Local 和 Test 环境不会共享项目状态
    当分别解析 Local 和 Test Compose 配置
    那么两个环境必须使用不同的 Compose 项目名
    并且两个环境的宿主机端口不得冲突

  @boundary
  场景: 基础组件健康不代表业务模块已经实现
    假如所有本地基础组件均已健康
    当第 5 步门禁通过
    那么结果只能证明本地数据基础设施可用
    并且不得将 RAG、Gateway、Agent、Skill、Memory 或 Sandbox 标记为已实现

