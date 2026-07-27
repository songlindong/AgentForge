# language: zh-CN
@foundation @contract @p0
功能: 仓库骨架与最小工程门禁
  仓库必须为后续服务实现提供明确边界，并使用同一入口执行离线门禁。

  背景:
    假如当前工作目录是 AgentForge 仓库根目录
    并且统一门禁入口为 tools/check.py

  @structure
  场景: 必需工程边界完整
    当执行 structure 门禁
    那么 services、web、harness、tests、infra 和 reports 目录必须存在
    并且 Go、Python 和 Web 工作区元数据必须存在

  @specification
  场景: 规格基础错误会阻止门禁
    假如一个契约包含无效 JSON 或不可解析的本地引用
    当执行 specs 门禁
    那么命令必须返回非零退出码
    并且错误信息必须指出失败文件和原因

  @offline
  场景: 最小门禁不依赖外部服务
    当执行 ci 门禁
    那么检查过程不得要求模型服务、金融接口或基础设施处于运行状态
    并且检查过程不得下载第三方依赖

  @boundary
  场景: 空目录不能被解释为业务能力完成
    假如服务和 Harness 目录当前只声明职责边界
    当工程门禁全部通过
    那么结果只能证明仓库骨架和规格基础有效
    并且不得将任何核心业务模块标记为已实现

