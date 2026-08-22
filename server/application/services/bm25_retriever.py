# -*- coding: utf-8 -*-
"""
BM25稀疏检索模块
- 基于 rank_bm25.BM25Okapi + jieba 中文分词
- 支持租户过滤(tenant_id)与磁盘持久化(重启后自动加载)
"""
import os
import pickle
import threading
from typing import List, Dict, Any, Optional

from utils.config_handler import config
from utils.logger_handler import logger

# 数据目录 server/data
SERVER_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(SERVER_DIR, 'data')
BM25_INDEX_FILE = os.path.join(DATA_DIR, 'bm25_index.pkl')


def tokenize(text: str) -> List[str]:
    """中文分词，失败退化为逐字切分"""
    try:
        import jieba
        return [w for w in jieba.cut(text) if w.strip()]
    except ImportError:
        logger.warning("jieba not installed, using char-level tokenization")
        return list(text)


class BM25Retriever:
    """BM25索引与检索"""

    def __init__(self):
        self._lock = threading.Lock()
        self._chunks: List[Dict[str, Any]] = []        # 原始块信息
        self._corpus: List[List[str]] = []             # 分词后的语料
        self._bm25 = None
        self._load_from_disk()

    # ---------- 持久化 ----------
    def _load_from_disk(self):
        if os.path.exists(BM25_INDEX_FILE):
            try:
                with open(BM25_INDEX_FILE, 'rb') as f:
                    data = pickle.load(f)
                self._chunks = data.get('chunks', [])
                self._corpus = data.get('corpus', [])
                self._rebuild_index()
                logger.info(f"BM25 index loaded from disk: {len(self._chunks)} chunks")
            except Exception as e:
                logger.error(f"Failed to load BM25 index from disk: {e}")
                self._chunks, self._corpus = [], []

    def _save_to_disk(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(BM25_INDEX_FILE, 'wb') as f:
                pickle.dump({'chunks': self._chunks, 'corpus': self._corpus}, f)
        except Exception as e:
            logger.error(f"Failed to save BM25 index to disk: {e}")

    def _rebuild_index(self):
        try:
            from rank_bm25 import BM25Okapi
            self._bm25 = BM25Okapi(self._corpus) if self._corpus else None
        except ImportError:
            logger.error("rank_bm25 not installed")
            self._bm25 = None

    # ---------- 索引操作 ----------
    def add_chunks(self, chunks: List[Any]):
        """增量添加LangChain Document块(带metadata)"""
        with self._lock:
            for chunk in chunks:
                meta = chunk.metadata
                self._chunks.append({
                    'doc_id': meta.get('doc_id'),
                    'parent_id': meta.get('parent_id'),
                    'source': meta.get('source', ''),
                    'tenant_id': meta.get('tenant_id', 1),
                    'chunk_index': meta.get('chunk_index', 0),
                    'doc_level': meta.get('doc_level', 'public'),
                    'min_level': meta.get('min_level', 1),
                    'owner_id': meta.get('owner_id'),
                    'text': chunk.page_content
                })
                self._corpus.append(tokenize(chunk.page_content))
            self._rebuild_index()
            self._save_to_disk()

    def rebuild(self, chunks: List[Any]):
        """全量重建"""
        with self._lock:
            self._chunks = []
            self._corpus = []
            self.add_chunks(chunks)

    def clear(self):
        """清空索引"""
        with self._lock:
            self._chunks = []
            self._corpus = []
            self._bm25 = None
            if os.path.exists(BM25_INDEX_FILE):
                try:
                    os.remove(BM25_INDEX_FILE)
                except OSError:
                    pass

    def remove_doc(self, doc_id) -> set:
        """移除某文档的全部块并持久化，返回被移除块的 parent_id 集合（供父窗口映射清理）"""
        with self._lock:
            keep_chunks, keep_corpus = [], []
            removed_parents = set()
            for chunk, corpus in zip(self._chunks, self._corpus):
                if chunk.get('doc_id') == doc_id:
                    removed_parents.add(chunk.get('parent_id'))
                else:
                    keep_chunks.append(chunk)
                    keep_corpus.append(corpus)
            if not removed_parents:
                return set()
            self._chunks, self._corpus = keep_chunks, keep_corpus
            self._rebuild_index()
            self._save_to_disk()
            logger.info(f"BM25 removed doc {doc_id}: {len(removed_parents)} chunks")
            return removed_parents

    # ---------- 检索 ----------
    def search(
        self,
        query: str,
        top_k: int,
        tenant_id: Optional[int] = None,
        user_id: Optional[int] = None,
        clearance_level: Optional[int] = None,
        acl_doc_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        BM25检索

        Args:
            query: 查询文本
            top_k: 返回数量
            tenant_id: 租户过滤(为空则不过滤)
            user_id: 查询用户ID(所有者恒可见)
            clearance_level: 用户密级(1公开/2内部/3机密/4绝密)
            acl_doc_ids: 用户被显式授权的文档ID列表(覆盖部门与密级)

        Returns:
            候选列表，每个元素为 {doc_id, parent_id, source, tenant_id, chunk_index, text, score}
            score 为 BM25分数(越大越相关)
        """
        if self._bm25 is None or not self._chunks:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        acl_doc_ids = acl_doc_ids or []

        def _visible(chunk: Dict[str, Any]) -> bool:
            if tenant_id is None:                      # admin 不过滤
                return True
            if chunk.get('owner_id') == user_id:       # 所有者
                return True
            if chunk.get('doc_id') in acl_doc_ids:     # 显式授权(覆盖部门/密级)
                return True
            # 同部门 + 公开 + 密级达标
            return (
                chunk.get('tenant_id') == tenant_id
                and chunk.get('doc_level') == 'public'
                and chunk.get('min_level', 1) <= (clearance_level or 1)
            )

        scores = self._bm25.get_scores(query_tokens)
        results = []
        for idx, score in enumerate(scores):
            chunk = self._chunks[idx]
            if not _visible(chunk):
                continue
            results.append({**chunk, 'score': float(score)})

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]
