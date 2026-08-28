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
from application.rag.state import (_parent_map, _parent_lock, _save_parent_map, DATA_DIR,
    LANCHAIN_AVAILABLE)

RAG_CONFIG = config.get_section('rag')
HYBRID_CONFIG = RAG_CONFIG.get('hybrid', {})
RERANK_CONFIG = RAG_CONFIG.get('rerank', {})
DYNAMIC_CONFIG = RAG_CONFIG.get('dynamic_topk', {})
ENUM_CONFIG = RAG_CONFIG.get('enumeration', {})


from application.services.fusion import reciprocal_rank_fusion


class RetrievalMixin:
    """检索管线：双路召回 → RRF融合 → 重排 → 动态TopK → 父窗口扩展"""
    def _dense_search(
        self,
        query: str,
        tenant_id: Optional[int],
        user_id: Optional[int] = None,
        clearance_level: Optional[int] = None,
        acl_doc_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """稠密检索(Embedding + Chroma)，带租户/密级/ACL过滤"""
        if not LANCHAIN_AVAILABLE or self.vectorstore is None:
            return []

        try:
            dense_top_k = int(HYBRID_CONFIG.get('dense_top_k', 20))
            filter_dict = None
            if tenant_id is not None:
                # 可见性：同部门+公开+密级达标 OR 所有者 OR 显式授权(覆盖部门/密级)
                or_clauses = [
                    {"$and": [
                        {"tenant_id": {"$eq": tenant_id}},
                        {"doc_level": {"$eq": "public"}},
                        {"min_level": {"$lte": clearance_level or 1}}
                    ]},
                    {"owner_id": {"$eq": user_id}},
                ]
                if acl_doc_ids:
                    or_clauses.append({"doc_id": {"$in": acl_doc_ids}})
                filter_dict = {"$or": or_clauses}

            results = self.vectorstore.similarity_search_with_score(
                query,
                k=dense_top_k,
                filter=filter_dict
            )

            candidates = []
            for doc, score in results:
                # Chroma返回L2距离，超过阈值视为不相关
                if score > RAG_CONFIG['score_threshold']:
                    continue
                meta = doc.metadata
                candidates.append({
                    'doc_id': meta.get('doc_id'),
                    'parent_id': meta.get('parent_id'),
                    'source': meta.get('source', ''),
                    'tenant_id': meta.get('tenant_id', 1),
                    'chunk_index': meta.get('chunk_index', 0),
                    'page': meta.get('page'),
                    'text': doc.page_content,
                    'score': float(score),        # L2距离(越小越相关)
                    'dense_score': float(score),
                })
            return candidates
        except Exception as e:
            logger.error(f"Dense search failed: {e}")
            return []

    def _hybrid_retrieve(
        self,
        query: str,
        tenant_id: Optional[int],
        requested_top_k: int,
        user_id: Optional[int] = None,
        clearance_level: Optional[int] = None,
        acl_doc_ids: Optional[List[int]] = None,
        history: Optional[List[Dict]] = None
    ) -> tuple:
        """
        完整混合检索管线
        查询改写 -> 双路召回(BM25+稠密) -> RRF融合 -> Cross-Encoder重排 -> 动态TopK -> 父窗口扩展

        Args:
            query: 查询文本
            tenant_id: 租户过滤(admin传None可见全部)
            requested_top_k: 请求的返回数量
            user_id: 查询用户ID(所有者恒可见)
            clearance_level: 用户密级
            acl_doc_ids: 用户被显式授权的文档ID列表
            history: 会话历史(用于查询改写时指代消解)

        Returns:
            (docs, stats)
        """
        stats = {'rewritten_queries': [], 'dense_count': 0, 'sparse_count': 0, 'topk_used': requested_top_k}

        # 1. 查询改写（结合历史消解指代）
        rewritten = self.query_rewriter.rewrite(query, history=history)
        stats['rewritten_queries'] = rewritten

        # 2. 对每个改写变体执行双路召回+RRF融合
        variant_candidates = []
        hybrid_enabled = HYBRID_CONFIG.get('enabled', True)
        dense_top_k = int(HYBRID_CONFIG.get('dense_top_k', 20))
        bm25_top_k = int(HYBRID_CONFIG.get('bm25_top_k', 20))
        rrf_k = int(HYBRID_CONFIG.get('rrf_k', 60))
        weights = HYBRID_CONFIG.get('weights', {'dense': 1.0, 'sparse': 1.0})

        for q in rewritten:
            dense = self._dense_search(q, tenant_id, user_id, clearance_level, acl_doc_ids) if hybrid_enabled else []
            sparse = self.bm25.search(q, bm25_top_k, tenant_id, user_id, clearance_level, acl_doc_ids) if hybrid_enabled else []
            stats['dense_count'] += len(dense)
            stats['sparse_count'] += len(sparse)

            if not dense and not sparse:
                continue
            fused = reciprocal_rank_fusion(dense, sparse, k=rrf_k, weights=weights)
            variant_candidates.append(fused)

        # 3. 合并多个改写变体的候选
        merged = self._merge_variants(variant_candidates)
        stats['fused_count'] = len(merged)

        if not merged:
            return [], stats

        # 4. Cross-Encoder重排 (rerank内部惰性加载，模型不可用自动降级为融合排序)
        fusion_top_n = int(HYBRID_CONFIG.get('fusion_top_n', 15))
        rerank_top_n = int(RERANK_CONFIG.get('top_n', 8))
        if RERANK_CONFIG.get('enabled', True):
            merged = self.reranker.rerank(query, merged[:fusion_top_n], rerank_top_n)
            stats['rerank_count'] = len(merged)
            # 重排置信度兜底：低于阈值的块不送LLM，防无关块靠词面overlap混入
            min_norm = float(RERANK_CONFIG.get('min_norm', 0.0))
            if min_norm > 0 and merged:
                pre_merged = merged
                merged = [c for c in merged if (c.get('rerank_norm') or 0) >= min_norm]
                if not merged:
                    merged = pre_merged[:1]  # 全部低于阈值则保留最优，避免空上下文
        else:
            merged = merged[:rerank_top_n]
            stats['rerank_count'] = len(merged)

        # 5. 动态TopK
        norm_scores = [self._norm_score(c) for c in merged]
        topk = self._select_dynamic_topk(norm_scores, requested_top_k)
        stats['topk_used'] = topk
        top = merged[:topk]

        # 6. 父窗口扩展
        docs = [self._to_output_doc(c) for c in top]

        # 7. 枚举/清单类查询：标题级匹配补充（根治"有哪些文档"类问题）
        if ENUM_CONFIG.get('enabled', True):
            try:
                pseudo = self._enumeration_docs(query, requested_top_k, tenant_id, user_id, clearance_level, acl_doc_ids)
            except Exception as e:
                logger.warning(f"Enumeration docs failed: {e}")
                pseudo = []
            if pseudo:
                pseudo_ids = {p.get('id') for p in pseudo}
                docs = pseudo + [d for d in docs if d.get('id') not in pseudo_ids]
                stats['enum_docs'] = len(pseudo)
                logger.info(f"Enumeration query matched {len(pseudo)} docs by title: '{query}'")

        # 8. 补全文档标题（供前端参考文档展示）
        try:
            doc_ids = [d.get('id') for d in docs if d.get('id')]
            if doc_ids:
                from application.utils.db_utils import execute_query
                placeholders = ','.join(['%s'] * len(doc_ids))
                rows = execute_query(
                    f"SELECT id, title FROM tb_document WHERE id IN ({placeholders})", doc_ids
                )
                title_map = {r['id']: r['title'] for r in rows}
                for d in docs:
                    d['title'] = title_map.get(d.get('id'))
        except Exception as e:
            logger.warning(f"Enrich doc titles failed: {e}")

        return docs, stats

    def _enumeration_docs(
        self,
        query: str,
        requested_top_k: int,
        tenant_id: Optional[int],
        user_id: Optional[int],
        clearance_level: Optional[int],
        acl_doc_ids: Optional[List[int]]
    ) -> List[Dict[str, Any]]:
        """
        枚举/清单类查询的标题级匹配（"技术文档有哪些" / "列出所有文档"）
        检测到枚举意图后，按标题 LIKE 检索用户可见文档，作为高优先级候选返回。
        无标题匹配时回退为列出全部可见文档，让LLM如实作答而非编造。
        """
        import re
        intent = re.search(r'有哪些|有什么|列出|列举|清单|全部|所有|多少(个|份|类|种|篇)|都有什么|包含哪些', query)
        if not intent:
            return []
        # 对比/差异类问题含"有什么"(如"有什么区别")，不是枚举意图，避免误注入文档卡片
        if re.search(r'区别|不同|对比|差异|多久|多少天|多少年', query):
            return []

        # 提取内容关键词（去掉意图词与通用词）
        keyword = re.sub(
            r'有哪些|有什么|列出|列举|清单|请|帮我|帮|都|什么|多少(个|份|类|种|篇)'
            r'|文档|资料|文件|知识库|请问|关于|内容|类型|标题',
            '', query
        ).strip()
        keyword = keyword[:20]
        limit = max(int(ENUM_CONFIG.get('max_docs', 15)), requested_top_k or 5)

        from application.utils.db_utils import execute_query
        if tenant_id is None:
            sql = ("SELECT id, title, content, tenant_id, doc_level, min_level "
                   "FROM tb_document WHERE status = 'completed'")
            params: tuple = ()
        else:
            sql = ("SELECT id, title, content, tenant_id, doc_level, min_level "
                   "FROM tb_document "
                   "WHERE status = 'completed' "
                   "AND ((tenant_id = %s AND doc_level = 'public' AND min_level <= %s) "
                   "OR upload_by = %s "
                   "OR id IN (SELECT document_id FROM tb_document_acl WHERE user_id = %s))")
            params = (tenant_id, clearance_level or 1, user_id, user_id)

        base_params = params
        if keyword:
            rows = execute_query(sql + " AND title LIKE %s ORDER BY id DESC LIMIT %s",
                                 params + (f'%{keyword}%', limit))
        else:
            rows = execute_query(sql + " ORDER BY id DESC LIMIT %s", params + (limit,))

        if not rows:
            # 强枚举意图(如"文档有哪些"/"列出所有资料")且标题无匹配 → 兜底列出全部，让LLM如实作答
            # 弱意图(仅命中"有哪些/有什么"但无文档上下文) → 返回空，避免伪卡片挤掉真实检索结果
            strong = re.search(
                r'(文档|资料|文件|知识库).{0,6}(有哪些|有什么|清单|列出)|列出.{0,8}(所有|全部)|(所有|全部).{0,4}(文档|资料|文件)',
                query)
            if strong:
                rows = execute_query(sql + " ORDER BY id DESC LIMIT %s", base_params + (limit,))
            else:
                return []

        pseudo = []
        for i, r in enumerate(rows):
            snippet = (r.get('content') or '').strip().replace('\n', ' ')[:120]
            text = f"【文档标题】{r['title']}。{snippet}"
            pseudo.append({
                'id': r['id'],
                'doc_id': r['id'],
                'parent_id': None,
                'source': f"document_{r['id']}",
                'tenant_id': r.get('tenant_id'),
                'content': text,
                'child_content': text,
                'score': 1e9 - i,          # 高优先级排在最前
                'rerank_score': 999.0,
                'rerank_norm': 1.0,
            })
        return pseudo

    def _merge_variants(self, variant_candidates: List[List[Dict]]) -> List[Dict]:
        """
        合并多个查询变体的候选，同一块(去重键)RRF分数累加
        """
        merged: Dict[tuple, Dict] = {}

        for variants in variant_candidates:
            for item in variants:
                key = (item.get('doc_id'), item.get('parent_id'), item.get('chunk_index'))
                if key not in merged:
                    merged[key] = dict(item)
                else:
                    merged[key]['score'] = merged[key].get('score', 0) + item.get('score', 0)

        return sorted(merged.values(), key=lambda x: x['score'], reverse=True)

    def _norm_score(self, candidate: Dict) -> float:
        """
        归一化相似度分数(0~1)
        优先使用重排后的 sigmoid 分数，否则用稠密L2距离换算
        """
        if candidate.get('rerank_norm') is not None:
            return float(candidate['rerank_norm'])
        dense = candidate.get('dense_score')
        if dense is not None:
            return 1.0 / (1.0 + float(dense))
        return 0.5  # 仅稀疏召回的块使用中性值

    def _select_dynamic_topk(self, scores: List[float], requested_top_k: int) -> int:
        """
        动态TopK调度 (特性3)
        基于分数分布决定送入LLM的块数量：
        - 峰值高且骤降 -> 单一强答案 -> 用最少块
        - 均值高(多块相关) -> 用最多块
        - 全部弱相关 -> 用最少块
        - 否则 -> 基准块数
        """
        if not DYNAMIC_CONFIG.get('enabled', True) or not scores:
            return requested_top_k or DYNAMIC_CONFIG.get('base_topk', 5)

        min_topk = int(DYNAMIC_CONFIG.get('min_topk', 3))
        max_topk = int(DYNAMIC_CONFIG.get('max_topk', 8))
        base_topk = int(DYNAMIC_CONFIG.get('base_topk', 5))
        high_threshold = float(DYNAMIC_CONFIG.get('high_threshold', 0.85))
        low_threshold = float(DYNAMIC_CONFIG.get('low_threshold', 0.5))

        sorted_scores = sorted(scores, reverse=True)
        top = sorted_scores[0]
        drop = (sorted_scores[0] - sorted_scores[1]) if len(sorted_scores) > 1 else 1.0
        mean = sum(sorted_scores) / len(sorted_scores)

        if top >= high_threshold and drop >= 0.15:
            k = min_topk                       # 单一强答案
        elif mean >= high_threshold:
            k = max_topk                       # 高度相关且集中
        elif top <= low_threshold:
            k = min_topk                       # 全部弱相关
        else:
            k = base_topk

        # 钳制范围并尊重调用方上限
        k = max(min_topk, min(k, max_topk))
        if requested_top_k:
            k = min(k, requested_top_k)
        return k

    def _to_output_doc(self, candidate: Dict) -> Dict[str, Any]:
        """将候选块转换为输出文档(父窗口作为作答上下文)"""
        child_text = candidate.get('text', '')
        parent_text = _parent_map.get(candidate.get('parent_id'), child_text)

        return {
            'id': candidate.get('doc_id'),
            'doc_id': candidate.get('doc_id'),
            'parent_id': candidate.get('parent_id'),
            'source': candidate.get('source'),
            'tenant_id': candidate.get('tenant_id'),
            'page': candidate.get('page'),
            'content': parent_text,            # 父窗口(作答上下文)
            'child_content': child_text,       # 子块(检索原文)
            'score': candidate.get('score'),   # RRF融合分
            'rerank_score': candidate.get('rerank_score'),
            'rerank_norm': candidate.get('rerank_norm'),
        }

    def retrieve_documents(
        self,
        query: str,
        top_k: int = 5,
        tenant_id: Optional[int] = None,
        user_id: Optional[int] = None,
        clearance_level: Optional[int] = None,
        acl_doc_ids: Optional[List[int]] = None,
        history: Optional[List[Dict]] = None
    ) -> List[Dict[str, Any]]:
        """
        检索与查询最相关的文档（完整混合检索管线）

        Args:
            query: 查询文本
            top_k: 返回的文档数量
            tenant_id: 租户过滤(admin传None可见全部)
            user_id: 查询用户ID(所有者恒可见)
            clearance_level: 用户密级
            acl_doc_ids: 用户被显式授权的文档ID列表
            history: 会话历史(用于查询改写时指代消解)

        Returns:
            List[Dict]: 相关文档列表
        """
        if not LANCHAIN_AVAILABLE:
            return self._mock_retrieve(query, top_k)

        docs, _ = self._hybrid_retrieve(query, tenant_id, top_k, user_id, clearance_level, acl_doc_ids, history)
        return docs

    def _mock_retrieve(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """
        模拟检索（当LangChain不可用时）

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            List[Dict]: 模拟的文档列表
        """
        from application.utils.db_utils import execute_query

        sql = """
            SELECT id, title, content FROM tb_document
            WHERE status = 'completed'
            LIMIT 10
        """
        docs = execute_query(sql)

        results = []
        for doc in docs[:top_k]:
            content = doc['content'] or ''
            score = 0.5 if query.lower() in content.lower() else 0.3
            results.append({
                'id': doc['id'],
                'title': doc['title'],
                'content': content[:500],
                'score': score
            })

        return results

    # ============================================================
    # 答案生成
    # ============================================================
