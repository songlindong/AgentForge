# language: zh-CN
@contract @knowledge @multimodal @p0
功能: 多模态 Knowledge Base 与引用契约
  金融知识必须版本化、进行租户隔离，并且能够追溯到原始文档区域。

  背景:
    假如受控文件 Schema 为 contracts/json-schema/file-object.schema.json
    并且 Knowledge 事件 Payload 定义在 contracts/json-schema/knowledge-event.schema.json
    并且 Kafka 事件定义在 contracts/asyncapi/kafka.asyncapi.json

  @security
  场景: 不安全文件不能进入解析流水线
    假如上传文件声明的媒体类型为 application/pdf
    当文件魔数不匹配或解压比例超过限制
    那么对象状态应为 rejected
    并且不得发布 document.uploaded 事件
    并且 OCR 或模型服务不得收到该文件

  @traceability
  场景: 文档每个处理阶段都保留来源和版本标识
    假如租户 "tenant_demo" 的文档 "doc-001" 版本 3 已通过安全检查
    当系统发布 uploaded、parsed、chunked 和 embedding 事件
    那么每个事件必须包含 tenant_id、document_id、document_version、job_id、attempt、trace_id 和 source_object_key
    并且同一幂等键的重试不得创建第二份向量或 BM25 版本

  @citation
  场景: 回答引用能够定位到原始页码或区域
    假如检索到的 Chunk 包含 document_id "doc-001" 和 page_number 4
    并且该 Chunk 包含规范化 bounding_box 和原文件对象引用
    当回答中包含 Citation Part
    那么 Citation 必须包含文档版本和可解析的页码或区域引用
    并且 Citation 的租户必须与通过认证的查询租户一致

  @versioning
  场景: 两类索引一致后才能发布 Knowledge Version
    假如文档版本 3 的 BM25 和 Milvus 写入尚未全部完成
    当系统收到发布请求
    那么不得发布 knowledge.version.published 事件
    当两类索引版本都通过一致性检查
    那么发布事件必须记录 BM25、向量索引和 Knowledge Version

