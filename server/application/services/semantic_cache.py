# -*- coding: utf-8 -*-
"""
L2 语义缓存模块
基于轻量级嵌入模型(BAAI/bge-small-zh-v1.5)的语义相似度缓存。
将高频问题的向量存入内存，新问题先计算向量，在缓存库中做余弦相似度检索。
命中(相似度>阈值)后直接返回缓存的答案，完全绕过文档向量库和LLM调用。

依赖:
- sentence-transformers (pip install sentence-transformers)
- numpy
"""

import os
import time
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Any

import numpy as np

from utils.logger_handler import logger


@dataclass
class L2Entry:
    """语义缓存条目"""
    question: str
    answer: str
    source_documents: List[int] = field(default_factory=list)
    model_used: str = ""
    embedding: Optional[np.ndarray] = None
    cached_at: float = 0.0
    ttl: int = 86400  # 24小时

    @property
    def is_expired(self) -> bool:
        return time.time() - self.cached_at > self.ttl


class SemanticCache:
    """
    语义缓存（L2）
    基于向量相似度的问题匹配，使用轻量级嵌入模型。
    线程安全，支持TTL过期和LRU淘汰。
    """

    def __init__(self, config: dict):
        """
        初始化语义缓存

        Args:
            config: cache.yml 中 l2_cache 章节的配置
        """
        self.enabled = config.get('enabled', True)
        self.ttl = int(config.get('ttl', 86400))
        self.max_entries = int(config.get('max_entries', 5000))
        self.similarity_threshold = float(config.get('similarity_threshold', 0.92))
        self.model_name = config.get('embedding_model', 'BAAI/bge-small-zh-v1.5')

        # 内存存储
        self._entries: List[L2Entry] = []          # 有序列表，尾部为最新
        self._vectors: List[np.ndarray] = []        # 对应条目的向量
        self._lock = threading.Lock()

        # 嵌入模型（懒加载）
        self._model = None
        self._model_lock = threading.Lock()
        self._model_loaded = False

        logger.info(f"SemanticCache initialized: model={self.model_name}, "
                    f"threshold={self.similarity_threshold}, max={self.max_entries}")

    def _lazy_load_model(self):
        """懒加载 sentence-transformers 嵌入模型"""
        if self._model_loaded:
            return True
        if not self.enabled:
            return False
        with self._model_lock:
            if self._model_loaded:
                return True
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading semantic cache embedding model: {self.model_name}")
                # 设置镜像以加速下载
                os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')
                self._model = SentenceTransformer(self.model_name)
                self._model_loaded = True
                logger.info(f"Semantic cache model loaded successfully: {self.model_name}")
                return True
            except Exception as e:
                logger.error(f"Failed to load semantic cache model: {e}")
                self.enabled = False  # 降级：禁用语义缓存
                return False

    def _compute_embedding(self, text: str) -> Optional[np.ndarray]:
        """计算文本的嵌入向量"""
        if not self._lazy_load_model():
            return None
        try:
            vec = self._model.encode(text, normalize_embeddings=True)
            return np.array(vec, dtype=np.float32)
        except Exception as e:
            logger.error(f"Embedding computation failed: {e}")
            return None

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度（向量已归一化时等价于内积）"""
        return float(np.dot(a, b))

    def search(self, query: str) -> Optional[Tuple[L2Entry, float]]:
        """
        在语义缓存中搜索最佳匹配

        Args:
            query: 用户问题

        Returns:
            (L2Entry, similarity_score) 或 None（未命中/出错）
        """
        if not self.enabled or not self._vectors:
            return None

        query_vec = self._compute_embedding(query)
        if query_vec is None:
            return None

        best_score = -1.0
        best_idx = -1

        with self._lock:
            # 清理过期条目
            self._evict_expired()

            for i, vec in enumerate(self._vectors):
                if i >= len(self._entries):
                    break
                score = self._cosine_similarity(query_vec, vec)
                if score > best_score:
                    best_score = score
                    best_idx = i

        if best_idx >= 0 and best_score >= self.similarity_threshold:
            entry = self._entries[best_idx]
            if not entry.is_expired:
                logger.info(f"L2 semantic cache HIT: similarity={best_score:.4f}, "
                            f"question='{query[:50]}' -> '{entry.question[:50]}'")
                return entry, best_score

        logger.debug(f"L2 semantic cache MISS: best_score={best_score:.4f}, "
                     f"threshold={self.similarity_threshold}")
        return None

    def store(self, question: str, answer: str, source_documents: List[int] = None,
              model_used: str = "") -> bool:
        """
        将问题-答案存入语义缓存

        Args:
            question: 问题文本
            answer: 答案文本
            source_documents: 源文档ID列表
            model_used: 使用的模型名称

        Returns:
            bool: 是否成功
        """
        if not self.enabled:
            return False

        vec = self._compute_embedding(question)
        if vec is None:
            return False

        entry = L2Entry(
            question=question,
            answer=answer,
            source_documents=source_documents or [],
            model_used=model_used,
            embedding=vec,
            cached_at=time.time(),
            ttl=self.ttl
        )

        with self._lock:
            # 检查是否已存在相同问题，更新之
            for i, e in enumerate(self._entries):
                if e.question == question:
                    self._entries[i] = entry
                    self._vectors[i] = vec
                    return True

            # 检查容量，淘汰最旧条目
            if len(self._entries) >= self.max_entries:
                self._entries.pop(0)
                self._vectors.pop(0)

            self._entries.append(entry)
            self._vectors.append(vec)

        logger.debug(f"L2 semantic cache stored: '{question[:50]}'")
        return True

    def _evict_expired(self):
        """移除过期条目（调用方需持有锁）"""
        now = time.time()
        before = len(self._entries)
        valid = [(e, v) for e, v in zip(self._entries, self._vectors)
                 if not (now - e.cached_at > e.ttl)]
        self._entries = [e for e, _ in valid]
        self._vectors = [v for _, v in valid]
        after = len(self._entries)
        if before > after:
            logger.info(f"SemanticCache evicted {before - after} expired entries")

    def clear(self):
        """清空语义缓存"""
        with self._lock:
            self._entries.clear()
            self._vectors.clear()
        logger.info("SemanticCache cleared")

    @property
    def size(self) -> int:
        return len(self._entries)