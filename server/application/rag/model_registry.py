# -*- coding: utf-8 -*-
"""P1重构：自 services/rag_service.py 机械搬移（行为等价，Mixin承载）"""
import json
import os
import re
import time
import shutil
import logging
from typing import List, Dict, Any, Iterator, Optional

import requests

from utils.logger_handler import logger
from utils.config_handler import config
from application.utils.db_utils import execute_query, execute_update, execute_insert
from application.rag import state
from application.rag.state import _parent_map, _parent_lock, _save_parent_map, DATA_DIR

RAG_CONFIG = config.get_section('rag')
HYBRID_CONFIG = RAG_CONFIG.get('hybrid', {})
RERANK_CONFIG = RAG_CONFIG.get('rerank', {})
DYNAMIC_CONFIG = RAG_CONFIG.get('dynamic_topk', {})
ENUM_CONFIG = RAG_CONFIG.get('enumeration', {})


from application.rag.embeddings import OMLXEmbeddings

LLM_CONFIG = config.get_section('llm')
EMBEDDING_CONFIG = config.get_section('embedding')


class RegistryMixin:
    """模型热插拔与运行时注册（LLM/EMBEDDING配置dict与service共享同一对象）"""
    def apply_active_models(self):
        """读取DB中启用的模型配置，原地覆盖运行时字典（LLM立即生效；嵌入仅在维度兼容时热切）"""
        from application.utils.db_utils import execute_query
        try:
            rows = execute_query(
                "SELECT model_type, api_base, api_key, model_name, pending_rebuild "
                "FROM tb_model_config WHERE is_active = 1"
            )
        except Exception as e:
            logger.warning(f"apply_active_models: 读取模型配置失败(回退YAML): {e}")
            return {'llm': False, 'embedding': False}

        applied = {'llm': False, 'embedding': False}
        for r in rows:
            if r['model_type'] == 'llm':
                LLM_CONFIG['api_base'] = r['api_base']
                LLM_CONFIG['api_key'] = r.get('api_key') or ''
                LLM_CONFIG['model_name'] = r['model_name']
                applied['llm'] = True
                logger.info(f"LLM 已切换为DB配置: {r['model_name']} @ {r['api_base']}")
            elif r['model_type'] == 'embedding':
                EMBEDDING_CONFIG['api_base'] = r['api_base']
                EMBEDDING_CONFIG['api_key'] = r.get('api_key') or ''
                EMBEDDING_CONFIG['model_name'] = r['model_name']
                self._initialize_embeddings()
                self._initialize_vectorstore()
                applied['embedding'] = True
                logger.info(f"Embedding 已切换为DB配置: {r['model_name']} @ {r['api_base']}")
        return applied

    def collection_dim(self) -> Optional[int]:
        """当前Chroma集合的向量维度（空库返回None）"""
        if self.vectorstore is None:
            return None
        try:
            res = self.vectorstore._collection.get(limit=1, include=['embeddings'])
            embs = res.get('embeddings')   # chromadb 1.x 返回 numpy.ndarray
            if embs is None or len(embs) == 0:
                return None
            return int(len(embs[0]))
        except Exception:
            return None

    def probe_embedding_dim(self, api_base: str, api_key: str, model_name: str) -> int:
        """探测指定嵌入配置的输出维度（临时实例，不影响运行时）"""
        tmp = OMLXEmbeddings(api_base=api_base, api_key=api_key or '', model_name=model_name)
        vec = tmp.embed_documents(['维度探测'])
        return len(vec[0])

    def hot_swap_llm(self, cfg: dict):
        """切换LLM并清空答案相关缓存（旧模型的缓存答案不再适用）"""
        LLM_CONFIG['api_base'] = cfg['api_base']
        LLM_CONFIG['api_key'] = cfg.get('api_key') or ''
        LLM_CONFIG['model_name'] = cfg['model_name']
        try:
            self.cache_manager.clear_all()
        except Exception:
            pass
        logger.info(f"LLM 热切换完成: {cfg['model_name']} @ {cfg['api_base']}")

    def hot_swap_embedding(self, cfg: dict) -> dict:
        """
        切换嵌入模型。维度不兼容时不热切，要求先重建向量库。
        Returns: {swapped, rebuild_required, old_dim, new_dim}
        """
        new_dim = self.probe_embedding_dim(cfg['api_base'], cfg.get('api_key'), cfg['model_name'])
        old_dim = self.collection_dim()

        if old_dim is not None and old_dim != new_dim:
            logger.warning(f"嵌入维度不兼容({old_dim}→{new_dim})，需重建向量库后生效")
            return {'swapped': False, 'rebuild_required': True,
                    'old_dim': old_dim, 'new_dim': new_dim}

        EMBEDDING_CONFIG['api_base'] = cfg['api_base']
        EMBEDDING_CONFIG['api_key'] = cfg.get('api_key') or ''
        EMBEDDING_CONFIG['model_name'] = cfg['model_name']
        self._initialize_embeddings()
        self._initialize_vectorstore()
        try:
            self.cache_manager.clear_all()
        except Exception:
            pass
        return {'swapped': True, 'rebuild_required': False,
                'old_dim': old_dim, 'new_dim': new_dim}
