# 第 4 步：仓库骨架与最小工程门禁规格

状态：第 4 步实现基线，等待确认  
版本：0.1.0  
更新日期：2026-07-27

## 1. 目标

本步建立一个能被本地开发和 CI 共同验证的单仓库骨架，使后续 Go、Python、Web、Harness、基础设施和测试工作都进入明确边界，并且所有规格变更在进入业务实现前先通过自动检查。

本步完成后应满足：

- 仓库目录职责明确，后续模块不会随意落在根目录。
- Go、Python、Node.js 和 pnpm 版本边界明确。
- 本地与 CI 使用同一个检查入口。
- OpenAPI、JSON Schema、AsyncAPI 和 Gherkin 规格能够离线完成基础校验。
- 当前空工程能够执行格式、静态、规格和测试门禁。
- 生成物、密钥、本地数据和报告不会污染版本库。

## 2. 非目标

本步不做以下工作：

- 不实现 Channel Gateway、LLM Gateway、Agent Runtime、Skill Registry、Memory、Knowledge、MCP 或 Sandbox 业务。
- 不创建数据库表、HTTP Handler、Agent、Skill、Prompt 或模型调用。
- 不启动 MySQL、Redis、Kafka、Milvus、OpenSearch、MinIO 或 Docker Compose。
- 不安装 Next.js、FastAPI、Hertz、Eino、OCR、向量模型或其他业务依赖。
- 不接入外部模型、金融接口或真实业务数据。
- 不把目录占位或通过空测试解释为业务能力已经完成。

## 3. 使用场景

### 3.1 开发者提交规格

开发者修改 OpenAPI、JSON Schema、AsyncAPI 或 Gherkin 后，运行统一门禁。系统必须检查 JSON 语法、本地 `$ref`、顶层规范版本和 Feature 基本结构，失败时返回非零退出码。

### 3.2 开发者增加模块

开发者把实现放入已经声明的服务、Web 或 Harness 边界中，通过对应语言的格式、静态和测试入口验证，不在根目录堆放临时代码。

### 3.3 CI 验证变更

代码推送或 Pull Request 触发 CI。CI 使用与本地相同的 `python tools/check.py ci`，任何一个阶段失败都会阻止门禁通过。

## 4. 仓库边界

```text
contracts/   OpenAPI、JSON Schema、AsyncAPI 契约
docs/        项目上下文、路线和进度
specs/       产品、架构、ADR、模块验收和工程规格
services/    Go/Python 服务边界
web/         H5 与运营端 Web 工作区边界
harness/     Fake、Mock、Fixture 和场景回放边界
tests/       单元、契约、集成、端到端、安全和性能测试边界
infra/       Compose、环境配置、观测和运维脚本边界
reports/     本地生成的验证证据目录
tools/       不含业务逻辑的仓库门禁工具
```

服务目录只声明架构中已经确认的容器边界。一个目录存在不表示对应服务已经实现或具备上线能力。

## 5. 统一命令契约

统一入口为：

```text
python tools/check.py <command>
```

| command | 输入 | 成功输出 | 失败语义 |
|---|---|---|---|
| `structure` | 仓库目录和关键配置 | 结构检查通过 | 缺少路径时退出码非零 |
| `specs` | `contracts/`、`specs/**/*.feature` | 规格检查通过 | JSON、`$ref`、规范顶层或 Gherkin 结构错误时失败 |
| `format` | 受版本控制的文本和 Go 文件 | 格式检查通过 | 编码、文件结尾、`gofmt` 或 Git 空白错误时失败 |
| `static` | Go、Python、Node/TOML 配置 | 静态检查通过 | 语法、元数据或 `go vet` 失败时失败 |
| `test` | 当前已有的工程门禁测试 | 测试检查通过 | 任一测试进程失败时失败 |
| `ci` | 上述全部输入 | 所有门禁通过 | 任一阶段失败立即返回非零退出码 |

PowerShell 和 Bash 包装脚本只能转发到该入口，不得拥有另一套校验逻辑。

## 6. 执行流程与状态

```text
requested
→ structure
→ specs
→ format
→ static
→ test
→ passed
```

任一阶段失败后进入 `failed`，打印阶段和根因，并返回非零退出码。门禁不自动修改规格或扩大容差。

## 7. Agent、Skill 与 Harness 边界

- `services/agent-runtime/` 和 `services/skill-registry/` 只预留未来实现位置。
- `harness/` 只预留 Fake LLM、Mock MCP、固定 Fixture 和回放边界。
- 本步不注册 Agent 或 Skill，不执行编排，不调用 MCP，也不运行不可信任务。
- 后续 Agent、Skill 和 Sandbox 实现必须继续遵守既有 Manifest、权限、预算、租户与隔离契约。
- 当前门禁只证明仓库结构和规格基础正确，不能替代第 6 步之后的行为 Harness。

## 8. 安全不变量

- 检查过程不需要外部网络、付费 API、生产凭证或真实金融数据。
- `.env`、密钥、证书、私钥、本地数据、缓存和生成报告默认忽略。
- 规格引用只能解析仓库内受控文件，不能通过远程 `$ref` 绕过审查。
- 门禁工具只读取仓库并运行本地编译/测试命令，不启动基础设施或执行业务副作用。
- 仓库继续执行既定渠道和背景表述约束。

## 9. 可度量指标

| 指标 | 第 4 步目标 |
|---|---|
| 本地门禁外部网络依赖 | 0 |
| 本地门禁付费服务依赖 | 0 |
| 无效 JSON 或不可解析本地 `$ref` 漏过数量 | 0 |
| 必需工程边界缺失但门禁通过数量 | 0 |
| 空工程 CI 目标时长 | 不超过 2 分钟，不含托管 Runner 排队时间 |
| 当前业务服务、基础设施启动数量 | 0 |

## 10. 依赖与取舍

本步不增加第三方运行时依赖。规格校验使用 Python 标准库实现基础门禁，优点是离线、跨平台、立即可执行；代价是它不能替代完整的 OpenAPI、AsyncAPI 和 JSON Schema 语义校验器。后续需要引入正式 Linter 时，必须固定版本并保留统一命令入口。

未采用 `make` 作为唯一入口，因为当前 Windows 环境没有该工具；未采用需要下载插件的任务运行器，因为本步门禁必须在受限网络下复现。

## 11. 验收场景

可执行规格见：

```text
specs/engineering/repository-foundation.feature
```

第 4 步完成时必须实际运行：

```text
python tools/check.py ci
git diff --check
```

