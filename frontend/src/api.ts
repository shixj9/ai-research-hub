import type {
  DocumentListResponse,
  DocumentPageListResponse,
  DocumentParseResponse,
  DocumentRecord,
} from "./types";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "/api/v1"
).replace(/\/$/, "");

async function parseError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
    if (data.detail) return JSON.stringify(data.detail);
  } catch {
    // The fallback below is clearer for non-JSON server errors.
  }
  return `请求失败（HTTP ${response.status}）`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) throw new Error(await parseError(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function checkBackend(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

export function listDocuments(): Promise<DocumentListResponse> {
  return request<DocumentListResponse>("/documents?limit=100");
}

export function uploadDocument(file: File, title: string): Promise<DocumentRecord> {
  const body = new FormData();
  body.append("file", file);
  if (title.trim()) body.append("title", title.trim());
  return request<DocumentRecord>("/documents/upload", { method: "POST", body });
}

export function deleteDocument(documentId: string): Promise<void> {
  return request<void>(`/documents/${documentId}`, { method: "DELETE" });
}

export function parseDocument(documentId: string): Promise<DocumentParseResponse> {
  return request<DocumentParseResponse>(`/documents/${documentId}/parse`, {
    method: "POST",
  });
}

export function listDocumentPages(documentId: string): Promise<DocumentPageListResponse> {
  return request<DocumentPageListResponse>(`/documents/${documentId}/pages`);
}

export function documentFileUrl(documentId: string, pageNumber?: number): string {
  const base = `${API_BASE_URL}/documents/${documentId}/file`;
  return pageNumber && pageNumber >= 1 ? `${base}#page=${pageNumber}` : base;
}
