# Knowledge Service

第 7 步已实现企业内部金融多模态知识写入链路：可信服务身份映射租户，
安全持久化原文件，异步解析、切片与 Embedding，把任务和来源写入 MySQL、
原文件写入 MinIO、关键词写入 OpenSearch、向量写入 Milvus，并通过
Transactional Outbox 向 Kafka 投递阶段事件。

## 核心文件

- `api.py`：内部 FastAPI 上传、状态查询和幂等重试接口。
- `pipeline.py`：入库状态机、敏感内容策略、双索引对账和版本发布门禁。
- `mysql_repository.py`：MySQL 真相源、事务状态迁移、Outbox/Inbox 和版本记录。
- `adapters.py`：MinIO、OpenSearch、Milvus 与 Kafka 适配器。
- `runtime.py`：由环境配置组装 Local/Test 真实运行组件。
- `event_payloads.py`：五类 Kafka 事件与统一 Envelope。
- `inmemory.py`：单元、契约和 API 测试使用的确定性内存实现。

## 运行

先按根目录 `requirements/README.md` 创建 `.venv` 并安装固定依赖，再启动
Local 基础设施：

```powershell
.\.venv\Scripts\python.exe tools/infra.py up --env local
.\.venv\Scripts\python.exe tools/knowledge.py migrate --env local
.\.venv\Scripts\python.exe tools/knowledge.py verify --env local
.\.venv\Scripts\python.exe tools/knowledge.py serve --env local
```

内部 API 默认监听 `127.0.0.1:8087`。Local 占位令牌只存在于可提交的
环境样例中，不能用于生产。独立投递某个租户的待发送事件：

```powershell
.\.venv\Scripts\python.exe tools/knowledge.py publish-outbox --env local --tenant tenant-local
```

当前只完成写入闭环，不包含第 8 步混合检索、重排、问答和质量评测。
Production Profile 也不会接受测试 OCR、Hash Embedding、测试扫描器、进程内
解析边界或静态身份映射，不能把 Local 验收结果当成正式服务器发布完成。
