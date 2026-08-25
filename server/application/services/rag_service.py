# -*- coding: utf-8 -*-
"""兼容垫片：实现已拆分至 application/rag/*（P1重构）。
新代码请直接从 application.rag.* 导入；本文件仅保留历史导入路径。"""
from utils.config_handler import config
from utils.logger_handler import logger

from application.rag.service import RAGService, get_rag_service
from application.rag.embeddings import OMLXEmbeddings
from application.rag.model_registry import LLM_CONFIG, EMBEDDING_CONFIG
from application.rag.state import (
    _parent_map, _parent_lock, _bm25, _load_parent_map, _save_parent_map,
    PARENT_MAP_FILE, DATA_DIR, LANCHAIN_AVAILABLE,
)

CHROMA_CONFIG = config.get_section('chroma')
RAG_CONFIG = config.get_section('rag')
DOCUMENT_CONFIG = config.get_section('document')
HYBRID_CONFIG = RAG_CONFIG.get('hybrid', {})
RERANK_CONFIG = RAG_CONFIG.get('rerank', {})
DYNAMIC_CONFIG = RAG_CONFIG.get('dynamic_topk', {})
QW_CONFIG = RAG_CONFIG.get('query_rewrite', {})
TENANT_CONFIG = RAG_CONFIG.get('tenant', {})
ENUM_CONFIG = RAG_CONFIG.get('enumeration', {})
