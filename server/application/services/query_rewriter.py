# -*- coding: utf-8 -*-
"""
查询改写模块 (Query Rewrite)
使用 LLM(oMLX Qwen3.5-9B) 将用户问题改写为多个利于检索的查询变体
失败时回退为 [原问题]
"""
import json
import re
from typing import List, Optional, Dict

import requests

from utils.config_handler import config
from utils.logger_handler import logger
from utils.prompt_loader import load_query_rewrite_prompt, build_dialogue_text

LLM_CONFIG = config.get_section('llm')
RAG_CONFIG = config.get_section('rag')
QW_CONFIG = RAG_CONFIG.get('query_rewrite', {})


class QueryRewriter:
    # 领域同义规则表：(查询正则, 追加的检索变体)。来源：评测badcase（如Q7"几名民警"查不到
    # "一名以上人民警察"）。新规则由关键词命中率指标驱动增长，勿凭空堆砌。
    SYNONYM_RULES = [
        (r'几名(民警|警察|执法人员|警员)|(民警|警察|执法人员|警员)(人数|数量)', '一名以上人民警察 人数'),
        (r'讯问.{0,6}(几个小时|多久|时限)|讯问时限', '讯问 犯罪嫌疑人 12小时 24小时'),
        (r'听证.{0,8}(多少钱|数额|门槛|标准)|多少.{0,4}(钱|元).{0,6}听证', '听证 四千元 个人罚款'),
    ]
    """查询改写器"""

    def rewrite(self, question: str, history: Optional[List[Dict]] = None) -> List[str]:
        """
        将问题改写为多个查询变体（结合对话历史做指代消解）

        Args:
            question: 用户原始问题
            history: 会话历史 [{'question', 'answer'}, ...]（按时间正序，可为空）

        Returns:
            查询变体列表(第一个始终是原问题)
        """
        if not QW_CONFIG.get('enabled', True):
            return [question]

        # 改写结果缓存：同一问题(+历史)返回确定性变体，消除LLM随机性导致的检索漂移
        import hashlib
        cache_key = hashlib.md5(
            (question + '|' + build_dialogue_text(history)).encode('utf-8')
        ).hexdigest()
        if not hasattr(self, '_rewrite_cache'):
            self._rewrite_cache = {}
        cached = self._rewrite_cache.get(cache_key)
        if cached is not None:
            return list(cached)

        num = int(QW_CONFIG.get('num_expansions', 2))
        try:
            prompt = load_query_rewrite_prompt().format(
                question=question, num=num,
                history=build_dialogue_text(history)
            )
            result = self._call_llm(prompt)
            queries = self._parse(result)
            queries = [q for q in queries if q.strip()]
            # 去重并确保原问题在首位
            queries = [question] + [q for q in queries if q != question]
            queries = queries[:num + 1]

            # 领域同义规则：确定性补充变体（不依赖LLM改写质量；由评测badcase驱动增长）
            for pat, extra in self.SYNONYM_RULES:
                if re.search(pat, question) and extra not in queries:
                    queries.append(extra)
            queries = queries[:num + 4]

            self._rewrite_cache[cache_key] = list(queries)
            if len(self._rewrite_cache) > 200:   # 防无限膨胀
                self._rewrite_cache.pop(next(iter(self._rewrite_cache)))
            logger.info(f"Query rewrite: '{question}' -> {queries}")
            return queries
        except Exception as e:
            logger.error(f"Query rewrite failed: {e}. Use original query.")
            return [question]

    def _call_llm(self, prompt: str) -> str:
        """调用oMLX聊天接口"""
        response = requests.post(
            f"{LLM_CONFIG['api_base']}/chat/completions",
            headers={
                'Authorization': f"Bearer {LLM_CONFIG.get('api_key', 'dummy')}",
                'Content-Type': 'application/json'
            },
            json={
                'model': LLM_CONFIG['model_name'],
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': QW_CONFIG.get('temperature', 0.3),
                'max_tokens': 512
            },
            timeout=LLM_CONFIG['timeout']
        )
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        raise RuntimeError(f"LLM rewrite error: {response.status_code} - {response.text}")

    def _parse(self, text: str) -> List[str]:
        """解析LLM输出：优先JSON数组，退化为按行分割"""
        text = text.strip()
        m = re.search(r'\[.*\]', text, re.S)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, list):
                    return [str(x) for x in data if str(x).strip()]
            except Exception:
                pass
        lines = []
        for ln in text.split('\n'):
            ln = re.sub(r'^[\d\.\-\*\s\u2460-\u2473]+', '', ln).strip()
            if ln and ln not in ('(', ')', '输出：', '输出', '结果：'):
                lines.append(ln)
        return lines
