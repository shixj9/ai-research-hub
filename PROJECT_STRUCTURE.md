# 项目目录与模块协作说明

本文描述当前后端基线的目录职责、请求流向和开发时各模块的搭配方式。

## 根目录

```text
ai-research-hub/
├── backend/                 FastAPI 后端代码、测试和数据库迁移
├── frontend/                React + Vite 前端页面
├── docs/                    架构、决策和 AI 协作记录
├── scripts/                 本地启动与辅助脚本
├── storage/                 运行时文件，后续保存本地 PDF，不进入 Git
├── alembic.ini              Alembic 入口配置
├── compose.yaml             PostgreSQL/pgvector 本地容器
├── pyproject.toml           Python 依赖与工具配置
├── uv.lock                  Python 依赖锁文件
├── .env.example             环境变量示例，不包含真实密码
└── README.md                项目启动和验证说明
```

## `docs/`

- `AI_COLLABORATION.md`：Codex、Antigravity 与用户共享的项目状态、决策边界、任务交接和学习复述检查表。每位参与者开始新模块前应先阅读，并在完成规划、实现或审查后追加通信记录。

## `frontend/`

轻量的 React + TypeScript 单页前端。

- `src/App.tsx`：上传、文档列表、详情和删除等页面交互。
- `src/api.ts`：统一封装对 FastAPI 的请求和 PDF 文件地址。
- `src/types.ts`：与后端响应对应的 TypeScript 数据类型。
- `src/styles.css`：响应式页面样式，不依赖额外 UI 框架。
- `.env.example`：前端 API 地址示例。

浏览器从前端调用 FastAPI；FastAPI 再协调 PostgreSQL 和本地文件存储。前端不直接访问数据库或 `storage/`。

## `backend/app/`

### `api/`

HTTP 接口层。负责接收请求、解析路径和查询参数、选择返回状态码，并调用下层模块。

- `api/router.py`：汇总所有业务路由，统一挂载到 `/api/v1`。
- `api/routes/health.py`：进程健康和数据库就绪检查。
- `api/routes/documents.py`：文档 CRUD、上传和原始 PDF 读取接口。

接口层不直接拼 SQL，也不保存文件。

### `schemas/`

Pydantic 输入输出模型。负责校验 JSON 数据并定义 OpenAPI/Swagger 中展示的数据结构。

- `schemas/document.py`：文档创建、更新、响应和列表结构。
- `schemas/system.py`：首页、健康检查和就绪检查响应。

Schema 不是数据库表；它定义 API 允许客户端看到或提交的字段。

### `models/`

SQLAlchemy 数据模型，对应真实数据库表。

- `models/document.py`：对应 PostgreSQL 的 `documents` 表。

Model 可以包含数据库约束、字段类型、索引和默认值。客户端不能直接控制 Model。

### `repositories/`

数据库访问层。集中保存查询、插入、更新和软删除操作。

- `repositories/document.py`：`documents` 表的数据操作。

接口层通过 Repository 操作数据库，避免 SQL 查询散落在路由文件里。加入文件上传、解析任务等业务规则后，可以在 API 和 Repository 之间增加 `services/` 层。

### `services/`

跨越多个基础设施的业务工作流。

- `services/document_upload.py`：流式接收 PDF、限制大小、验证格式、计算 SHA-256、提取页数、移动文件并创建数据库记录。

上传服务同时协调文件系统、PDF 解析器和 Repository，因此不能放进单纯的 API 或数据库访问层。

### `db/`

数据库基础设施。

- `db/base.py`：所有 SQLAlchemy Model 的共同基类。
- `db/session.py`：创建 Engine、Session，并为每个 HTTP 请求提供独立数据库会话。

Session 负责事务边界。写操作成功后提交，失败时回滚，请求结束后关闭连接。

### `core/`

全局配置和基础能力。

- `core/config.py`：读取 `.env`，提供 API 前缀、CORS 和数据库连接地址。

业务代码不应到处直接读取环境变量，而应统一通过 Settings 使用配置。

### `main.py`

FastAPI 应用入口。创建应用、配置 CORS 和安全响应头、挂载 `/api/v1` 路由。

## `backend/migrations/`

Alembic 数据库结构版本。

- `env.py`：连接项目 Settings 和 SQLAlchemy Metadata。
- `versions/`：每一次表结构变化对应一个迁移文件。

模型修改后应创建新迁移，不应修改已经在共享环境执行过的旧迁移。

## `backend/tests/`

后端自动测试。

- `conftest.py`：创建隔离测试数据库并替换真实数据库依赖。
- `test_system.py`：首页、健康和数据库就绪接口。
- `test_documents.py`：完整 CRUD 生命周期和重复数据冲突。

单元/接口测试使用临时 SQLite 提高速度；真实 PostgreSQL 由迁移和 HTTPS 冒烟测试额外验证。

## 一次文档创建请求如何流动

```text
POST /api/v1/documents
        ↓
api/routes/documents.py
        ↓ 使用 DocumentCreate 校验输入
schemas/document.py
        ↓
repositories/document.py
        ↓ 使用请求级 Session
db/session.py
        ↓ 使用 Document 映射
models/document.py
        ↓
PostgreSQL documents 表
        ↓
DocumentResponse 转换为 JSON 返回
```

## 数据库结构如何变化

```text
修改 SQLAlchemy Model
        ↓
生成并检查 Alembic migration
        ↓
uv run alembic upgrade head
        ↓
PostgreSQL 表结构升级
```

SQLAlchemy Model 表示“代码认为表应该是什么样”，Alembic migration 表示“数据库如何从旧版本变成新版本”。两者必须保持一致。

## 本地运行组合

```text
Docker Compose       → 启动 PostgreSQL/pgvector
Alembic              → 创建或升级 documents 表
FastAPI + Uvicorn    → 提供 HTTPS API
Swagger              → 手工调用并观察 CRUD
pytest               → 自动验证接口行为
```

PDF 二进制文件进入 `storage/dev/blobs/`，数据库只保存文件元数据和 `storage_key`；迁移到阿里云后，上传服务可以替换为 OSS 实现，而 API 和数据库模型保持稳定。

## 一次 PDF 上传如何流动

```text
POST /api/v1/documents/upload
        ↓ multipart/form-data
api/routes/documents.py
        ↓
services/document_upload.py
        ├── 清理原始文件名
        ├── 流式写入临时文件
        ├── 检查大小与 PDF 文件头
        ├── pypdf 验证并统计页数
        ├── 计算 SHA-256 和最终 storage_key
        ├── 原子移动到 storage/dev/blobs/
        └── DocumentRepository 创建数据库记录
                ↓
        DocumentResponse 返回给客户端
```
