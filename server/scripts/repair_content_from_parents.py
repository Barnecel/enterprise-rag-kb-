# -*- coding: utf-8 -*-
"""
从父窗口映射修复 tb_document.content（无需重新OCR/解析）
适用：历史入库时 content 被 [:800] 截断的文档。
用法（server目录）: ../.venv/bin/python scripts/repair_content_from_parents.py 4
"""

import os
import sys

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

import application.services.rag_service as rs  # noqa: E402
from application.utils.db_utils import execute_query, execute_update  # noqa: E402


def main():
    doc_id = int(sys.argv[1])
    svc = rs.get_rag_service()

    with rs._parent_lock:
        parent_map = dict(rs._parent_map)

    rows = svc.vectorstore._collection.get(
        where={'doc_id': doc_id}, limit=5000,
        include=['metadatas']
    )
    if not rows['ids']:
        print(f"doc#{doc_id} 在向量库中无数据")
        sys.exit(1)

    # 按子块顺序还原父块出现顺序
    order = {}
    for meta in rows['metadatas']:
        pid = meta.get('parent_id')
        idx = meta.get('chunk_index', 0)
        if pid is not None and pid in parent_map:
            if pid not in order or idx < order[pid]:
                order[pid] = idx
    sorted_pids = sorted(order, key=lambda p: order[p])

    text = '\n'.join((parent_map[p] or '').strip() for p in sorted_pids if parent_map.get(p))
    if not text.strip():
        print("父窗口映射中无可还原文本")
        sys.exit(1)

    execute_update("UPDATE tb_document SET content=%s WHERE id=%s", (text, doc_id))
    print(f"doc#{doc_id} content 已修复: {len(sorted_pids)} 个父块, 共 {len(text)} 字符")


if __name__ == '__main__':
    main()
