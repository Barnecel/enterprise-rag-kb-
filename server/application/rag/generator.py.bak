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


from utils.prompt_loader import load_rag_prompt, build_dialogue_text

LLM_CONFIG = config.get_section('llm')


class GenerationMixin:
    """答案生成：提示词构建 + LLM流式/非流式调用"""
    def generate_answer(self, question: str, context_documents: List[Dict], history: Optional[List[Dict]] = None) -> str:
        """
        使用LLM生成回答（上下文为父窗口文本）

        Args:
            question: 用户问题
            context_documents: 上下文文档列表
            history: 会话历史(供LLM理解指代与语境)

        Returns:
            str: 生成的回答
        """
        try:
            context = "\n\n".join([
                f"文档{i+1}:\n{doc.get('content', '')}"
                for i, doc in enumerate(context_documents)
            ])

            prompt = load_rag_prompt().format(
                context=context, question=question,
                history=build_dialogue_text(history)
            )
            return self._call_llm(prompt)
        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            return self._mock_generate_answer(question, context_documents)

    def _call_llm(self, prompt: str) -> str:
        """
        调用LLM大模型 (oMLX Qwen3.5-9B)

        Args:
            prompt: 提示词

        Returns:
            str: 模型生成的回复
        """
        try:
            response = requests.post(
                f"{LLM_CONFIG['api_base']}/chat/completions",
                headers={
                    'Authorization': f"Bearer {LLM_CONFIG.get('api_key', 'dummy')}",
                    'Content-Type': 'application/json'
                },
                json={
                    'model': LLM_CONFIG['model_name'],
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': LLM_CONFIG['temperature'],
                    'max_tokens': LLM_CONFIG['max_tokens']
                },
                timeout=LLM_CONFIG['timeout']
            )
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                return f"API error: {response.status_code} - {response.text}"
        except Exception as e:
            return f"LLM调用失败: {str(e)}"

    def _call_llm_stream(self, prompt: str) -> Iterator[str]:
        """
        流式调用LLM(oMLX)，逐token产出文本

        Args:
            prompt: 完整提示词

        Yields:
            文本增量(token)
        """
        try:
            response = requests.post(
                f"{LLM_CONFIG['api_base']}/chat/completions",
                headers={
                    'Authorization': f"Bearer {LLM_CONFIG.get('api_key', 'dummy')}",
                    'Content-Type': 'application/json'
                },
                json={
                    'model': LLM_CONFIG['model_name'],
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': LLM_CONFIG['temperature'],
                    'max_tokens': LLM_CONFIG['max_tokens'],
                    'stream': True
                },
                timeout=LLM_CONFIG['timeout'],
                stream=True
            )
            if response.status_code != 200:
                yield f"API error: {response.status_code} - {response.text}"
                return
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode('utf-8', errors='ignore').strip()
                if not line.startswith('data:'):
                    continue
                data = line[len('data:'):].strip()
                if data == '[DONE]':
                    break
                try:
                    chunk = json.loads(data)
                    choices = chunk.get('choices') or []
                    if choices:
                        delta = (choices[0].get('delta') or {}).get('content')
                        if delta:
                            yield delta
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            yield f"LLM调用失败: {str(e)}"

    def answer_question_stream(
        self,
        question: str,
        user_id: int,
        tenant_id: Optional[int] = None,
        clearance_level: Optional[int] = None,
        acl_doc_ids: Optional[List[int]] = None,
        history: Optional[List[Dict]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        流式RAG问答入口
        事件序列: retrieving(检索中) -> thinking(检索完成,LLM生成中) -> token*(增量) -> done(结束)
        命中L1/L2全量缓存时直接输出缓存答案；命中L3时跳过检索仅重新生成。

        Args:
            question: 用户问题
            user_id: 用户ID
            tenant_id: 租户ID(admin传None)
            clearance_level: 用户密级
            acl_doc_ids: ACL授权文档ID列表
            history: 会话历史(指代消解与语境理解)
        """
        top_k = int(RAG_CONFIG['top_k'])

        # 0. 全量答案缓存(L1精确/L2语义)
        try:
            cached_full = self.cache_manager.get(question, user_id, tenant_id)
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")
            cached_full = None
        if cached_full and cached_full.get('answer'):
            yield {'type': 'status', 'phase': 'thinking', 'retrieved_docs': [],
                   'stats': {'cache': cached_full.get('from_cache')}, 'from_cache': True}
            yield {'type': 'token', 'delta': cached_full['answer']}
            yield {'type': 'done', 'source_documents': cached_full.get('source_documents') or [],
                   'stats': {'cache': cached_full.get('from_cache')},
                   'model_used': cached_full.get('model_used') or LLM_CONFIG['model_name']}
            return

        # 1. 检索阶段(L3上下文缓存命中则跳过，查询改写/双路召回/重排耗时较长)
        yield {'type': 'status', 'phase': 'retrieving'}
        stats: Dict[str, Any] = {}
        l3 = self.cache_manager.get_l3_context(question, user_id, tenant_id)
        if l3 is not None:
            retrieved_docs, stats = l3
            stats['cache'] = 'L3'
        else:
            retrieved_docs, stats = self._hybrid_retrieve(
                question, tenant_id, top_k, user_id, clearance_level, acl_doc_ids, history
            )
        yield {'type': 'status', 'phase': 'thinking', 'retrieved_docs': retrieved_docs, 'stats': stats}

        # 2. 生成阶段(流式输出)
        answer_parts: List[str] = []
        try:
            context = "\n\n".join([
                f"文档{i+1}:\n{doc.get('content', '')}"
                for i, doc in enumerate(retrieved_docs)
            ])
            prompt = load_rag_prompt().format(
                context=context, question=question,
                history=build_dialogue_text(history)
            )
            for delta in self._call_llm_stream(prompt):
                answer_parts.append(delta)
                yield {'type': 'token', 'delta': delta}
        except Exception as e:
            logger.error(f"Stream generate failed: {e}")
            yield {'type': 'token', 'delta': f"（生成回答失败：{e}）"}

        # 3. 结束事件
        source_doc_ids = list(dict.fromkeys([doc['id'] for doc in retrieved_docs if doc.get('id')]))
        yield {
            'type': 'done',
            'source_documents': source_doc_ids,
            'stats': stats,
            'model_used': LLM_CONFIG['model_name']
        }

        # 4. 热点问题写入各级缓存
        try:
            self.cache_manager.try_cache_hot_question(
                question, ''.join(answer_parts), source_doc_ids, LLM_CONFIG['model_name'],
                retrieved_docs=retrieved_docs, retrieval_stats=stats,
                user_id=user_id, tenant_id=tenant_id
            )
        except Exception as e:
            logger.warning(f"Cache hot question failed: {e}")

    def _mock_generate_answer(self, question: str, context_documents: List[Dict]) -> str:
        """
        模拟回答生成

        Args:
            question: 用户问题
            context_documents: 上下文文档

        Returns:
            str: 模拟回答
        """
        if not context_documents:
            return "抱歉，知识库中暂时没有找到相关信息。"

        context_text = "\n".join([doc.get('content', '')[:300] for doc in context_documents])

        return f"""根据检索到的相关文档，我为您找到以下信息：

{context_text[:500]}...

如果您需要了解更多详情，请提出更具体的问题。"""

    def answer_question(
        self,
        question: str,
        user_id: int,
        tenant_id: Optional[int] = None,
        clearance_level: Optional[int] = None,
        acl_doc_ids: Optional[List[int]] = None,
        history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        RAG问答的入口方法
        完整流程：缓存检查 -> 查询改写 -> 混合检索 -> 重排 -> 动态TopK -> 父窗口作答

        Args:
            question: 用户问题
            user_id: 用户ID
            tenant_id: 所属租户ID
            clearance_level: 用户密级
            acl_doc_ids: 用户被显式授权的文档ID列表
            history: 会话历史(指代消解与语境理解)

        Returns:
            Dict: 包含回答、源文档、token消耗等
        """
        top_k = int(RAG_CONFIG['top_k'])

        # 0. 缓存检查(L1精确/L2语义返回完整答案；L3返回检索结果仅省去检索)
        try:
            cached = self.cache_manager.get(question, user_id, tenant_id)
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")
            cached = None

        if cached and cached.get('answer'):
            answer = cached['answer']
            source_doc_ids = cached.get('source_documents') or []
            return {
                'answer': answer,
                'source_documents': source_doc_ids,
                'retrieved_docs': [],
                'model_used': cached.get('model_used') or LLM_CONFIG['model_name'],
                'token_count': len(question) + len(answer),
                'topk_used': 0,
                'retrieval_stats': {'cache': cached.get('from_cache')},
                'from_cache': cached.get('from_cache')
            }

        # 1. 混合检索（L3命中则复用检索结果）
        l3 = self.cache_manager.get_l3_context(question, user_id, tenant_id)
        if l3 is not None:
            retrieved_docs, stats = l3
            stats['cache'] = 'L3'
        else:
            retrieved_docs, stats = self._hybrid_retrieve(
                question, tenant_id, top_k, user_id, clearance_level, acl_doc_ids, history
            )

        # 2. 生成回答
        answer = self.generate_answer(question, retrieved_docs, history)

        # 3. 提取源文档ID(修复历史恒为空的问题)
        source_doc_ids = list(dict.fromkeys([doc['id'] for doc in retrieved_docs if doc.get('id')]))

        # 4. 热点问题写入各级缓存
        try:
            self.cache_manager.try_cache_hot_question(
                question, answer, source_doc_ids, LLM_CONFIG['model_name'],
                retrieved_docs=retrieved_docs, retrieval_stats=stats,
                user_id=user_id, tenant_id=tenant_id
            )
        except Exception as e:
            logger.warning(f"Cache hot question failed: {e}")

        return {
            'answer': answer,
            'source_documents': source_doc_ids,
            'retrieved_docs': retrieved_docs,
            'model_used': LLM_CONFIG['model_name'],
            'token_count': len(question) + len(answer),  # 粗略估算
            'topk_used': stats.get('topk_used'),
            'retrieval_stats': stats
        }

    # ============================================================
    # 向量库重建
    # ============================================================
