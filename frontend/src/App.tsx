import {
  type ChangeEvent,
  type FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  Database,
  ExternalLink,
  FileText,
  FolderOpen,
  HardDrive,
  Info,
  Library,
  Menu,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Upload,
  WifiOff,
  X,
} from "lucide-react";
import {
  checkBackend,
  deleteDocument,
  documentFileUrl,
  listDocumentPages,
  listDocuments,
  parseDocument,
  uploadDocument,
} from "./api";
import type { DocumentPageListResponse, DocumentPageRecord, DocumentRecord } from "./types";

type Page = "library" | "detail";
type InspectorTab = "pages" | "meta";

const statusLabel: Record<DocumentRecord["status"], string> = {
  uploaded: "待解析",
  processing: "解析中",
  ready: "已解析",
  failed: "解析失败",
};

const pageStatusLabel: Record<DocumentPageRecord["status"], string> = {
  ready: "已提取",
  empty: "空白/无文本",
  failed: "提取异常",
};

function formatBytes(value: number | null): string {
  if (value === null) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 ** 2).toFixed(1)} MB`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function App() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selected, setSelected] = useState<DocumentRecord | null>(null);
  const [page, setPage] = useState<Page>("library");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("pages");
  const [pagesData, setPagesData] = useState<DocumentPageListResponse | null>(null);
  const [pagesLoading, setPagesLoading] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [activePdfPage, setActivePdfPage] = useState<number>(1);
  const [query, setQuery] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const filteredDocuments = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return documents;
    return documents.filter((document) =>
      [document.title, document.original_filename, document.sha256]
        .filter(Boolean)
        .some((value) => value!.toLowerCase().includes(keyword)),
    );
  }, [documents, query]);

  async function refreshDocuments() {
    setLoading(true);
    setError(null);
    try {
      const result = await listDocuments();
      setDocuments(result.items);
      setBackendOnline(true);
      setSelected((current) =>
        current ? result.items.find((item) => item.id === current.id) ?? null : null,
      );
    } catch (caught) {
      setBackendOnline(false);
      setError(caught instanceof Error ? caught.message : "无法读取文档列表");
    } finally {
      setLoading(false);
    }
  }

  async function loadPagesForDocument(documentId: string) {
    setPagesLoading(true);
    try {
      const result = await listDocumentPages(documentId);
      setPagesData(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法读取页面解析结果");
    } finally {
      setPagesLoading(false);
    }
  }

  useEffect(() => {
    void checkBackend().then(setBackendOnline);
    void refreshDocuments();
  }, []);

  useEffect(() => {
    if (page === "detail" && selected) {
      setActivePdfPage(1);
      void loadPagesForDocument(selected.id);
    } else {
      setPagesData(null);
    }
  }, [page, selected?.id]);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setUploadOpen(false);
        setSidebarOpen(false);
      }
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  function openLibrary() {
    setPage("library");
    setSidebarOpen(false);
  }

  function openDocument(document: DocumentRecord) {
    setSelected(document);
    setInspectorTab("pages");
    setPage("detail");
    setSidebarOpen(false);
  }

  function openUpload() {
    setMessage(null);
    setError(null);
    setUploadOpen(true);
  }

  function closeUpload() {
    if (uploading) return;
    setUploadOpen(false);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setError(null);
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("请先选择一个 PDF 文件");
      return;
    }

    setUploading(true);
    setMessage(null);
    setError(null);
    try {
      const created = await uploadDocument(file, title);
      setTitle("");
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      setUploadOpen(false);
      await refreshDocuments();
      setSelected(created);
      setInspectorTab("pages");
      setPage("detail");
      setMessage(`“${created.title}”已上传`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  async function handleParse(document: DocumentRecord) {
    setParsing(true);
    setError(null);
    setMessage(null);
    try {
      const result = await parseDocument(document.id);
      setSelected(result.document);
      await refreshDocuments();
      await loadPagesForDocument(document.id);
      setInspectorTab("pages");
      if (result.document.status === "ready") {
        setMessage(
          `解析完成：共 ${result.total_pages} 页，提取 ${result.non_empty_pages} 页正文（${result.total_chars.toLocaleString()} 字符）`,
        );
      } else {
        setError(result.document.parse_error ?? "未提取到有效正文");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "解析失败");
    } finally {
      setParsing(false);
    }
  }

  async function handleDelete(document: DocumentRecord) {
    if (!window.confirm(`确定删除“${document.title}”吗？原始 PDF 暂时仍会保留。`)) return;
    setError(null);
    setMessage(null);
    try {
      await deleteDocument(document.id);
      setSelected(null);
      setPage("library");
      setMessage("文档记录已软删除");
      await refreshDocuments();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除失败");
    }
  }

  return (
    <div className="app-shell">
      {sidebarOpen && (
        <button
          className="sidebar-backdrop"
          type="button"
          aria-label="关闭导航"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside className={`sidebar ${sidebarOpen ? "is-open" : ""}`}>
        <div className="workspace-brand">
          <span className="workspace-logo"><FileText size={17} /></span>
          <div>
            <strong>Research Hub</strong>
            <span>个人研究空间</span>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="主导航">
          <p className="nav-label">工作空间</p>
          <button className="nav-item active" type="button" onClick={openLibrary}>
            <Library size={16} />
            <span>文档库</span>
            <span className="nav-count">{documents.length}</span>
          </button>
        </nav>

        <div className="sidebar-section">
          <p className="nav-label">本地存储</p>
          <div className="storage-summary">
            <HardDrive size={15} />
            <div>
              <span>PDF 原文件</span>
              <code>storage/dev/blobs</code>
            </div>
          </div>
          <div className="storage-summary">
            <Database size={15} />
            <div>
              <span>元数据与分页正文</span>
              <small>PostgreSQL · documents / document_pages</small>
            </div>
          </div>
        </div>

        <div className="sidebar-footer">
          <div className={`backend-status ${backendOnline ? "online" : "offline"}`}>
            {backendOnline ? <CheckCircle2 size={15} /> : <WifiOff size={15} />}
            <div>
              <span>{backendOnline === null ? "正在检查服务" : backendOnline ? "服务运行正常" : "后端未连接"}</span>
              <small>{backendOnline ? "FastAPI · PostgreSQL" : "请启动后端和数据库"}</small>
            </div>
          </div>
        </div>
      </aside>

      <div className="app-content">
        <header className="app-header">
          <div className="header-leading">
            <button
              className="mobile-menu icon-button"
              type="button"
              aria-label="打开导航"
              onClick={() => setSidebarOpen(true)}
            >
              <Menu size={18} />
            </button>
            {page === "detail" && selected ? (
              <>
                <button className="back-button" type="button" onClick={openLibrary}>
                  <ArrowLeft size={16} /> 返回文档库
                </button>
                <span className="header-divider" />
                <span className="header-document-title">{selected.title}</span>
                <span className={`status-tag ${selected.status}`}>{statusLabel[selected.status]}</span>
              </>
            ) : (
              <div>
                <h1>文档库</h1>
                <p>管理、预览和逐页解析本地研究资料</p>
              </div>
            )}
          </div>

          <div className="header-actions">
            {page === "library" && (
              <label className="search-box">
                <Search size={16} />
                <input
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索文档"
                  aria-label="搜索文档"
                />
                {query && (
                  <button type="button" aria-label="清空搜索" onClick={() => setQuery("")}>
                    <X size={14} />
                  </button>
                )}
              </label>
            )}
            {page === "detail" && selected && (
              <>
                <button
                  className="secondary-button"
                  type="button"
                  disabled={parsing}
                  onClick={() => void handleParse(selected)}
                >
                  {parsing ? (
                    <><RefreshCw className="spin" size={15} /> 正在解析…</>
                  ) : (
                    <><Sparkles size={15} /> {selected.status === "ready" ? "重新解析正文" : "提取 PDF 正文"}</>
                  )}
                </button>
                <a
                  className="secondary-button"
                  href={documentFileUrl(selected.id, activePdfPage)}
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink size={15} /> 新窗口打开
                </a>
              </>
            )}
            <button className="primary-button" type="button" onClick={openUpload}>
              <Upload size={15} /> 上传 PDF
            </button>
          </div>
        </header>

        <main className="main-canvas">
          {(message || error) && (
            <div className={`notice ${error ? "error" : "success"}`} role="status">
              <span>{error ?? message}</span>
              <button type="button" aria-label="关闭提示" onClick={() => { setMessage(null); setError(null); }}>
                <X size={14} />
              </button>
            </div>
          )}

          {page === "library" || !selected ? (
            <section className="library-page" aria-label="文档库">
              <div className="library-toolbar">
                <div>
                  <strong>全部文档</strong>
                  <span>{query ? `${filteredDocuments.length} 项结果` : `${documents.length} 个文件`}</span>
                </div>
                <button className="icon-button" type="button" aria-label="刷新文档" onClick={() => void refreshDocuments()}>
                  <RefreshCw size={16} className={loading ? "spin" : ""} />
                </button>
              </div>

              <div className="document-table" role="table" aria-label="文档列表">
                <div className="table-header" role="row">
                  <span role="columnheader">名称</span>
                  <span role="columnheader">状态</span>
                  <span role="columnheader">页数</span>
                  <span role="columnheader">大小</span>
                  <span role="columnheader">上传时间</span>
                  <span aria-hidden="true" />
                </div>

                {loading ? (
                  <div className="state-panel compact">
                    <RefreshCw className="spin" size={20} />
                    <span>正在读取文档…</span>
                  </div>
                ) : filteredDocuments.length === 0 ? (
                  <div className="state-panel">
                    <span className="empty-icon"><FolderOpen size={26} /></span>
                    <strong>{query ? "没有匹配的文档" : "文档库还是空的"}</strong>
                    <p>{query ? "尝试其他关键词" : "上传第一篇 PDF，建立你的研究资料库。"}</p>
                    {!query && (
                      <button className="secondary-button" type="button" onClick={openUpload}>
                        <Upload size={15} /> 上传 PDF
                      </button>
                    )}
                  </div>
                ) : (
                  filteredDocuments.map((document) => (
                    <div className="table-row" role="row" key={document.id}>
                      <button className="document-name" type="button" onClick={() => openDocument(document)}>
                        <span className="pdf-file-icon"><FileText size={18} /></span>
                        <span>
                          <strong>{document.title}</strong>
                          <small>{document.original_filename ?? "PDF 文档"}</small>
                        </span>
                      </button>
                      <span role="cell"><span className={`status-tag ${document.status}`}>{statusLabel[document.status]}</span></span>
                      <span role="cell" data-label="页数">{document.page_count ?? "—"}</span>
                      <span role="cell" data-label="大小">{formatBytes(document.file_size)}</span>
                      <span role="cell" data-label="上传时间">{formatDate(document.created_at)}</span>
                      <button className="row-open" type="button" aria-label={`查看 ${document.title}`} onClick={() => openDocument(document)}>
                        查看
                      </button>
                    </div>
                  ))
                )}
              </div>
            </section>
          ) : (
            <section className="detail-page" aria-label="文档详情">
              <div className="pdf-panel">
                <div className="panel-heading">
                  <div>
                    <FileText size={16} />
                    <span>PDF 原文预览（第 {activePdfPage} 页）</span>
                  </div>
                  <span>共 {selected.page_count ?? "—"} 页</span>
                </div>
                <div className="pdf-frame-wrap">
                  <iframe
                    key={`${selected.id}-${activePdfPage}`}
                    src={documentFileUrl(selected.id, activePdfPage)}
                    title={`${selected.title} PDF 预览`}
                  />
                </div>
              </div>

              <aside className="document-inspector">
                <div className="inspector-tabs" role="tablist" aria-label="详情面板切换">
                  <button
                    role="tab"
                    type="button"
                    aria-selected={inspectorTab === "pages"}
                    className={`inspector-tab ${inspectorTab === "pages" ? "active" : ""}`}
                    onClick={() => setInspectorTab("pages")}
                  >
                    <BookOpen size={14} />
                    <span>逐页正文</span>
                    {pagesData && pagesData.total_pages > 0 && (
                      <span className="tab-badge">{pagesData.non_empty_pages}/{pagesData.total_pages}</span>
                    )}
                  </button>
                  <button
                    role="tab"
                    type="button"
                    aria-selected={inspectorTab === "meta"}
                    className={`inspector-tab ${inspectorTab === "meta" ? "active" : ""}`}
                    onClick={() => setInspectorTab("meta")}
                  >
                    <Info size={14} />
                    <span>文档元数据</span>
                  </button>
                </div>

                {inspectorTab === "pages" ? (
                  <div className="parsed-pages-panel">
                    <div className="parse-summary-card">
                      <div className="parse-summary-main">
                        <strong>
                          {selected.status === "ready"
                            ? "已完成逐页文本提取"
                            : selected.status === "failed"
                              ? "未能提取到有效文本"
                              : "尚未提取 PDF 文本"}
                        </strong>
                        <span>
                          {pagesData && pagesData.total_pages > 0
                            ? `${pagesData.non_empty_pages}/${pagesData.total_pages} 页含正文 · 共 ${pagesData.total_chars.toLocaleString()} 字符`
                            : "点击按钮使用 pypdf 按页抽取原文并存入 PostgreSQL"}
                        </span>
                      </div>
                      <button
                        className="primary-button"
                        type="button"
                        disabled={parsing}
                        onClick={() => void handleParse(selected)}
                      >
                        {parsing ? (
                          <><RefreshCw className="spin" size={14} /> 解析中</>
                        ) : (
                          <><Sparkles size={14} /> {selected.status === "ready" ? "重新解析" : "开始解析"}</>
                        )}
                      </button>
                    </div>

                    {(selected.parse_error || pagesData?.parse_error) && (
                      <div className="parse-error-banner" role="alert">
                        <AlertCircle size={15} />
                        <span>{selected.parse_error ?? pagesData?.parse_error}</span>
                      </div>
                    )}

                    {pagesLoading ? (
                      <div className="state-panel compact">
                        <RefreshCw className="spin" size={18} />
                        <span>正在读取分页正文…</span>
                      </div>
                    ) : !pagesData || pagesData.items.length === 0 ? (
                      <div className="empty-pages-hint">
                        <BookOpen size={24} />
                        <strong>暂无已保存的分页正文</strong>
                        <p>点击上方“开始解析”，系统将逐页提取文本并与左侧 PDF 预览建立页码联动。</p>
                      </div>
                    ) : (
                      <div className="page-card-list">
                        {pagesData.items.map((item) => (
                          <article
                            key={item.id}
                            className={`page-card ${activePdfPage === item.page_number ? "is-active" : ""}`}
                          >
                            <header className="page-card-header">
                              <button
                                type="button"
                                className="page-jump-button"
                                onClick={() => setActivePdfPage(item.page_number)}
                                title={`左侧 PDF 跳转到第 ${item.page_number} 页`}
                              >
                                <strong>第 {item.page_number} 页</strong>
                                <span>跳转预览</span>
                              </button>
                              <div className="page-card-meta">
                                <span>{item.char_count.toLocaleString()} 字符</span>
                                <span className={`page-status-badge ${item.status}`}>
                                  {pageStatusLabel[item.status]}
                                </span>
                              </div>
                            </header>
                            {item.status === "ready" ? (
                              <pre className="page-card-text">{item.text}</pre>
                            ) : (
                              <p className="page-card-empty">
                                {item.error_message ?? "该页未检测到可提取的文本层（空白页或纯图片内容）。"}
                              </p>
                            )}
                          </article>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <>
                    <div className="inspector-header">
                      <span className="large-file-icon"><FileText size={22} /></span>
                      <div>
                        <h2>{selected.title}</h2>
                        <p>{selected.original_filename ?? "PDF 文档"}</p>
                      </div>
                    </div>

                    <div className="inspector-section">
                      <h3>文档信息</h3>
                      <dl>
                        <div><dt>状态</dt><dd><span className={`status-tag ${selected.status}`}>{statusLabel[selected.status]}</span></dd></div>
                        <div><dt>页数</dt><dd>{selected.page_count ?? "—"}</dd></div>
                        <div><dt>文件大小</dt><dd>{formatBytes(selected.file_size)}</dd></div>
                        <div><dt>文件类型</dt><dd>{selected.mime_type ?? "—"}</dd></div>
                        <div><dt>上传时间</dt><dd>{formatDate(selected.created_at)}</dd></div>
                        <div><dt>解析时间</dt><dd>{selected.parsed_at ? formatDate(selected.parsed_at) : "尚未解析"}</dd></div>
                      </dl>
                    </div>

                    <div className="inspector-section">
                      <h3>存储信息</h3>
                      <div className="technical-field">
                        <span>文档 ID</span>
                        <code>{selected.id}</code>
                      </div>
                      <div className="technical-field">
                        <span>SHA-256</span>
                        <code>{selected.sha256 ?? "—"}</code>
                      </div>
                      <div className="technical-field">
                        <span>存储键</span>
                        <code>{selected.storage_key ?? "—"}</code>
                      </div>
                    </div>

                    <div className="inspector-actions">
                      <a href={documentFileUrl(selected.id, activePdfPage)} target="_blank" rel="noreferrer">
                        <ExternalLink size={15} /> 新窗口打开
                      </a>
                      <button type="button" onClick={() => void handleDelete(selected)}>
                        <Trash2 size={15} /> 删除文档
                      </button>
                    </div>
                  </>
                )}
              </aside>
            </section>
          )}
        </main>
      </div>

      {uploadOpen && (
        <div className="modal-layer" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeUpload();
        }}>
          <section className="upload-dialog" role="dialog" aria-modal="true" aria-labelledby="upload-title">
            <header>
              <div>
                <h2 id="upload-title">上传 PDF</h2>
                <p>文件会保存在本地，元数据写入 PostgreSQL。</p>
              </div>
              <button className="icon-button" type="button" aria-label="关闭上传窗口" onClick={closeUpload}>
                <X size={18} />
              </button>
            </header>

            <form onSubmit={handleUpload}>
              <label className="field-label" htmlFor="document-title">文档标题 <span>可选</span></label>
              <input
                id="document-title"
                className="text-input"
                type="text"
                maxLength={300}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="不填写时使用原始文件名"
              />

              <label className={`file-drop ${file ? "has-file" : ""}`} htmlFor="pdf-file">
                <span className="drop-icon"><Upload size={20} /></span>
                <strong>{file?.name ?? "选择一个 PDF 文件"}</strong>
                <small>{file ? formatBytes(file.size) : "最大 100 MB"}</small>
              </label>
              <input
                ref={fileInput}
                id="pdf-file"
                className="visually-hidden"
                type="file"
                accept="application/pdf,.pdf"
                onChange={handleFileChange}
              />

              {error && <div className="dialog-error">{error}</div>}

              <footer>
                <button className="secondary-button" type="button" onClick={closeUpload} disabled={uploading}>取消</button>
                <button className="primary-button" type="submit" disabled={!file || uploading}>
                  {uploading ? <><RefreshCw className="spin" size={15} /> 正在上传</> : <><Upload size={15} /> 上传文件</>}
                </button>
              </footer>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

export default App;
