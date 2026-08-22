# -*- coding: utf-8 -*-
"""
Cross-Encoder 重排模块
使用本地 BAAI/bge-reranker-base 对候选进行精排
- 惰性加载模型，失败自动降级(不阻塞主流程)
- bge-reranker 分数越高越相关，输出降序
"""
import os
import threading
from typing import List, Dict

import numpy as np

# HuggingFace 直连不可用时走镜像(如 hf-mirror.com)，需在导入 sentence_transformers 前设置
if not os.environ.get('HF_ENDPOINT'):
    os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

from utils.config_handler import config
from utils.logger_handler import logger

RAG_CONFIG = config.get_section('rag')
RERANK_CONFIG = RAG_CONFIG.get('rerank', {})
RERANK_MODEL = RERANK_CONFIG.get('model_name', 'BAAI/bge-reranker-base')


def _sigmoid(x):
    return float(1.0 / (1.0 + np.exp(-x)))


class Reranker:
    """Cross-Encoder 重排器"""

    def __init__(self):
        self._model = None
        self._lock = threading.Lock()
        self.available = False

    def _load(self) -> bool:
        """惰性加载模型"""
        if self._model is not None:
            return True
        with self._lock:
            if self._model is not None:
                return True
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(RERANK_MODEL)
                self.available = True
                logger.info(f"Cross-Encoder reranker loaded: {RERANK_MODEL}")
            except Exception as e:
                self.available = False
                logger.error(f"Failed to load reranker model {RERANK_MODEL}: {e}. Rerank disabled.")
        return self.available

    def rerank(self, query: str, candidates: List[Dict], top_n: int) -> List[Dict]:
        """
        对候选列表进行交叉编码重排

        Args:
            query: 原始查询
            candidates: 候选列表(需含 text 字段作为重排文本)
            top_n: 保留数量

        Returns:
            重排后的前 top_n 候选，附加 rerank_score 与 rerank_norm(sigmoid归一化)
            模型不可用时原样返回
        """
        if not self._load() or not candidates:
            return candidates
        try:
            pairs = [(query, (c.get('text') or c.get('content') or '')) for c in candidates]
            scores = self._model.predict(pairs)
            for c, s in zip(candidates, scores):
                c['rerank_score'] = float(s)
                c['rerank_norm'] = _sigmoid(float(s))
            candidates = sorted(candidates, key=lambda x: x['rerank_score'], reverse=True)
            logger.info(f"Rerank completed: {len(candidates)} -> top {min(top_n, len(candidates))}")
            return candidates[:top_n]
        except Exception as e:
            logger.error(f"Rerank failed: {e}. Fallback to fused order.")
            return candidates[:top_n]
