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
  askDocumentQuestion,
  checkBackend,
  deleteDocument,
  documentFileUrl,
  getAIConfig,
  listDocumentChunks,
  listDocumentPages,
  listDocuments,
  parseDocument,
  searchDocumentChunks,
  updateAIConfig,
  uploadDocument,
} from "./api";
import type {
  AIConfigSummary,
  ChunkSearchHit,
  DocumentChunkListResponse,
  DocumentChunkRecord,
  DocumentChunkType,
  DocumentPageListResponse,
  DocumentPageRecord,
  DocumentRecord,
  RagAskResponse,
  SearchMode,
} from "./types";

type Page = "library" | "detail";
type InspectorTab = "chunks" | "qa" | "pages" | "meta";

const chunkTypeLabel: Record<DocumentChunkType, string> = {
  text: "段落切块",
  table: "表格 Key-Value",
  image: "图片提取预留",
};

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
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("chunks");
  const [pagesData, setPagesData] = useState<DocumentPageListResponse | null>(null);
  const [chunksData, setChunksData] = useState<DocumentChunkListResponse | null>(null);
  const [chunkFilter, setChunkFilter] = useState<DocumentChunkType | "all">("all");
  const [chunkQuery, setChunkQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("hybrid");
  const [searchHits, setSearchHits] = useState<ChunkSearchHit[] | null>(null);
  const [searchingChunks, setSearchingChunks] = useState(false);
  const [aiConfig, setAiConfig] = useState<AIConfigSummary | null>(null);
  const [configOpen, setConfigOpen] = useState(false);
  const [cfgProvider, setCfgProvider] = useState("deepseek");
  const [cfgModel, setCfgModel] = useState("deepseek-chat");
  const [cfgBaseUrl, setCfgBaseUrl] = useState("https://api.deepseek.com/v1");
  const [cfgApiKey, setCfgApiKey] = useState("");
  const [savingConfig, setSavingConfig] = useState(false);
  const [qaQuestion, setQaQuestion] = useState("");
  const [qaLoading, setQaLoading] = useState(false);
  const [qaResult, setQaResult] = useState<RagAskResponse | null>(null);
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
      const [pagesResult, chunksResult] = await Promise.all([
        listDocumentPages(documentId),
        listDocumentChunks(documentId),
      ]);
      setPagesData(pagesResult);
      setChunksData(chunksResult);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法读取页面解析结果");
    } finally {
      setPagesLoading(false);
    }
  }

  const hitMap = useMemo(() => {
    const map = new Map<string, ChunkSearchHit>();
    if (searchHits) {
      for (const h of searchHits) map.set(h.chunk.id, h);
    }
    return map;
  }, [searchHits]);

  const visibleChunks = useMemo<DocumentChunkRecord[]>(() => {
    if (chunkQuery.trim() && searchHits !== null) {
      const fromHits = searchHits.map((h) => h.chunk);
      return chunkFilter === "all"
        ? fromHits
        : fromHits.filter((item) => item.chunk_type === chunkFilter);
    }
    const all = chunksData?.items ?? [];
    return chunkFilter === "all" ? all : all.filter((item) => item.chunk_type === chunkFilter);
  }, [chunksData, chunkFilter, chunkQuery, searchHits]);

  useEffect(() => {
    void checkBackend().then(setBackendOnline);
    void getAIConfig()
      .then((cfg) => {
        setAiConfig(cfg);
        setCfgProvider(cfg.active_llm);
        setCfgModel(cfg.llm_model);
        setCfgBaseUrl(cfg.llm_base_url);
      })
      .catch(() => null);
    void refreshDocuments();
  }, []);

  function handleSelectProvider(providerKey: string) {
    setCfgProvider(providerKey);
    const preset = aiConfig?.llm_presets?.[providerKey];
    if (preset) {
      setCfgModel(preset.model);
      setCfgBaseUrl(preset.base_url);
    }
    setCfgApiKey("");
  }

  async function handleSaveAIConfig() {
    setSavingConfig(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await updateAIConfig({
        active_llm: cfgProvider,
        llm_model: cfgModel,
        llm_base_url: cfgBaseUrl,
        ...(cfgApiKey.trim() ? { llm_api_key: cfgApiKey.trim() } : {}),
      });
      setAiConfig(updated);
      setCfgApiKey("");
      setConfigOpen(false);
      setMessage(
        `模型配置已保存：${updated.active_llm} (${updated.llm_model}) · ${
          updated.llm_api_configured ? "API Key 已就绪" : "未填 Key（使用离线证据模式）"
        }`,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存模型配置失败");
    } finally {
      setSavingConfig(false);
    }
  }

  useEffect(() => {
    const q = chunkQuery.trim();
    if (!q || !selected) {
      setSearchHits(null);
      setSearchingChunks(false);
      return;
    }
    let cancelled = false;
    setSearchingChunks(true);
    const timer = window.setTimeout(() => {
      void searchDocumentChunks(q, {
        documentId: selected.id,
        chunkType: chunkFilter === "all" ? undefined : chunkFilter,
        mode: searchMode,
      })
        .then((res) => {
          if (!cancelled) setSearchHits(res.items);
        })
        .catch(() => {
          if (!cancelled) setSearchHits([]);
        })
        .finally(() => {
          if (!cancelled) setSearchingChunks(false);
        });
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [chunkQuery, selected?.id, chunkFilter, searchMode]);

  useEffect(() => {
    if (page === "detail" && selected) {
      setActivePdfPage(1);
      setChunkFilter("all");
      setChunkQuery("");
      setQaQuestion("");
      setQaResult(null);
      void loadPagesForDocument(selected.id);
    } else {
      setPagesData(null);
      setChunksData(null);
      setQaResult(null);
    }
  }, [page, selected?.id]);

  async function handleAskQuestion(customQuestion?: string) {
    if (!selected) return;
    const q = (customQuestion ?? qaQuestion).trim();
    if (!q) return;
    if (customQuestion) setQaQuestion(customQuestion);
    setQaLoading(true);
    setError(null);
    try {
      const res = await askDocumentQuestion(selected.id, q, searchMode, 4);
      setQaResult(res);
      if (res.citations.length > 0) {
        setActivePdfPage(res.citations[0].page_number);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "RAG 问答请求失败");
    } finally {
      setQaLoading(false);
    }
  }

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
    setInspectorTab("chunks");
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
      setInspectorTab("chunks");
      if (result.document.status === "ready") {
        setMessage(
          `解析完成：共 ${result.total_pages} 页，生成 ${result.total_chunks} 个切块（段落 ${result.text_chunks} / 表格 ${result.table_chunks} / 图片 ${result.image_chunks}）`,
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
                          {document.keywords && document.keywords.length > 0 && (
                            <span className="row-keywords">
                              {document.keywords.slice(0, 5).map((kw) => (
                                <em key={kw} className="kw-chip">{kw}</em>
                              ))}
                            </span>
                          )}
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
                    aria-selected={inspectorTab === "chunks"}
                    className={`inspector-tab ${inspectorTab === "chunks" ? "active" : ""}`}
                    onClick={() => setInspectorTab("chunks")}
                  >
                    <Sparkles size={14} />
                    <span>结构化切块</span>
                    {chunksData && chunksData.total_chunks > 0 && (
                      <span className="tab-badge">{chunksData.total_chunks}</span>
                    )}
                  </button>
                  <button
                    role="tab"
                    type="button"
                    aria-selected={inspectorTab === "qa"}
                    className={`inspector-tab ${inspectorTab === "qa" ? "active" : ""}`}
                    onClick={() => setInspectorTab("qa")}
                  >
                    <Search size={14} />
                    <span>AI 问答 (RAG)</span>
                  </button>
                  <button
                    role="tab"
                    type="button"
                    aria-selected={inspectorTab === "pages"}
                    className={`inspector-tab ${inspectorTab === "pages" ? "active" : ""}`}
                    onClick={() => setInspectorTab("pages")}
                  >
                    <BookOpen size={14} />
                    <span>逐页原文</span>
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
                    <span>元数据</span>
                  </button>
                </div>

                {inspectorTab === "chunks" ? (
                  <div className="parsed-pages-panel">
                    <div className="parse-summary-card">
                      <div className="parse-summary-main">
                        <strong>
                          {selected.status === "ready"
                            ? "已完成关键词、表格 KV、段落切块与 pgvector 向量化"
                            : "尚未生成结构化切块"}
                        </strong>
                        <span>
                          {chunksData && chunksData.total_chunks > 0
                            ? `共 ${chunksData.total_chunks} 块（已向量化 ${chunksData.embedded_chunks ?? chunksData.total_chunks} 块 · ${aiConfig?.embedding_model ?? "256d"}）：段落 ${chunksData.text_chunks} · 表格 ${chunksData.table_chunks} · 图片 ${chunksData.image_chunks}`
                            : "点击右侧按钮自动提取文档关键词、表格键值、完整段落并生成 pgvector 向量"}
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

                    {(chunksData?.keywords?.length || selected.keywords?.length) ? (
                      <div className="keywords-bar">
                        <span className="keywords-label">文档核心关键词（点击筛选切块）：</span>
                        <div className="keywords-list">
                          {(chunksData?.keywords?.length ? chunksData.keywords : selected.keywords).map((kw) => {
                            const active = chunkQuery.toLowerCase() === kw.toLowerCase();
                            return (
                              <button
                                key={kw}
                                type="button"
                                className={`keyword-pill ${active ? "is-active" : ""}`}
                                onClick={() => setChunkQuery(active ? "" : kw)}
                              >
                                #{kw}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}

                    <div className="chunk-toolbar">
                      <div className="chunk-filter-pills">
                        <button
                          type="button"
                          className={`filter-pill ${chunkFilter === "all" ? "active" : ""}`}
                          onClick={() => setChunkFilter("all")}
                        >
                          全部 ({chunksData?.total_chunks ?? 0})
                        </button>
                        <button
                          type="button"
                          className={`filter-pill ${chunkFilter === "text" ? "active" : ""}`}
                          onClick={() => setChunkFilter("text")}
                        >
                          段落 ({chunksData?.text_chunks ?? 0})
                        </button>
                        <button
                          type="button"
                          className={`filter-pill ${chunkFilter === "table" ? "active" : ""}`}
                          onClick={() => setChunkFilter("table")}
                        >
                          表格 KV ({chunksData?.table_chunks ?? 0})
                        </button>
                        <button
                          type="button"
                          className={`filter-pill ${chunkFilter === "image" ? "active" : ""}`}
                          onClick={() => setChunkFilter("image")}
                        >
                          图片 ({chunksData?.image_chunks ?? 0})
                        </button>
                      </div>
                      <div className="search-mode-bar">
                        <div className="search-mode-group" role="group" aria-label="检索模式">
                          <button
                            type="button"
                            className={`mode-pill ${searchMode === "hybrid" ? "active" : ""}`}
                            onClick={() => setSearchMode("hybrid")}
                          >
                            混合检索 (Hybrid)
                          </button>
                          <button
                            type="button"
                            className={`mode-pill ${searchMode === "semantic" ? "active" : ""}`}
                            onClick={() => setSearchMode("semantic")}
                          >
                            向量语义 (pgvector)
                          </button>
                          <button
                            type="button"
                            className={`mode-pill ${searchMode === "keyword" ? "active" : ""}`}
                            onClick={() => setSearchMode("keyword")}
                          >
                            关键词 (Keyword)
                          </button>
                        </div>
                        {aiConfig && (
                          <span className="ai-config-chip" title={`配置文件: ${aiConfig.config_file}`}>
                            向量: {aiConfig.active_embedding} · LLM: {aiConfig.active_llm}
                          </span>
                        )}
                      </div>
                      <label className="chunk-search-input">
                        <Search size={14} />
                        <input
                          type="search"
                          value={chunkQuery}
                          onChange={(e) => setChunkQuery(e.target.value)}
                          placeholder="输入跨语言语义问题（如：自注意力机制复杂度）或关键词检索…"
                        />
                        {searchingChunks && <RefreshCw className="spin" size={13} />}
                        {chunkQuery && (
                          <button type="button" onClick={() => setChunkQuery("")} aria-label="清空过滤">
                            <X size={13} />
                          </button>
                        )}
                      </label>
                    </div>

                    {pagesLoading ? (
                      <div className="state-panel compact">
                        <RefreshCw className="spin" size={18} />
                        <span>正在读取结构化切块…</span>
                      </div>
                    ) : visibleChunks.length === 0 ? (
                      <div className="empty-pages-hint">
                        <Sparkles size={24} />
                        <strong>{chunksData?.total_chunks ? "没有匹配当前筛选条件的切块" : "暂无结构化切块"}</strong>
                        <p>{chunksData?.total_chunks ? "请切换分类或清空搜索词。" : "点击上方“开始解析”，系统将自动提取关键词、表格 Key-Value、完整段落与内嵌图片。"}</p>
                      </div>
                    ) : (
                      <div className="page-card-list">
                        {visibleChunks.map((chunk) => (
                          <article
                            key={chunk.id}
                            className={`page-card chunk-card chunk-${chunk.chunk_type} ${activePdfPage === chunk.page_number ? "is-active" : ""}`}
                          >
                            <header className="page-card-header">
                              <button
                                type="button"
                                className="page-jump-button"
                                onClick={() => setActivePdfPage(chunk.page_number)}
                                title={`左侧 PDF 跳转到第 ${chunk.page_number} 页`}
                              >
                                <strong>第 {chunk.page_number} 页 · #{chunk.chunk_index + 1}</strong>
                                <span>跳转预览</span>
                              </button>
                              <div className="page-card-meta">
                                {hitMap.get(chunk.id) && (
                                  <span className="score-badge">
                                    综合 {hitMap.get(chunk.id)!.score.toFixed(2)} · 向量 {hitMap.get(chunk.id)!.semantic_score.toFixed(2)}
                                  </span>
                                )}
                                {chunk.has_embedding && !hitMap.get(chunk.id) && (
                                  <span className="vector-badge">pgvector 256d</span>
                                )}
                                <span>{chunk.char_count.toLocaleString()} 字符</span>
                                <span className={`chunk-type-badge ${chunk.chunk_type}`}>
                                  {chunkTypeLabel[chunk.chunk_type]}
                                </span>
                              </div>
                            </header>
                            {chunk.title && <div className="chunk-card-title">{chunk.title}</div>}

                            {chunk.chunk_type === "table" && chunk.meta.rows ? (
                              <div className="kv-table-list">
                                {chunk.meta.rows.map((row, rIdx) => (
                                  <div key={rIdx} className="kv-table-row">
                                    {row.map((pair, cIdx) => (
                                      <div key={cIdx} className="kv-pair-item">
                                        <span className="kv-key">{pair.key}</span>
                                        <span className="kv-val">{pair.value}</span>
                                      </div>
                                    ))}
                                  </div>
                                ))}
                              </div>
                            ) : chunk.chunk_type === "image" ? (
                              <div className="image-chunk-body">
                                {chunk.meta.image_url && (
                                  <img
                                    src={chunk.meta.image_url}
                                    alt={chunk.title ?? "PDF 内嵌图片"}
                                    className="extracted-figure-preview"
                                    loading="lazy"
                                  />
                                )}
                                <p className="page-card-text">{chunk.content}</p>
                              </div>
                            ) : (
                              <pre className="page-card-text">{chunk.content}</pre>
                            )}
                          </article>
                        ))}
                      </div>
                    )}
                  </div>
                ) : inspectorTab === "qa" ? (
                  <div className="parsed-pages-panel">
                    <div className="rag-qa-box">
                      <div className="search-mode-bar">
                        <strong>带页码引用溯源的 RAG 问答</strong>
                        <div className="page-card-meta">
                          {aiConfig && (
                            <span className={aiConfig.llm_api_configured ? "score-badge" : "ai-config-chip"}>
                              {aiConfig.active_llm} ({aiConfig.llm_model}) ·{" "}
                              {aiConfig.llm_api_configured
                                ? `已配 Key (${aiConfig.llm_api_key_masked || "****"})`
                                : "离线抽取模式"}
                            </span>
                          )}
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => setConfigOpen((v) => !v)}
                          >
                            {configOpen ? "收起配置" : "配置模型 / API Key"}
                          </button>
                        </div>
                      </div>

                      {configOpen && (
                        <div className="llm-config-card">
                          <div className="llm-config-grid">
                            <label className="llm-config-field">
                              <span>选择大模型厂商</span>
                              <select
                                value={cfgProvider}
                                onChange={(e) => handleSelectProvider(e.target.value)}
                              >
                                {(aiConfig?.available_llm_providers ?? ["deepseek", "qwen", "openai"]).map((p) => (
                                  <option key={p} value={p}>
                                    {p === "deepseek"
                                      ? "DeepSeek (deepseek)"
                                      : p === "qwen"
                                        ? "通义千问 / 百炼 (qwen)"
                                        : p === "openai"
                                          ? "OpenAI 兼容接口 (openai)"
                                          : p}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label className="llm-config-field">
                              <span>模型名称 (Model)</span>
                              <input
                                type="text"
                                value={cfgModel}
                                onChange={(e) => setCfgModel(e.target.value)}
                                placeholder="如 deepseek-chat / qwen-plus"
                              />
                            </label>
                            <label className="llm-config-field">
                              <span>API 地址 (Base URL)</span>
                              <input
                                type="text"
                                value={cfgBaseUrl}
                                onChange={(e) => setCfgBaseUrl(e.target.value)}
                                placeholder="https://api.deepseek.com/v1"
                              />
                            </label>
                            <label className="llm-config-field">
                              <span>
                                API Key{" "}
                                {aiConfig?.llm_presets?.[cfgProvider]?.api_configured
                                  ? `（已存 ${aiConfig.llm_presets[cfgProvider].api_key_masked}，留空保持不变）`
                                  : "（填入 sk-... 密钥）"}
                              </span>
                              <input
                                type="password"
                                value={cfgApiKey}
                                onChange={(e) => setCfgApiKey(e.target.value)}
                                placeholder="sk-..."
                              />
                            </label>
                          </div>
                          <div className="llm-config-actions">
                            <small>保存后自动写入本地 config/ai_providers.json（已忽略 Git 提交）</small>
                            <button
                              type="button"
                              className="primary-button"
                              disabled={savingConfig}
                              onClick={() => void handleSaveAIConfig()}
                            >
                              {savingConfig ? "保存中…" : "保存并连接模型"}
                            </button>
                          </div>
                        </div>
                      )}
                      <form
                        className="rag-qa-form"
                        onSubmit={(e) => {
                          e.preventDefault();
                          void handleAskQuestion();
                        }}
                      >
                        <input
                          type="text"
                          value={qaQuestion}
                          onChange={(e) => setQaQuestion(e.target.value)}
                          placeholder="输入你的研究问题（如：本文提出的核心架构与自注意力机制复杂度优势是什么？）"
                        />
                        <button
                          className="primary-button"
                          type="submit"
                          disabled={qaLoading || !qaQuestion.trim()}
                        >
                          {qaLoading ? <><RefreshCw className="spin" size={14} /> 检索生成中</> : <><Sparkles size={14} /> 提问</>}
                        </button>
                      </form>
                      <div className="keywords-list">
                        {[
                          "为什么使用 Self-Attention，它在计算复杂度和并行化上有什么优势？",
                          "本文的模型架构、核心指标或实验结果是什么？",
                          "这份文档的阶段规划与核心任务有哪些？",
                        ].map((preset) => (
                          <button
                            key={preset}
                            type="button"
                            className="keyword-pill"
                            onClick={() => void handleAskQuestion(preset)}
                          >
                            {preset}
                          </button>
                        ))}
                      </div>
                    </div>

                    {qaResult && (
                      <>
                        {qaResult.llm_error && (
                          <div className="parse-error-banner" role="alert">
                            <AlertCircle size={15} />
                            <span>
                              大模型 API 调用未通过（已自动降级为离线证据模式）：{qaResult.llm_error}
                            </span>
                          </div>
                        )}
                        <div className="rag-answer-card">
                          <div className="rag-answer-header">
                            <strong>AI 回答（基于 Top-{qaResult.citations.length} 检索证据）</strong>
                            <span className="vector-badge">
                              {qaResult.used_extractive_fallback
                                ? "离线证据综合 (Extractive)"
                                : `${qaResult.llm_provider}:${qaResult.llm_model}`}
                            </span>
                          </div>
                          <div className="rag-answer-body">{qaResult.answer}</div>
                        </div>

                        <div className="rag-citations-list">
                          {qaResult.citations.map((cit) => (
                            <article
                              key={cit.chunk_id}
                              className={`page-card chunk-card chunk-${cit.chunk_type} ${activePdfPage === cit.page_number ? "is-active" : ""}`}
                            >
                              <header className="page-card-header">
                                <button
                                  type="button"
                                  className="page-jump-button"
                                  onClick={() => setActivePdfPage(cit.page_number)}
                                >
                                  <strong>[{cit.citation_index}] 第 {cit.page_number} 页 · #{cit.chunk_index + 1}</strong>
                                  <span>点击跳转原文</span>
                                </button>
                                <div className="page-card-meta">
                                  <span className="score-badge">
                                    综合 {cit.score.toFixed(2)} · 向量 {cit.semantic_score.toFixed(2)}
                                  </span>
                                  <span className={`chunk-type-badge ${cit.chunk_type}`}>
                                    {chunkTypeLabel[cit.chunk_type]}
                                  </span>
                                </div>
                              </header>
                              {cit.title && <div className="chunk-card-title">{cit.title}</div>}
                              <pre className="page-card-text">{cit.snippet}</pre>
                            </article>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                ) : inspectorTab === "pages" ? (
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
