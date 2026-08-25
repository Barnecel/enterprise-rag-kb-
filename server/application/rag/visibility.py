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


class VisibilityMixin:
    """权限元数据双库同步（Chroma metadata + BM25 chunk字典）"""
    def update_doc_visibility(self, doc_id: int, tenant_id: Optional[int] = None,
                              doc_level: Optional[str] = None,
                              min_level: Optional[int] = None) -> Dict[str, int]:
        """
        同步更新文档在两套索引中的权限元数据（Chroma metadata + BM25 chunk字典）。
        场景：管理员修改文档的租户/密级/级别后，已入库向量必须同步，否则权限变更不生效。
        Returns: {'chroma': 更新块数, 'bm25': 更新块数}
        """
        changes = {}
        if tenant_id is not None:
            changes['tenant_id'] = tenant_id
        if doc_level is not None:
            changes['doc_level'] = doc_level
        if min_level is not None:
            changes['min_level'] = min_level
        if not changes:
            return {'chroma': 0, 'bm25': 0}

        updated = {'chroma': 0, 'bm25': 0}

        # 1) Chroma：取现metadata合并新值后回写（update为整体替换，须带全量）
        if self.vectorstore is not None:
            try:
                res = self.vectorstore._collection.get(where={'doc_id': doc_id},
                                                       limit=10000, include=['metadatas'])
                ids, metas = res['ids'], res['metadatas']
                for i in range(0, len(ids), 500):
                    batch_ids = ids[i:i+500]
                    batch_meta = []
                    for m in metas[i:i+500]:
                        m = dict(m or {})
                        m.update(changes)
                        batch_meta.append(m)
                    self.vectorstore._collection.update(ids=batch_ids, metadatas=batch_meta)
                    updated['chroma'] += len(batch_ids)
            except Exception as e:
                logger.error(f"update_doc_visibility chroma failed doc {doc_id}: {e}")

        # 2) BM25：原地改字典（词频不受影响，无需重建索引，仅需落盘）
        with self.bm25._lock:
            for chunk in self.bm25._chunks:
                if chunk.get('doc_id') == doc_id:
                    chunk.update(changes)
                    updated['bm25'] += 1
            try:
                self.bm25._save_to_disk()
            except Exception as e:
                logger.error(f"update_doc_visibility bm25 save failed: {e}")

        logger.info(f"doc {doc_id} 权限元数据已同步: {changes} chroma={updated['chroma']} bm25={updated['bm25']}")
        return updated
