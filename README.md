# AI Research Hub

面向个人研究者的 AI 智能文档理解与研究分析平台。

当前里程碑是 `v0.2` 文档接入与逐页解析闭环：React 工作台前端、FastAPI 本地开发 HTTPS、PostgreSQL、SQLAlchemy、Alembic、PDF 上传、文档 CRUD 以及 PDF 逐页文本提取与页码联动预览。

## 本地启动后端

在项目根目录执行：

```powershell
uv sync
docker compose up -d db
uv run alembic upgrade head
powershell -ExecutionPolicy Bypass -File .\scripts\run_backend_https.ps1
```

首次启动会在 `backend/certs/` 下生成仅供本地开发使用的自签名证书。

启动后访问：

- API 首页：<https://localhost:8443/>
- Swagger 文档：<https://localhost:8443/docs>
- 健康检查：<https://localhost:8443/api/v1/health>
- 数据库就绪检查：<https://localhost:8443/api/v1/ready>
- 文档列表：<https://localhost:8443/api/v1/documents>

浏览器会提示自签名证书不受信任，这是本地开发证书的正常现象。不要将证书和私钥提交到 Git，也不要把这套证书用于生产环境。

## 本地启动前端

保持后端终端运行，再打开一个 PowerShell：

```powershell
cd .\frontend
npm install
npm run dev
```

访问 <http://127.0.0.1:5173>。开发服务器会把 `/api` 请求代理到本地 HTTPS 后端，因此页面操作不需要处理证书警告；直接打开 <https://localhost:8443/docs> 时，浏览器仍可能要求接受一次本地自签名证书。

页面可以完成：

- 选择并上传 PDF；
- 查看标题、页数、大小、SHA-256、存储键等元数据；
- 在新标签页打开原始 PDF；
- 软删除文档记录。

## 文档 CRUD

| 方法 | 地址 | 作用 |
|---|---|---|
| `POST` | `/api/v1/documents` | 创建文档元数据 |
| `POST` | `/api/v1/documents/upload` | 上传、校验并保存 PDF |
| `GET` | `/api/v1/documents` | 分页列出文档 |
| `GET` | `/api/v1/documents/{id}` | 查询单篇文档 |
| `GET` | `/api/v1/documents/{id}/file` | 在浏览器中打开原始 PDF |
| `POST` | `/api/v1/documents/{id}/parse` | 触发 PDF 逐页文本解析并落盘 |
| `GET` | `/api/v1/documents/{id}/pages` | 获取文档的逐页解析文本与统计 |
| `PATCH` | `/api/v1/documents/{id}` | 更新文档字段 |
| `DELETE` | `/api/v1/documents/{id}` | 软删除文档 |

上传接口接收 `multipart/form-data`：`file` 为必填 PDF，`title` 为可选标题。后端会流式计算 SHA-256、验证 PDF、提取页数，并按内容哈希保存到 `storage/dev/blobs/`。重复文件返回 409，默认大小上限为 100 MB，可通过 `MAX_PDF_SIZE_MB` 调整。

文件采用内容寻址路径：

```text
storage/dev/blobs/<sha256 前两位>/<完整 sha256>.pdf
```

可以在 Swagger 中直接执行上传和完整 CRUD。

## 数据分别保存在哪里

- PDF 原文件：项目目录下的 `storage/dev/blobs/<哈希前两位>/<完整哈希>.pdf`。
- 文档元数据：Docker 中运行的 PostgreSQL 的 `documents` 表。
- PostgreSQL 数据文件：Docker 命名卷 `ai-research-hub_postgres_data`，停止容器不会丢失；执行 `docker compose down -v` 会删除该卷和数据库数据，请谨慎使用。
- `DELETE /documents/{id}` 当前是软删除：列表里不再显示记录，但 PDF 文件仍留在磁盘，便于以后实现回收站。

页面中的“查看数据”用于查看数据库返回的元数据；“打开 PDF”用于查看磁盘中的原文件。需要直接检查数据库时，可以执行：

```powershell
docker compose exec db psql -U ai_research_hub -d ai_research_hub -c "SELECT id, title, page_count, file_size, sha256, storage_key, status, created_at FROM documents ORDER BY created_at DESC;"
```

## Docker 在当前项目中的作用

Docker 当前只负责运行 PostgreSQL/pgvector，让本机无需手动安装和配置数据库服务。FastAPI、React 前端和 PDF 文件仍直接运行或保存在本机。`docker compose up -d db` 启动数据库，`docker compose stop db` 暂停数据库并保留数据，`docker compose logs db` 查看数据库日志。

以后部署到阿里云时，可以让 Docker 同时运行后端、前端和 PostgreSQL；PDF 可先放服务器磁盘，正式使用时更推荐迁移到 OSS。Docker 负责提供一致的运行环境，但它本身不是数据库，也不是云备份。

目录和模块关系详见 [`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md)。Codex、Antigravity 与用户的项目状态、决策边界和交接记录统一维护在 [`docs/AI_COLLABORATION.md`](docs/AI_COLLABORATION.md)。

## 验证

```powershell
uv run pytest
uv run ruff check .
cd .\frontend
npm run build
```
