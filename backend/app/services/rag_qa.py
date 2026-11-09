from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from backend.app.schemas.document import (
    ChunkSearchHit,
    RagAskRequest,
    RagAskResponse,
    RagCitation,
)
from backend.app.services.document_chunker import search_document_chunks
from backend.app.services.embedding_service import _resolve_api_key, load_ai_providers_raw

RAG_SYSTEM_PROMPT = (
    "你是一个严谨的学术与技术文档研究助手（AI Research Hub）。\n"
    "请严格依据下方提供的【检索证据切块】回答用户问题，遵守以下规则：\n"
    "1. 只使用证据中明确出现的事实、数据和结论，不得编造证据之外的信息；\n"
    "2. 在引述每个关键结论、指标或段落后，必须使用方括号标注对应的证据编号，例如 [1]、[2]；\n"
    "3. 如果证据中包含表格 Key-Value 数据，请准确列出关键指标对比并标注对应编号；\n"
    "4. 如果提供的证据不足以回答该问题，请直接说明当前文档未包含相关内容。"
)


def _build_citation(idx: int, hit: ChunkSearchHit) -> RagCitation:
    raw = hit.chunk.content.strip()
    snippet = raw if len(raw) <= 260 else f"{raw[:257]}..."
    return RagCitation(
        citation_index=idx,
        chunk_id=hit.chunk.id,
        document_id=hit.chunk.document_id,
        document_title=hit.document_title,
        page_number=hit.chunk.page_number,
        chunk_index=hit.chunk.chunk_index,
        chunk_type=hit.chunk.chunk_type,
        title=hit.chunk.title,
        snippet=snippet,
        score=hit.score,
        semantic_score=hit.semantic_score,
        keyword_score=hit.keyword_score,
    )


def _format_context_for_llm(citations: list[RagCitation], hits: list[ChunkSearchHit]) -> str:
    blocks: list[str] = []
    for cit, hit in zip(citations, hits, strict=False):
        header = (
            f"[{cit.citation_index}] 文档: 《{cit.document_title}》 | "
            f"第 {cit.page_number} 页 | 切块 #{cit.chunk_index + 1} "
            f"({cit.chunk_type.value})"
        )
        if cit.title:
            header += f" | 标题: {cit.title}"
        blocks.append(f"{header}\n{hit.chunk.content}")
    return "\n\n---\n\n".join(blocks)


def _call_openai_compatible_llm(
    question: str,
    context_text: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    temperature: float = 0.2,
    max_tokens: int = 1200,
) -> tuple[str | None, str | None]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    user_prompt = (
        f"【用户问题】\n{question}\n\n"
        f"【检索证据切块】\n{context_text}\n\n"
        "请基于上述检索证据给出条理清晰、带 [1][2] 引用角标的中文回答："
    )
    payload: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                try:
                    err_msg = resp.json().get("error", {}).get("message") or resp.text[:160]
                except Exception:
                    err_msg = resp.text[:160]
                return None, f"HTTP {resp.status_code}: {err_msg}"
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                return None, "大模型返回结果为空"
            content = choices[0].get("message", {}).get("content", "")
            return (str(content).strip() or None), None
    except Exception as exc:
        return None, f"请求大模型接口异常: {exc}"


def _synthesize_extractive_grounded_answer(
    question: str,
    citations: list[RagCitation],
    hits: list[ChunkSearchHit],
) -> str:
    """Deterministic grounded answer builder when no external LLM API key is configured."""
    if not citations:
        return (
            "未在当前文档库中检索到与该问题直接相关的段落或表格切块。"
            "请确认文档已完成解析，或尝试更换关键词进行提问。"
        )

    lines: list[str] = [
        f"根据混合检索命中的 **{len(citations)}** 个高相关文档切块，"
        "为你整理出以下有据可查的原文证据要点："
    ]

    for cit, hit in zip(citations, hits, strict=False):
        type_name = (
            "表格数据"
            if cit.chunk_type.value == "table"
            else "图片图注"
            if cit.chunk_type.value == "image"
            else "正文段落"
        )
        raw_content = re.sub(r"\s+", " ", hit.chunk.content).strip()
        excerpt = raw_content if len(raw_content) <= 220 else f"{raw_content[:217]}..."
        title_part = f"（{cit.title}）" if cit.title else ""
        lines.append(
            f"- **[{cit.citation_index}] 《{cit.document_title}》"
            f"第 {cit.page_number} 页 · {type_name}{title_part}**："
            f"{excerpt} [{cit.citation_index}]"
        )

    lines.append(
        "\n> 提示：点击上方或下方引用角标（如 `[1]`），"
        "左侧 PDF 预览将直接跳转到对应页码核对原文。"
        "若需启用生成式总结，只需在 `config/ai_providers.json` 中"
        "填入 `deepseek` 或 `qwen` 的 `api_key`。"
    )
    return "\n".join(lines)


def answer_question_with_rag(
    db: Session,
    payload: RagAskRequest,
    *,
    override_document_id: UUID | None = None,
) -> RagAskResponse:
    target_doc_id = override_document_id or payload.document_id
    search_res = search_document_chunks(
        db,
        payload.question,
        document_id=target_doc_id,
        mode=payload.mode,
        limit=payload.top_k,
    )

    hits = search_res.items[: payload.top_k]
    citations = [_build_citation(idx, hit) for idx, hit in enumerate(hits, start=1)]

    raw_cfg = load_ai_providers_raw()
    active_llm_key = str(raw_cfg.get("active_llm") or "deepseek")
    llm_providers = raw_cfg.get("llm_providers") or {}
    llm_cfg = llm_providers.get(active_llm_key) or {}
    llm_model = str(llm_cfg.get("model") or "deepseek-chat")
    base_url = str(llm_cfg.get("base_url") or "").strip()
    api_key = _resolve_api_key(llm_cfg)
    temperature = float(llm_cfg.get("temperature", 0.2))
    max_tokens = int(llm_cfg.get("max_tokens", 1200))

    llm_error_msg: str | None = None
    if hits and api_key and base_url:
        context_text = _format_context_for_llm(citations, hits)
        llm_answer, llm_error_msg = _call_openai_compatible_llm(
            payload.question,
            context_text,
            base_url=base_url,
            api_key=api_key,
            model=llm_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if llm_answer:
            return RagAskResponse(
                question=payload.question,
                answer=llm_answer,
                llm_provider=active_llm_key,
                llm_model=llm_model,
                used_extractive_fallback=False,
                llm_error=None,
                retrieval_mode=payload.mode,
                embedding_model=search_res.embedding_model,
                citations=citations,
            )

    extractive_answer = _synthesize_extractive_grounded_answer(
        payload.question,
        citations,
        hits,
    )
    return RagAskResponse(
        question=payload.question,
        answer=extractive_answer,
        llm_provider=f"{active_llm_key} (extractive_fallback)",
        llm_model=llm_model,
        used_extractive_fallback=True,
        llm_error=llm_error_msg,
        retrieval_mode=payload.mode,
        embedding_model=search_res.embedding_model,
        citations=citations,
    )
