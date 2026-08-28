# -*- coding: utf-8 -*-
"""
多级缓存管理器
统筹 L1（精确匹配）、L2（语义缓存）、L3（上下文缓存）三级缓存策略。
核心职责：
1. 按 L1→L2→L3 顺序逐级检查缓存，命中即返回
2. 热点问题检测：L4 执行完毕后判断是否为高频问题，写入各级缓存
3. 统计各级缓存命中率
4. 降级与容错：缓存服务异常时自动走 L4 兜底

集成方式（在 rag_service.py 中）：
    self.cache_manager = CacheManager(config)
    # 在 answer_question 开头：
    result = self.cache_manager.get(question, user_id, tenant_id)
    if result: return result
    # 在 answer_question 末尾：
    self.cache_manager.try_cache_hot_question(question, result)
"""

import time
import threading
import hashlib
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple

from utils.logger_handler import logger
from utils.config_handler import config as app_config
from application.services.semantic_cache import SemanticCache


# ============================================================
# 数据结构
# ============================================================

@dataclass
class L1Entry:
    """L1 精确缓存条目"""
    question: str
    answer: str
    source_documents: List[int] = field(default_factory=list)
    model_used: str = ""
    cached_at: float = 0.0
    ttl: int = 86400  # 24小时

    @property
    def is_expired(self) -> bool:
        return time.time() - self.cached_at > self.ttl


@dataclass
class L3Entry:
    """L3 上下文缓存条目（存储检索结果，省去文档向量检索）"""
    question: str
    retrieved_docs: list = field(default_factory=list)
    retrieval_stats: dict = field(default_factory=dict)
    cached_at: float = 0.0
    ttl: int = 21600  # 6小时

    @property
    def is_expired(self) -> bool:
        return time.time() - self.cached_at > self.ttl


# ============================================================
# 缓存管理器
# ============================================================

class CacheManager:
    """
    多级缓存管理器（单例）
    线程安全，自动降级。
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, cache_config: dict = None):
        """非单例模式（每次调用都会走，但状态只初始化一次）"""
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        config = cache_config or app_config.get_section('cache') or {}

        # ---- L1 配置 ----
        l1_cfg = config.get('l1_cache', {})
        self.l1_enabled = l1_cfg.get('enabled', True)
        self.l1_ttl = int(l1_cfg.get('ttl', 86400))
        self.l1_max = int(l1_cfg.get('max_entries', 10000))
        self._l1: Dict[str, L1Entry] = {}
        self._l1_order: deque = deque()  # 用于LRU淘汰

        # ---- L2 配置（委托给 SemanticCache） ----
        l2_cfg = config.get('l2_cache', {})
        self.l2_enabled = l2_cfg.get('enabled', True)
        self._l2 = SemanticCache(l2_cfg)

        # ---- L3 配置 ----
        l3_cfg = config.get('l3_cache', {})
        self.l3_enabled = l3_cfg.get('enabled', True)
        self.l3_ttl = int(l3_cfg.get('ttl', 21600))
        self.l3_max = int(l3_cfg.get('max_entries', 3000))
        self._l3: Dict[str, L3Entry] = {}
        self._l3_order: deque = deque()  # 用于LRU淘汰

        # ---- 热点检测 ----
        hot_cfg = config.get('hot_question', {})
        self.hot_enabled = hot_cfg.get('enabled', True)
        self.hot_min_frequency = int(hot_cfg.get('min_frequency', 5))
        self.hot_window = int(hot_cfg.get('window_minutes', 1440)) * 60
        self._hot_counter: Dict[str, deque] = defaultdict(deque)
        self._hot_lock = threading.Lock()

        # ---- 统计 ----
        self._stats = {
            'l1_hits': 0, 'l2_hits': 0, 'l3_hits': 0,
            'l1_misses': 0, 'l2_misses': 0, 'l3_misses': 0,
            'total_requests': 0,
            'started_at': time.time(),
        }
        self._stats_lock = threading.Lock()

        # ---- 全局锁 ----
        self._lock = threading.Lock()

        logger.info("CacheManager initialized: L1=%s L2=%s L3=%s hot=%s",
                    self.l1_enabled, self.l2_enabled, self.l3_enabled, self.hot_enabled)

    # ============================================================
    # 公共接口
    # ============================================================

    def get(self, question: str, user_id: int = None,
            tenant_id: int = None) -> Optional[Dict[str, Any]]:
        """
        多级缓存查询（L1→L2→L3）

        Args:
            question: 用户问题
            user_id: 用户ID（用于缓存键隔离）
            tenant_id: 租户ID（用于缓存键隔离）

        Returns:
            如果命中缓存，返回包含 answer/source_documents/model_used 的 dict
            如果未命中，返回 None
        """
        if not question:
            return None

        self._incr('total_requests')
        normalized = self._normalize(question)
        cache_key = self._build_key(normalized, user_id, tenant_id)

        # ---- L1 精确匹配 ----
        if self.l1_enabled:
            result = self._check_l1(cache_key)
            if result is not None:
                return result

        # ---- L2 语义缓存 ----
        if self.l2_enabled:
            result = self._check_l2(normalized)
            if result is not None:
                return result

        # ---- L3 上下文缓存 ----
        if self.l3_enabled:
            result = self._check_l3(cache_key, normalized)
            if result is not None:
                return result

        return None

    def get_l3_context(self, question: str, user_id: int = None,
                       tenant_id: int = None) -> Optional[Tuple[List, Dict]]:
        """
        仅检查 L3 上下文缓存（用于流式场景，命中后只返回检索结果）
        Returns: (retrieved_docs, retrieval_stats) 或 None
        """
        if not self.l3_enabled:
            return None

        normalized = self._normalize(question)
        cache_key = self._build_key(normalized, user_id, tenant_id)

        try:
            entry = self._l3.get(cache_key)
            if entry is None:
                return None
            if entry.is_expired:
                with self._lock:
                    self._l3.pop(cache_key, None)
                return None
            # 更新LRU顺序
            with self._lock:
                if cache_key in self._l3:
                    self._l3_order.remove(cache_key)
                    self._l3_order.append(cache_key)
            self._incr('l3_hits')
            logger.info(f"L3 context cache HIT: '{normalized[:50]}'")
            return entry.retrieved_docs, entry.retrieval_stats
        except Exception as e:
            logger.warning(f"L3 cache check failed (graceful degradation): {e}")
            return None

    def try_cache_hot_question(self, question: str, answer: str,
                                source_documents: List[int],
                                model_used: str,
                                retrieved_docs: list = None,
                                retrieval_stats: dict = None,
                                user_id: int = None,
                                tenant_id: int = None):
        """
        L4 执行完毕后调用，检测是否为高频问题，若是则写入各级缓存

        Args:
            question: 用户问题
            answer: 生成的答案
            source_documents: 源文档ID列表
            model_used: 使用的模型
            retrieved_docs: 检索到的文档列表（用于L3缓存）
            retrieval_stats: 检索统计信息
            user_id: 用户ID
            tenant_id: 租户ID
        """
        if not self.hot_enabled:
            return

        try:
            normalized = self._normalize(question)
            cache_key = self._build_key(normalized, user_id, tenant_id)

            # 记录访问时间戳
            now = time.time()
            with self._hot_lock:
                dq = self._hot_counter[normalized]
                # 清理窗口外的旧时间戳
                while dq and now - dq[0] > self.hot_window:
                    dq.popleft()
                dq.append(now)
                freq = len(dq)

            # 判断是否为热点
            if freq >= self.hot_min_frequency:
                logger.info(f"Hot question detected (freq={freq}): '{normalized[:50]}'")

                # 写入 L1
                if self.l1_enabled:
                    self._set_l1(cache_key, normalized, answer, source_documents, model_used)

                # 写入 L2
                if self.l2_enabled:
                    self._l2.store(normalized, answer, source_documents, model_used)

                # 写入 L3
                if self.l3_enabled and retrieved_docs is not None:
                    self._set_l3(cache_key, normalized, retrieved_docs, retrieval_stats)

                # 从热点计数器移除（避免重复写入）
                with self._hot_lock:
                    self._hot_counter.pop(normalized, None)
        except Exception as e:
            logger.warning(f"Cache hot question failed (graceful degradation): {e}")

    def cache_hot_question_force(self, question: str, answer: str,
                                  source_documents: List[int],
                                  model_used: str,
                                  retrieved_docs: list = None,
                                  retrieval_stats: dict = None,
                                  user_id: int = None,
                                  tenant_id: int = None):
        """
        强制将某问题写入各级缓存（用于缓存预热）
        """
        normalized = self._normalize(question)
        cache_key = self._build_key(normalized, user_id, tenant_id)

        if self.l1_enabled:
            self._set_l1(cache_key, normalized, answer, source_documents, model_used)
        if self.l2_enabled:
            self._l2.store(normalized, answer, source_documents, model_used)
        if self.l3_enabled and retrieved_docs is not None:
            self._set_l3(cache_key, normalized, retrieved_docs, retrieval_stats)

        logger.info(f"Force cached question: '{normalized[:50]}'")

    # ============================================================
    # 统计
    # ============================================================

    def get_stats(self) -> Dict[str, Any]:
        """获取各级缓存命中率统计"""
        with self._stats_lock:
            s = dict(self._stats)

        total_hits = s['l1_hits'] + s['l2_hits'] + s['l3_hits']
        total_checks = total_hits + s['l1_misses']
        s['total_hits'] = total_hits
        s['total_misses'] = s['l1_misses']
        s['overall_hit_rate'] = round(total_hits / max(total_checks, 1) * 100, 2)
        s['l1_hit_rate'] = round(s['l1_hits'] / max(s['l1_hits'] + s['l1_misses'], 1) * 100, 2)
        s['l2_hit_rate'] = round(s['l2_hits'] / max(s['l2_hits'] + s['l2_misses'], 1) * 100, 2)
        s['l3_hit_rate'] = round(s['l3_hits'] / max(s['l3_hits'] + s['l3_misses'], 1) * 100, 2)
        s['l1_size'] = len(self._l1)
        s['l2_size'] = self._l2.size
        s['l3_size'] = len(self._l3)
        s['hot_questions_tracking'] = len(self._hot_counter)
        s['uptime_seconds'] = round(time.time() - s['started_at'], 1)

        return s

    def clear_all(self):
        """清空所有缓存"""
        with self._lock:
            self._l1.clear()
            self._l3.clear()
            self._l1_order.clear()
            self._l3_order.clear()
        self._l2.clear()
        with self._hot_lock:
            self._hot_counter.clear()
        logger.info("All caches cleared")

    # ============================================================
    # L1 内部实现
    # ============================================================

    def _check_l1(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """检查 L1 精确缓存"""
        try:
            entry = self._l1.get(cache_key)
            if entry is None:
                return None
            if entry.is_expired:
                with self._lock:
                    self._l1.pop(cache_key, None)
                self._incr('l1_misses')
                return None
            self._incr('l1_hits')
            # 更新LRU
            with self._lock:
                if cache_key in self._l1:
                    self._l1_order.remove(cache_key)
                    self._l1_order.append(cache_key)
            logger.info(f"L1 exact cache HIT: '{entry.question[:50]}'")
            return {
                'answer': entry.answer,
                'source_documents': entry.source_documents,
                'model_used': entry.model_used,
                'from_cache': 'L1',
            }
        except Exception as e:
            logger.warning(f"L1 cache check failed (graceful degradation): {e}")
            self._incr('l1_misses')
            return None

    def _set_l1(self, cache_key: str, question: str, answer: str,
                source_documents: List[int], model_used: str):
        """写入 L1 精确缓存"""
        try:
            entry = L1Entry(
                question=question, answer=answer,
                source_documents=source_documents, model_used=model_used,
                cached_at=time.time(), ttl=self.l1_ttl
            )
            with self._lock:
                if cache_key in self._l1:
                    self._l1_order.remove(cache_key)
                elif len(self._l1) >= self.l1_max:
                    # LRU淘汰
                    oldest = self._l1_order.popleft()
                    self._l1.pop(oldest, None)
                self._l1[cache_key] = entry
                self._l1_order.append(cache_key)
        except Exception as e:
            logger.warning(f"L1 cache write failed: {e}")

    # ============================================================
    # L2 内部实现（委托给 SemanticCache）
    # ============================================================

    def _check_l2(self, normalized: str) -> Optional[Dict[str, Any]]:
        """检查 L2 语义缓存"""
        try:
            result = self._l2.search(normalized)
            if result is None:
                self._incr('l2_misses')
                return None
            entry, score = result
            self._incr('l2_hits')
            return {
                'answer': entry.answer,
                'source_documents': entry.source_documents,
                'model_used': entry.model_used,
                'from_cache': 'L2',
                'similarity': round(score, 4),
            }
        except Exception as e:
            logger.warning(f"L2 cache check failed (graceful degradation): {e}")
            self._incr('l2_misses')
            return None

    # ============================================================
    # L3 内部实现
    # ============================================================

    def _check_l3(self, cache_key: str, normalized: str) -> Optional[Dict[str, Any]]:
        """检查 L3 上下文缓存（返回"已缓存检索结果，仍需LLM生成"的标记）"""
        try:
            entry = self._l3.get(cache_key)
            if entry is None:
                self._incr('l3_misses')
                return None
            if entry.is_expired:
                with self._lock:
                    self._l3.pop(cache_key, None)
                self._incr('l3_misses')
                return None
            # 更新LRU
            with self._lock:
                if cache_key in self._l3:
                    self._l3_order.remove(cache_key)
                    self._l3_order.append(cache_key)
            self._incr('l3_hits')
            logger.info(f"L3 context cache HIT: '{normalized[:50]}'")
            return {
                'from_cache': 'L3',
                'retrieved_docs': entry.retrieved_docs,
                'retrieval_stats': entry.retrieval_stats,
            }
        except Exception as e:
            logger.warning(f"L3 cache check failed (graceful degradation): {e}")
            self._incr('l3_misses')
            return None

    def _set_l3(self, cache_key: str, question: str,
                retrieved_docs: list, retrieval_stats: dict = None):
        """写入 L3 上下文缓存"""
        try:
            entry = L3Entry(
                question=question,
                retrieved_docs=retrieved_docs,
                retrieval_stats=retrieval_stats or {},
                cached_at=time.time(),
                ttl=self.l3_ttl
            )
            with self._lock:
                if cache_key in self._l3:
                    self._l3_order.remove(cache_key)
                elif len(self._l3) >= self.l3_max:
                    oldest = self._l3_order.popleft()
                    self._l3.pop(oldest, None)
                self._l3[cache_key] = entry
                self._l3_order.append(cache_key)
        except Exception as e:
            logger.warning(f"L3 cache write failed: {e}")

    # ============================================================
    # 工具方法
    # ============================================================

    @staticmethod
    def _normalize(question: str) -> str:
        """标准化问题：去除首尾空白、多余空格、统一标点"""
        q = question.strip()
        # 统一标点（英文逗号句号→中文）
        q = q.replace(',', '，').replace('.', '。').replace('?', '？').replace('!', '！')
        # 压缩多余空格
        import re
        q = re.sub(r'\s+', ' ', q)
        return q

    @staticmethod
    def _build_key(normalized: str, user_id: int = None, tenant_id: int = None) -> str:
        """构建缓存键（含租户隔离）"""
        parts = [normalized]
        if tenant_id is not None:
            parts.append(f"t{tenant_id}")
        if user_id is not None:
            parts.append(f"u{user_id}")
        return '::'.join(parts)

    def _incr(self, key: str):
        """原子递增统计计数器"""
        with self._stats_lock:
            self._stats[key] = self._stats.get(key, 0) + 1