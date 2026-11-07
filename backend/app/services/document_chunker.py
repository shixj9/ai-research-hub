from __future__ import annotations

import re
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

from PIL import Image
from sqlalchemy.orm import Session

from backend.app.repositories.document import DocumentRepository
from backend.app.schemas.document import (
    ChunkSearchHit,
    ChunkSearchResponse,
    DocumentChunkCreate,
    DocumentChunkResponse,
    DocumentChunkType,
)

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "have", "has", "had", "not", "but", "you", "all", "can", "her", "his", "our",
    "out", "use", "used", "using", "each", "which", "their", "into", "more",
    "other", "than", "then", "also", "these", "those", "such", "when", "where",
    "who", "will", "would", "could", "should", "about", "after", "before", "between",
    "under", "over", "while", "what", "how", "why", "paper", "figure", "table",
    "section", "model", "models", "based", "results", "show", "shown", "one", "two",
    "我们", "可以", "一个", "这个", "那个", "进行", "通过", "使用", "以及", "或者", "如果",
    "因为", "所以", "但是", "需要", "什么", "怎么", "如何", "哪些", "包括", "提供", "实现",
    "支持", "问题", "内容", "阶段", "建议", "部分", "开始", "后续", "说明", "自己", "能够",
}

FLOWCHART_MARKERS = ("↓", "↑", "→", "←", "├", "└", "│", "┌", "┐", "┘", "┴", "┬")
HEADING_RE = re.compile(
    r"^(?:第\s*[0-9一二三四五六七八九十]+\s*[章节阶段周天部分]|"
    r"[0-9]+(?:\.[0-9]+)*\s+\S+|[一二三四五六七八九十]+[、.．]\s*\S+)"
)


def extract_document_keywords(
    title: str,
    page_texts: list[str],
    *,
    table_values: list[str] | None = None,
    max_keywords: int = 8,
) -> list[str]:
    """Extract representative technical keywords covering the PDF document."""
    scores: Counter[str] = Counter()
    display_map: dict[str, str] = {}

    def add_candidate(raw_term: str, weight: float) -> None:
        term = raw_term.strip(" ,.;:!?()[]{}<>\"'“”‘’、，。；：！？/\\|-")
        if len(term) < 2 or len(term) > 28:
            return
        lower = term.lower()
        if lower in STOPWORDS or lower.isdigit():
            return
        if re.fullmatch(r"[0-9.\-+%]+", lower):
            return
        scores[lower] += weight
        if lower not in display_map or (term[0].isupper() and not display_map[lower][0].isupper()):
            display_map[lower] = term

    for token in re.findall(r"[A-Za-z][A-Za-z0-9_+.\-]{2,24}|[\u4e00-\u9fff]{2,8}", title):
        add_candidate(token, 5.0)

    full_text = "\n".join(page_texts)
    for match in re.finditer(
        r"\b(?:[A-Z][a-zA-Z0-9+\-]{2,18}(?:\s+[A-Z][a-zA-Z0-9+\-]{2,18}){0,2})\b",
        full_text,
    ):
        phrase = match.group(0)
        if phrase.lower() not in STOPWORDS:
            add_candidate(phrase, 1.8)

    for line in full_text.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) > 60:
            continue
        if HEADING_RE.match(stripped):
            for tok in re.findall(r"[A-Za-z][A-Za-z0-9_+.\-]{2,20}|[\u4e00-\u9fff]{2,6}", stripped):
                add_candidate(tok, 3.0)

    for cell_text in table_values or []:
        for tok in re.findall(r"[A-Za-z][A-Za-z0-9_+.\-]{2,20}|[\u4e00-\u9fff]{2,6}", cell_text):
            add_candidate(tok, 2.2)

    for tok in re.findall(r"[\u4e00-\u9fff]{2,6}", full_text):
        if len(tok) <= 4 and tok not in STOPWORDS:
            add_candidate(tok, 0.6)

    ranked: list[str] = []
    for key, _ in scores.most_common(max_keywords * 3):
        candidate = display_map[key]
        if any(
            candidate.lower() != existing.lower()
            and (candidate.lower() in existing.lower() or existing.lower() in candidate.lower())
            and len(candidate) < len(existing)
            for existing in ranked
        ):
            continue
        ranked.append(candidate)
        if len(ranked) >= max_keywords:
            break
    return ranked


def extract_query_keywords(query: str) -> list[str]:
    cleaned = query.strip()
    if not cleaned:
        return []
    tokens = re.findall(r"[A-Za-z0-9_+.\-]{2,24}|[\u4e00-\u9fff]{2,8}", cleaned)
    result: list[str] = []
    for tok in tokens:
        low = tok.lower()
        if low in STOPWORDS:
            continue
        if low not in [r.lower() for r in result]:
            result.append(tok)
    return result or [cleaned]


def clean_page_paragraphs(raw_text: str) -> list[str]:
    """Clean PDF line wraps, de-hyphenate broken words, and preserve complete paragraphs."""
    if not raw_text.strip():
        return []

    text = raw_text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"([A-Za-z]{2,})-\n\s*([a-z]{2,})", r"\1\2", text)

    lines = [line.strip() for line in text.split("\n")]
    paragraphs: list[str] = []
    current_lines: list[str] = []

    def flush() -> None:
        if not current_lines:
            return
        joined = "\n".join(current_lines).strip()
        if joined:
            paragraphs.append(joined)
        current_lines.clear()

    for line in lines:
        if not line:
            flush()
            continue

        is_flowchart = any(marker in line for marker in FLOWCHART_MARKERS) or len(line) <= 18
        is_heading = bool(HEADING_RE.match(line))
        is_bullet = line.startswith(("•", "-", "*", "·")) or bool(re.match(r"^\d+[.)、]\s*", line))

        if is_heading:
            flush()
            paragraphs.append(line)
            continue

        if is_flowchart or is_bullet:
            current_lines.append(line)
            continue

        if current_lines:
            prev = current_lines[-1]
            sentence_endings = ("。", "！", "？", ".", "!", "?", ":", "：", ";", "；")
            prev_ends_sentence = prev.endswith(sentence_endings)
            prev_is_special = any(m in prev for m in FLOWCHART_MARKERS) or len(prev) <= 18
            if not prev_ends_sentence and not prev_is_special:
                is_cjk_join = bool(
                    re.search(r"[\u4e00-\u9fff]$", prev)
                    and re.match(r"^[\u4e00-\u9fff]", line)
                )
                sep = "" if is_cjk_join else " "
                current_lines[-1] = f"{prev}{sep}{line}"
                continue

        current_lines.append(line)

    flush()
    return paragraphs


def build_text_chunks_for_page(
    page_number: int,
    raw_text: str,
    *,
    start_index: int,
    max_chars: int = 580,
) -> list[DocumentChunkCreate]:
    paragraphs = clean_page_paragraphs(raw_text)
    if not paragraphs:
        return []

    chunks: list[DocumentChunkCreate] = []
    buffer: list[str] = []
    buffer_len = 0
    current_title: str | None = None

    def emit_chunk(text_block: str, title: str | None) -> None:
        cleaned = text_block.strip()
        if not cleaned:
            return
        idx = start_index + len(chunks)
        chunks.append(
            DocumentChunkCreate(
                page_number=page_number,
                chunk_index=idx,
                chunk_type=DocumentChunkType.TEXT,
                title=title or f"第 {page_number} 页 · 段落切块 #{len(chunks) + 1}",
                content=cleaned,
                char_count=len(cleaned),
                meta={"strategy": "paragraph_first", "paragraph_count": cleaned.count("\n") + 1},
            )
        )

    for para in paragraphs:
        if HEADING_RE.match(para) and len(para) <= 60:
            if buffer:
                emit_chunk("\n\n".join(buffer), current_title)
                buffer.clear()
                buffer_len = 0
            current_title = para[:120]
            buffer.append(para)
            buffer_len += len(para)
            continue

        if len(para) > max_chars:
            if buffer:
                emit_chunk("\n\n".join(buffer), current_title)
                buffer.clear()
                buffer_len = 0
            sentences = re.split(r"(?<=[。！？.!?])\s+", para)
            sub_buf: list[str] = []
            sub_len = 0
            for sent in sentences:
                if sub_len + len(sent) > max_chars and sub_buf:
                    emit_chunk(" ".join(sub_buf), current_title)
                    sub_buf = [sub_buf[-1]] if len(sub_buf[-1]) < 120 else []
                    sub_len = sum(len(s) for s in sub_buf)
                sub_buf.append(sent)
                sub_len += len(sent)
            if sub_buf:
                emit_chunk(" ".join(sub_buf), current_title)
            continue

        if buffer_len + len(para) + 2 > max_chars and buffer:
            emit_chunk("\n\n".join(buffer), current_title)
            buffer.clear()
            buffer_len = 0

        buffer.append(para)
        buffer_len += len(para) + 2

    if buffer:
        emit_chunk("\n\n".join(buffer), current_title)

    return chunks


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    cleaned = str(value).replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"\s*\n\s*", " ", cleaned).strip()
    return cleaned


def extract_table_chunks_for_page(
    plumber_page: Any,
    page_number: int,
    *,
    start_index: int,
) -> tuple[list[DocumentChunkCreate], list[str]]:
    """Extract structured tables from a PDF page and bind column keys with row values."""
    chunks: list[DocumentChunkCreate] = []
    table_terms: list[str] = []

    try:
        raw_tables = plumber_page.extract_tables() or []
    except Exception:
        return [], []

    for table_idx, raw_table in enumerate(raw_tables, start=1):
        if not raw_table or len(raw_table) < 2:
            continue

        cleaned_rows = [[_clean_cell(cell) for cell in row] for row in raw_table if row]
        cleaned_rows = [row for row in cleaned_rows if any(cell for cell in row)]
        if len(cleaned_rows) < 2:
            continue

        col_count = max(len(row) for row in cleaned_rows)
        if col_count < 2 or col_count > 12:
            continue

        total_cells = sum(len(row) for row in cleaned_rows)
        non_empty_cells = sum(1 for row in cleaned_rows for cell in row if len(cell) >= 2)
        if total_cells == 0 or (non_empty_cells / total_cells) < 0.5:
            continue

        headers = [
            cleaned_rows[0][i] if i < len(cleaned_rows[0]) and cleaned_rows[0][i] else f"列{i + 1}"
            for i in range(col_count)
        ]
        table_terms.extend(headers)

        structured_rows: list[list[dict[str, str]]] = []
        formatted_lines: list[str] = []

        for row in cleaned_rows[1:]:
            kv_pairs: list[dict[str, str]] = []
            line_parts: list[str] = []
            for col_i in range(col_count):
                key = headers[col_i]
                val = row[col_i] if col_i < len(row) else ""
                if not val:
                    continue
                kv_pairs.append({"key": key, "value": val})
                line_parts.append(f"{key}: {val}")
                table_terms.append(val)
            if kv_pairs:
                structured_rows.append(kv_pairs)
                formatted_lines.append(" | ".join(line_parts))

        if not structured_rows:
            continue

        title = f"第 {page_number} 页 · 表格 #{table_idx}（{' / '.join(headers[:4])}）"
        content = "\n".join(formatted_lines)
        chunks.append(
            DocumentChunkCreate(
                page_number=page_number,
                chunk_index=start_index + len(chunks),
                chunk_type=DocumentChunkType.TABLE,
                title=title[:300],
                content=content,
                char_count=len(content),
                meta={
                    "headers": headers,
                    "rows": structured_rows,
                    "row_count": len(structured_rows),
                    "col_count": col_count,
                },
            )
        )

    return chunks, table_terms


def _find_figure_caption(page_text: str, image_idx: int) -> str | None:
    matches = re.findall(
        r"(?:Figure|Fig\.|图)\s*\d+\s*[:：.]?\s*[^\n]{3,120}",
        page_text,
        flags=re.IGNORECASE,
    )
    if matches:
        chosen = matches[min(image_idx - 1, len(matches) - 1)]
        return chosen.strip()
    return None


def extract_image_chunks_for_page(
    pypdf_page: Any,
    page_number: int,
    *,
    document_id: UUID,
    page_text: str,
    storage_root: Path,
    start_index: int,
) -> list[DocumentChunkCreate]:
    """Extract embedded PDF images to local storage and reserve OCR/VLM fields."""
    chunks: list[DocumentChunkCreate] = []
    try:
        images = list(getattr(pypdf_page, "images", []))
    except Exception:
        return []

    if not images:
        return []

    figures_dir = storage_root.resolve() / "figures" / str(document_id)
    figures_dir.mkdir(parents=True, exist_ok=True)

    for img_idx, img_file in enumerate(images, start=1):
        try:
            raw_bytes = getattr(img_file, "data", None)
            if not raw_bytes:
                continue
            with Image.open(BytesIO(raw_bytes)) as pil_img:
                width, height = pil_img.size
                if width < 64 or height < 64:
                    continue
                filename = f"page_{page_number}_img_{img_idx}.png"
                target_path = figures_dir / filename
                pil_img.convert("RGB").save(target_path, format="PNG")
        except Exception:
            continue

        caption = _find_figure_caption(page_text, img_idx)
        title = caption or f"第 {page_number} 页 · 内嵌图片 #{img_idx} ({width}×{height})"
        image_url = f"/api/v1/documents/{document_id}/figures/{filename}"
        content = (
            f"[图片切块预留] 所在页: 第 {page_number} 页 | 尺寸: {width}×{height} px"
            + (f" | 图注: {caption}" if caption else "")
            + " | 状态: 已提取原图，预留后续 OCR / 多模态 VLM 视觉描述接入"
        )
        chunks.append(
            DocumentChunkCreate(
                page_number=page_number,
                chunk_index=start_index + len(chunks),
                chunk_type=DocumentChunkType.IMAGE,
                title=title[:300],
                content=content,
                char_count=len(content),
                meta={
                    "figure_name": filename,
                    "image_url": image_url,
                    "width": width,
                    "height": height,
                    "caption": caption,
                    "ocr_status": "reserved",
                    "ocr_text": None,
                    "vlm_description": None,
                },
            )
        )

    return chunks


def search_document_chunks(
    db: Session,
    query: str,
    *,
    document_id: UUID | None = None,
    chunk_type: DocumentChunkType | None = None,
    limit: int = 30,
) -> ChunkSearchResponse:
    keywords = extract_query_keywords(query)
    if not keywords:
        return ChunkSearchResponse(query=query, extracted_keywords=[], total=0, items=[])

    candidates = DocumentRepository.list_searchable_chunks(
        db,
        document_id=document_id,
        chunk_type=chunk_type,
    )
    hits: list[ChunkSearchHit] = []
    for chunk_model, doc_title in candidates:
        haystack = f"{chunk_model.title or ''}\n{chunk_model.content}".lower()
        matched: list[str] = []
        score = 0.0
        for kw in keywords:
            kw_low = kw.lower()
            count = haystack.count(kw_low)
            if count > 0:
                matched.append(kw)
                title_bonus = 2.5 if kw_low in (chunk_model.title or "").lower() else 0.0
                type_bonus = 1.2 if chunk_model.chunk_type == "table" else 1.0
                score += (3.0 + min(count, 5) * 0.8 + title_bonus) * type_bonus
        if matched:
            hits.append(
                ChunkSearchHit(
                    chunk=DocumentChunkResponse.model_validate(chunk_model),
                    document_title=doc_title,
                    score=round(score, 2),
                    matched_keywords=matched,
                )
            )

    hits.sort(key=lambda item: (-len(item.matched_keywords), -item.score, item.chunk.page_number))
    return ChunkSearchResponse(
        query=query,
        extracted_keywords=keywords,
        total=len(hits),
        items=hits[:limit],
    )
