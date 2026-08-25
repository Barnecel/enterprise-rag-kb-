# -*- coding: utf-8 -*-
"""嵌入客户端（P1 Step 1：自 services/rag_service.py 机械搬移，行为等价）"""
import logging
from typing import List

import requests

logger = logging.getLogger("rag_system")


class OMLXEmbeddings:
    """
    自定义嵌入类 - 通过oMLX API调用Qwen3-Embedding-8B-4bit-DWQ模型
    """

    def __init__(self, api_base: str, api_key: str, model_name: str, query_instruction: str = ""):
        self.api_base = api_base
        self.api_key = api_key
        self.model_name = model_name
        # Qwen3-Embedding 官方机制：查询侧加任务指令可显著提升检索质量（文档侧不加）
        self.query_instruction = query_instruction or ""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        批量嵌入文档

        Args:
            texts: 文档列表

        Returns:
            List[List[float]]: 嵌入向量列表
        """
        try:
            response = requests.post(
                f"{self.api_base}/embeddings",
                headers={
                    'Authorization': f"Bearer {self.api_key}",
                    'Content-Type': 'application/json'
                },
                json={
                    'model': self.model_name,
                    'input': texts
                },
                timeout=120
            )
            if response.status_code == 200:
                result = response.json()
                return [item['embedding'] for item in result['data']]
            raise RuntimeError(f"Embedding API error: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise

    def embed_query(self, text: str) -> List[float]:
        """
        嵌入单个查询（按Qwen3-Embedding官方建议，查询侧拼接任务指令）

        Args:
            text: 查询文本

        Returns:
            List[float]: 嵌入向量
        """
        q = f"Instruct: {self.query_instruction}\nQuery: {text}" if self.query_instruction else text
        results = self.embed_documents([q])
        return results[0]

    def __call__(self, texts: List[str]) -> List[List[float]]:
        """使对象可调用"""
        return self.embed_documents(texts)
