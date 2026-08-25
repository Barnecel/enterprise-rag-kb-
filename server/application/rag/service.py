# -*- coding: utf-8 -*-
"""RAG服务编排层（P1重构组装点）"""
import os
import logging
import threading
from typing import Optional

from utils.logger_handler import logger
from utils.config_handler import config
from application.rag import state
from application.rag.state import _bm25, LANCHAIN_AVAILABLE, Chroma
from application.rag.embeddings import OMLXEmbeddings
from application.rag.retrievers import RetrievalMixin
from application.rag.ingestion import IngestionMixin
from application.rag.generator import GenerationMixin
from application.rag.model_registry import RegistryMixin, LLM_CONFIG, EMBEDDING_CONFIG
from application.rag.visibility import VisibilityMixin
from application.services.reranker import Reranker
from application.services.query_rewriter import QueryRewriter
from application.services.cache_manager import CacheManager

CHROMA_CONFIG = config.get_section('chroma')

_rag_service_instance: Optional["RAGService"] = None
_rag_service_lock = threading.Lock()

class RAGService(RetrievalMixin, IngestionMixin, GenerationMixin, RegistryMixin, VisibilityMixin):
    """
    RAG服务类 - 封装检索增强生成的核心逻辑
    """

    def __init__(self):
        """初始化RAG服务，加载向量库和LLM模型"""
        self.vectorstore = None
        self.embeddings = None
        self.bm25 = _bm25
        self.reranker = Reranker()
        self.query_rewriter = QueryRewriter()
        self.cache_manager = CacheManager()
        self._initialize_embeddings()
        self._initialize_vectorstore()

    def _initialize_embeddings(self):
        """
        初始化嵌入模型
        使用oMLX的Qwen3-Embedding-8B-4bit-DWQ
        """
        if not LANCHAIN_AVAILABLE:
            logger.warning("LangChain not available, using mock embeddings")
            self.embeddings = None
            return

        try:
            self.embeddings = OMLXEmbeddings(
                api_base=EMBEDDING_CONFIG['api_base'],
                api_key=LLM_CONFIG.get('api_key', 'dummy'),
                model_name=EMBEDDING_CONFIG['model_name'],
                query_instruction=EMBEDDING_CONFIG.get('query_instruction', '')
            )
            logger.info(f"Embedding model initialized: {EMBEDDING_CONFIG['model_name']} at {EMBEDDING_CONFIG['api_base']}")
        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {e}")
            self.embeddings = None

    def _initialize_vectorstore(self):
        """
        初始化Chroma向量数据库
        """
        if not LANCHAIN_AVAILABLE or self.embeddings is None:
            return

        try:
            persist_dir = CHROMA_CONFIG['persist_directory']
            if os.path.exists(persist_dir):
                self.vectorstore = Chroma(
                    collection_name=CHROMA_CONFIG['collection_name'],
                    persist_directory=persist_dir,
                    embedding_function=self.embeddings
                )
                logger.info(f"Vector store loaded from: {persist_dir}")
            else:
                os.makedirs(persist_dir, exist_ok=True)
                logger.info(f"New vector store will be created at: {persist_dir}")
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            self.vectorstore = None

    # ============================================================
    # 文档加载与入库 (特性2: 父子索引 / 特性5: 租户元数据)
    # ============================================================


def get_rag_service() -> "RAGService":
    """获取全局唯一的 RAGService 实例（线程安全，避免重复初始化 Chroma 客户端）"""
    global _rag_service_instance
    if _rag_service_instance is None:
        with _rag_service_lock:
            if _rag_service_instance is None:
                _rag_service_instance = RAGService()
    return _rag_service_instance
