from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

import httpx

from backend.app.core.config import PROJECT_ROOT

EMBEDDING_DIM = 256

# Bilingual semantic concept groups so Chinese queries and English paper chunks
# project onto shared semantic dimensions even in offline/local mode.
BILINGUAL_CONCEPT_CLUSTERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "concept_attention",
        (
            "attention",
            "self-attention",
            "multi-head",
            "scaled dot-product",
            "注意力",
            "自注意力",
            "多头注意力",
            "注意力机制",
            "权重分配",
        ),
    ),
    (
        "concept_architecture",
        (
            "transformer",
            "architecture",
            "encoder",
            "decoder",
            "layer",
            "residual",
            "normalization",
            "架构",
            "模型结构",
            "编码器",
            "解码器",
            "残差连接",
            "网络结构",
        ),
    ),
    (
        "concept_complexity_parallel",
        (
            "complexity",
            "parallel",
            "parallelizable",
            "sequential",
            "computation",
            "recurrent",
            "rnn",
            "lstm",
            "convolutional",
            "复杂度",
            "计算复杂度",
            "并行",
            "并行化",
            "并行计算",
            "序列计算",
            "时间复杂度",
        ),
    ),
    (
        "concept_evaluation_metrics",
        (
            "bleu",
            "perplexity",
            "accuracy",
            "score",
            "benchmark",
            "wmt",
            "translation",
            "english-to-german",
            "english-to-french",
            "sota",
            "实验",
            "实验结果",
            "评估",
            "指标",
            "翻译",
            "性能对比",
            "基线",
            "分数",
        ),
    ),
    (
        "concept_training_optimization",
        (
            "training",
            "optimizer",
            "adam",
            "learning rate",
            "warmup",
            "dropout",
            "label smoothing",
            "gpu",
            "hardware",
            "训练",
            "优化器",
            "学习率",
            "正则化",
            "超参数",
            "训练耗时",
            "硬件",
        ),
    ),
    (
        "concept_positional_embedding",
        (
            "positional",
            "encoding",
            "embedding",
            "wavelength",
            "sinusoid",
            "token",
            "vocabulary",
            "位置编码",
            "词向量",
            "嵌入",
            "正弦",
            "序列位置",
        ),
    ),
    (
        "concept_agent_roadmap",
        (
            "agent",
            "rag",
            "retrieval",
            "vector",
            "pgvector",
            "workflow",
            "prompt",
            "langchain",
            "智能体",
            "检索增强",
            "向量检索",
            "混合检索",
            "学习路线",
            "规划",
            "阶段",
            "周计划",
        ),
    ),
    (
        "concept_model_size_params",
        (
            "parameters",
            "base model",
            "big model",
            "variations",
            "d_model",
            "d_ff",
            "heads",
            "参数量",
            "模型大小",
            "消融实验",
            "消融",
            "维度",
            "层数",
        ),
    ),
)


def get_ai_config_path() -> Path:
    custom_path = os.getenv("AI_PROVIDERS_CONFIG")
    if custom_path:
        path = Path(custom_path)
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()

    primary = PROJECT_ROOT / "config" / "ai_providers.json"
    if primary.is_file():
        return primary
    return PROJECT_ROOT / "config" / "ai_providers.example.json"


def load_ai_providers_raw() -> dict[str, Any]:
    path = get_ai_config_path()
    if not path.is_file():
        return {
            "active_embedding": "local_bilingual",
            "active_llm": "deepseek",
            "embedding_dimensions": EMBEDDING_DIM,
            "embedding_providers": {
                "local_bilingual": {
                    "type": "local_hash",
                    "model": "bilingual-semantic-256d",
                    "description": "内置离线中英双语语义哈希向量（256维）",
                }
            },
            "llm_providers": {},
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {
            "active_embedding": "local_bilingual",
            "active_llm": "deepseek",
            "embedding_dimensions": EMBEDDING_DIM,
            "embedding_providers": {},
            "llm_providers": {},
        }


def _resolve_api_key(provider_cfg: dict[str, Any]) -> str:
    direct = str(provider_cfg.get("api_key") or "").strip()
    if direct:
        return direct
    env_name = str(provider_cfg.get("api_key_env") or "").strip()
    if env_name:
        return os.getenv(env_name, "").strip()
    return ""


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:3]}****{key[-4:]}"


def get_ai_config_summary() -> dict[str, Any]:
    raw = load_ai_providers_raw()
    active_emb_key = str(raw.get("active_embedding") or "local_bilingual")
    active_llm_key = str(raw.get("active_llm") or "deepseek")
    emb_providers = raw.get("embedding_providers") or {}
    llm_providers = raw.get("llm_providers") or {}

    emb_cfg = emb_providers.get(active_emb_key) or {}
    llm_cfg = llm_providers.get(active_llm_key) or {}

    emb_api_key = _resolve_api_key(emb_cfg)
    llm_api_key = _resolve_api_key(llm_cfg)

    llm_presets: dict[str, dict[str, Any]] = {}
    for k, v in llm_providers.items():
        if isinstance(v, dict):
            resolved = _resolve_api_key(v)
            llm_presets[k] = {
                "model": str(v.get("model") or ""),
                "base_url": str(v.get("base_url") or ""),
                "api_configured": bool(resolved),
                "api_key_masked": _mask_key(resolved),
                "description": str(v.get("description") or ""),
            }

    return {
        "config_file": str(get_ai_config_path().relative_to(PROJECT_ROOT))
        if get_ai_config_path().is_relative_to(PROJECT_ROOT)
        else str(get_ai_config_path()),
        "active_embedding": active_emb_key,
        "embedding_model": str(emb_cfg.get("model") or "bilingual-semantic-256d"),
        "embedding_type": str(emb_cfg.get("type") or "local_hash"),
        "embedding_dimensions": EMBEDDING_DIM,
        "embedding_api_configured": bool(emb_api_key)
        or str(emb_cfg.get("type") or "local_hash") == "local_hash",
        "active_llm": active_llm_key,
        "llm_model": str(llm_cfg.get("model") or "deepseek-chat"),
        "llm_base_url": str(llm_cfg.get("base_url") or ""),
        "llm_api_configured": bool(llm_api_key),
        "llm_api_key_masked": _mask_key(llm_api_key),
        "available_embedding_providers": list(emb_providers.keys()),
        "available_llm_providers": list(llm_providers.keys()),
        "llm_presets": llm_presets,
    }


def update_ai_providers_config(
    *,
    active_llm: str | None = None,
    llm_model: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    active_embedding: str | None = None,
    embedding_model: str | None = None,
    embedding_base_url: str | None = None,
    embedding_api_key: str | None = None,
) -> dict[str, Any]:
    raw = load_ai_providers_raw()
    llm_providers = raw.setdefault("llm_providers", {})
    emb_providers = raw.setdefault("embedding_providers", {})

    if active_llm:
        raw["active_llm"] = active_llm
    target_llm = str(raw.get("active_llm") or "deepseek")
    llm_entry = llm_providers.setdefault(
        target_llm,
        {
            "type": "openai_compatible",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "",
            "model": "deepseek-chat",
            "temperature": 0.2,
            "max_tokens": 1500,
        },
    )
    if llm_model is not None and llm_model.strip():
        llm_entry["model"] = llm_model.strip()
    if llm_base_url is not None and llm_base_url.strip():
        llm_entry["base_url"] = llm_base_url.strip()
    if llm_api_key is not None:
        llm_entry["api_key"] = llm_api_key.strip()

    if active_embedding:
        raw["active_embedding"] = active_embedding
    target_emb = str(raw.get("active_embedding") or "local_bilingual")
    emb_entry = emb_providers.setdefault(
        target_emb,
        {
            "type": "local_hash" if target_emb == "local_bilingual" else "openai_compatible",
            "model": "bilingual-semantic-256d",
        },
    )
    if embedding_model is not None and embedding_model.strip():
        emb_entry["model"] = embedding_model.strip()
    if embedding_base_url is not None and embedding_base_url.strip():
        emb_entry["base_url"] = embedding_base_url.strip()
    if embedding_api_key is not None:
        emb_entry["api_key"] = embedding_api_key.strip()

    target_path = get_ai_config_path()
    if target_path.name == "ai_providers.example.json":
        target_path = PROJECT_ROOT / "config" / "ai_providers.json"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return get_ai_config_summary()


def _hash_feature(token: str, dim: int = EMBEDDING_DIM) -> tuple[int, float]:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    val = int.from_bytes(digest, "little")
    idx = val % dim
    sign = 1.0 if ((val >> 31) & 1) == 0 else -1.0
    return idx, sign


def _normalize_vector(vec: list[float], dim: int = EMBEDDING_DIM) -> list[float]:
    if len(vec) != dim:
        projected = [0.0] * dim
        for i, v in enumerate(vec):
            projected[i % dim] += float(v)
        vec = projected
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 1e-12:
        vec[0] = 1.0
        return vec
    return [round(v / norm, 6) for v in vec]


def compute_local_bilingual_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic 256-d bilingual semantic + n-gram hash embedding."""
    cleaned = (text or "").lower().strip()
    vec = [0.0] * dim
    if not cleaned:
        vec[0] = 1.0
        return vec

    # 1. Bilingual concept projection (high weight for cross-lingual semantic alignment)
    for cluster_id, terms in BILINGUAL_CONCEPT_CLUSTERS:
        hit_count = 0
        for term in terms:
            if term in cleaned:
                hit_count += 1
        if hit_count > 0:
            weight = 3.2 * (1.0 + math.log1p(hit_count))
            for salt in range(4):
                idx, sign = _hash_feature(f"{cluster_id}#{salt}", dim)
                vec[idx] += sign * weight

    # 2. English/numeric words & technical tokens
    en_tokens = re.findall(r"[a-z][a-z0-9_+.\-]{1,24}", cleaned)
    for tok in en_tokens:
        idx, sign = _hash_feature(f"w:{tok}", dim)
        vec[idx] += sign * 1.5
        if len(tok) >= 4:
            prefix = tok[:4]
            p_idx, p_sign = _hash_feature(f"pre:{prefix}", dim)
            vec[p_idx] += p_sign * 0.7

    # 3. Chinese character unigrams, bigrams, and trigrams
    cjk_runs = re.findall(r"[\u4e00-\u9fff]{2,}", cleaned)
    for run in cjk_runs:
        for i in range(len(run)):
            if i + 2 <= len(run):
                bg = run[i : i + 2]
                idx, sign = _hash_feature(f"cjk2:{bg}", dim)
                vec[idx] += sign * 1.6
            if i + 3 <= len(run):
                tg = run[i : i + 3]
                idx, sign = _hash_feature(f"cjk3:{tg}", dim)
                vec[idx] += sign * 1.9

    return _normalize_vector(vec, dim)


def _call_openai_compatible_embeddings(
    texts: list[str],
    *,
    base_url: str,
    api_key: str,
    model: str,
    dim: int = EMBEDDING_DIM,
) -> list[list[float]] | None:
    url = f"{base_url.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "input": [t[:4000] if t.strip() else " " for t in texts],
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            items = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
            if len(items) != len(texts):
                return None
            return [_normalize_vector(item["embedding"], dim) for item in items]
    except Exception:
        return None


def embed_texts(texts: list[str]) -> tuple[list[list[float]], str]:
    """Generate 256-d normalized embeddings for a batch of texts using config/ai_providers.json."""
    if not texts:
        return [], "bilingual-semantic-256d"

    raw = load_ai_providers_raw()
    active_key = str(raw.get("active_embedding") or "local_bilingual")
    providers = raw.get("embedding_providers") or {}
    cfg = providers.get(active_key) or {}
    provider_type = str(cfg.get("type") or "local_hash")
    model_name = str(cfg.get("model") or "bilingual-semantic-256d")

    if provider_type == "openai_compatible":
        api_key = _resolve_api_key(cfg)
        base_url = str(cfg.get("base_url") or "").strip()
        if api_key and base_url:
            remote_vectors = _call_openai_compatible_embeddings(
                texts,
                base_url=base_url,
                api_key=api_key,
                model=model_name,
                dim=EMBEDDING_DIM,
            )
            if remote_vectors is not None:
                return remote_vectors, f"{active_key}:{model_name}"

    local_vectors = [compute_local_bilingual_embedding(t, EMBEDDING_DIM) for t in texts]
    return local_vectors, "local_bilingual:bilingual-semantic-256d"


def embed_query(query: str) -> tuple[list[float], str]:
    vectors, model_label = embed_texts([query])
    return vectors[0], model_label


def cosine_similarity(vec_a: list[float] | None, vec_b: list[float] | None) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    return max(0.0, min(1.0, float(dot)))
