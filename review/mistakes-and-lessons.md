# Mistakes and Lessons

## 2026-10-26 - 本地 HTTPS 冒烟测试受到系统代理和 PowerShell 转义影响

问题：
- Python HTTP 客户端请求 `https://localhost:8443` 时继承系统代理并超时。
- PostgreSQL 的 `psql \d` 元命令在 PowerShell 多层调用中出现转义和等待问题。

原因：
- 本机配置了代理环境，客户端默认信任环境代理设置。
- 反斜杠元命令经过 PowerShell、Docker Compose 和 psql 多层解析，行为不够稳定。

修正：
- 本地 Python 冒烟请求显式使用 `trust_env=False`，或使用 `curl --noproxy '*'`。
- 自动验证数据库结构时使用 `information_schema` 普通 SQL，不依赖 psql 元命令。

未来规则：
- localhost 自动测试必须显式绕过系统代理。
- 跨 shell 的数据库自动化优先使用标准 SQL，减少命令转义依赖。

## 2026-10-26 - Alembic 状态命令与数据库连接在 `localhost:5432` 下卡死

问题：
- `uv run alembic current` 在已完成迁移后仍未在预期时间内退出。
- 前端请求 `/api/v1/documents` 时一直处于“正在读取文档…”转圈状态，而 `/api/v1/health` 毫秒级返回。

原因：
- 本机 Windows 的 `DllHost.exe` 监听了 IPv6 `[::1]:5432`，当 `DATABASE_URL` 使用 `localhost:5432` 时，`psycopg` / `libpq` 会命中 `[::1]:5432` 并建立 TCP 连接，但该进程不返回 PostgreSQL 握手包，导致连接无限期阻塞；而直接连接 IPv4 `127.0.0.1:5432` 仅需 `15ms`。

修正：
- 将 `backend/app/core/config.py` 与 `.env.example` 中的默认 `DATABASE_URL` 主机名从 `localhost:5432` 改为显式 IPv4 `127.0.0.1:5432`。

未来规则：
- Windows 本地开发环境下，数据库连接与 Vite 代理目标统一显式使用 `127.0.0.1` 而非 `localhost`，避免 IPv6 `[::1]` 端口抢占或解析延迟。
## 2026-10-26 - Vite 前端首次构建缺少客户端类型声明

问题：
- TypeScript 构建无法识别 `import.meta.env` 和 CSS 副作用导入。

原因：
- 手动建立最小 Vite 工程时遗漏了 Vite 的客户端类型引用文件。

修正：
- 添加 `frontend/src/vite-env.d.ts`，引用 `vite/client`。

未来规则：
- 手动创建 Vite + TypeScript 前端时，将 `vite-env.d.ts` 纳入最小脚手架检查清单。

## 2026-10-27 - 本机 Docker Desktop 安装路径非默认 Program Files

问题：
- 按常见默认路径 `C:\Program Files\Docker\Docker\Docker Desktop.exe` 或 `C:\Users\Lenovo\AppData\Local\Programs\Docker\...` 启动 Docker Desktop 失败。

原因：
- 本机 Docker Desktop 实际安装在用户目录 `C:\Users\Lenovo\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe`。

修正：
- 使用已确认的真实路径 `C:\Users\Lenovo\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe` 启动守护进程。

未来规则：
- 需要自动拉起本机 Docker Desktop 时，固定使用 `C:\Users\Lenovo\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe`。

## 2026-10-27 - 全局 `X-Frame-Options: DENY` 拦截前端详情页 `<iframe>` 内嵌 PDF 预览

问题：
- 前端详情页改用 `<iframe src="/api/v1/documents/{id}/file" />` 内嵌渲染 PDF 时，后端返回 `X-Frame-Options: DENY` 会被浏览器拒绝在框架中加载。

原因：
- `backend/app/main.py` 的安全响应头中间件对所有响应统一设置了 `X-Frame-Options: DENY`，未考虑同源前端通过 Vite `/api` 代理内嵌预览 PDF 的场景。

修正：
- 将 `X-Frame-Options` 调整为 `SAMEORIGIN`，并在 `backend/tests/test_document_upload.py` 中增加对 `/file` 响应头的断言。

未来规则：
- 当新增前端 `<iframe>` / `<embed>` / `<object>` 内嵌资源预览时，必须同步检查后端 `X-Frame-Options` 与 CSP `frame-ancestors` 响应头。

## 2026-10-27 - Repository 类内 `def list()` 方法遮蔽内置 `list[...]` 类型注解

问题：
- 在 `DocumentRepository` 中定义 `def replace_pages(..., pages: list[DocumentPageCreate])` 时，导入阶段报错 `TypeError: 'staticmethod' object is not subscriptable`。

原因：
- `DocumentRepository` 已定义了同名静态方法 `def list(...)`，在未启用延迟注解求值时，Python 在类体作用域内将 `list[...]` 解析为对该静态方法对象做下标操作。

修正：
- 在 `backend/app/repositories/document.py` 顶部添加 `from __future__ import annotations`。

未来规则：
- 当类中存在与内置类型同名的方法（如 `list`、`set`、`dict`、`type`）时，文件顶部必须声明 `from __future__ import annotations`。

## 2026-10-27 - PDF 文本提取中的 `\x00` 空字节与 PostgreSQL `TEXT` 字段兼容处理

问题：
- 部分学术 PDF 字体编码在 `pypdf.extract_text()` 时会产生 NUL (`\x00`) 字符，直接写入 PostgreSQL `TEXT` 字段会触发数据库异常。

修正：
- 在 `backend/app/services/document_parser.py` 的 `_normalize_page_text()` 中显式清理 `\x00` 并统一换行符。

未来规则：
- 任何外部文件解析出的文本在写入 PostgreSQL 前，必须经过 NUL (`\x00`) 字节清洗。
