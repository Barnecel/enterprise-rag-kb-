# -*- coding: utf-8 -*-
"""
向量库/BM25 内容级去重（不重新解析、不重新嵌入）
按正文 md5 识别同文档内的重复块，保留首现、删除其余；
BM25 侧整文档移除后用保留块重建（add_chunks 只需 Document 的 page_content+metadata）。
用法（server目录）: ../.venv/bin/python scripts/dedupe_doc_vectors.py 4
"""

import hashlib
import os
import sys

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

from langchain_core.documents import Document  # noqa: E402
from application.services.rag_service import get_rag_service  # noqa: E402


def main():
    doc_id = int(sys.argv[1])
    svc = get_rag_service()
    col = svc.vectorstore._collection

    res = col.get(where={'doc_id': doc_id}, limit=10000,
                  include=['documents', 'metadatas'])
    ids, texts, metas = res['ids'], res['documents'], res['metadatas']
    if not ids:
        print(f"doc#{doc_id} 无向量数据")
        return

    seen, dup_ids = set(), []
    for cid, text in zip(ids, texts):
        key = hashlib.md5((text or '').strip().encode('utf-8')).hexdigest()
        if key in seen:
            dup_ids.append(cid)
        else:
            seen.add(key)

    print(f"doc#{doc_id}: 总块 {len(ids)} | 唯一 {len(seen)} | 重复待删 {len(dup_ids)}")
    if not dup_ids:
        print("无需去重")
        return

    # 1) Chroma 按 ID 删除重复块
    col.delete(ids=dup_ids)
    print(f"Chroma 已删除 {len(dup_ids)} 块")

    # 2) BM25：整文档移除后，用保留块重建（保持与 Chroma 一致）
    keep = [(c, t, m) for c, t, m in zip(ids, texts, metas) if c not in set(dup_ids)]
    svc.bm25.remove_doc(doc_id)
    docs = [Document(page_content=t, metadata=m) for _, t, m in keep]
    svc.bm25.add_chunks(docs)
    print(f"BM25 已重建: {len(docs)} 块")

    # 3) 校验
    left = len(col.get(where={'doc_id': doc_id}, limit=10000)['ids'])
    bm_left = sum(1 for c in svc.bm25._chunks if c.get('doc_id') == doc_id)
    print(f"校验 → Chroma: {left} | BM25: {bm_left} | {'一致 ✓' if left == bm_left == len(seen) else '不一致 ✗'}")


if __name__ == '__main__':
    main()
