# -*- coding: utf-8 -*-
"""
指定文档离线重入库（用于大文件/长OCR任务，绕开HTTP同步超时）
用法（server目录）:
    nohup ../.venv/bin/python -u scripts/reingest_doc.py 4 > data/reingest_4.log 2>&1 &
"""

import os
import sys
import time

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

from application.services.rag_service import get_rag_service  # noqa: E402
from application.utils.db_utils import execute_query, execute_update  # noqa: E402


def main():
    doc_id = int(sys.argv[1])
    row = execute_query(
        "SELECT id, file_path, tenant_id, doc_level, min_level, upload_by "
        "FROM tb_document WHERE id = %s", (doc_id,)
    )
    if not row:
        print(f"文档 {doc_id} 不存在")
        sys.exit(1)
    r = row[0]
    if not os.path.isfile(r['file_path']):
        print(f"文件不存在: {r['file_path']}")
        sys.exit(1)

    execute_update("UPDATE tb_document SET status='processing' WHERE id=%s", (doc_id,))
    svc = get_rag_service()
    # 先清旧向量（防双写：规范化后文本变化，内容哈希去重无法识别）
    try:
        svc.delete_document_from_vectorstore(doc_id)
        print('已清除旧向量')
    except Exception as e:
        print(f'清除旧向量失败(可忽略若本无): {e}')

    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] 开始重入库 doc#{doc_id}: {r['file_path']}")
    try:
        ok = svc.add_document_to_vectorstore(
            r['file_path'], doc_id=doc_id,
            tenant_id=r['tenant_id'], doc_level=r['doc_level'],
            min_level=r['min_level'], owner_id=r['upload_by']
        )
    except Exception as e:
        ok = False
        print(f"异常: {e}")
    dt = time.time() - t0

    execute_update("UPDATE tb_document SET status=%s WHERE id=%s",
                   ('completed' if ok else 'failed', doc_id))
    col = svc.vectorstore._collection
    n = len(col.get(where={'doc_id': doc_id})['ids'])
    print(f"[{time.strftime('%H:%M:%S')}] 完成: {'成功' if ok else '失败'} | 耗时 {dt/60:.1f} 分钟 | Chroma块数 {n}")


if __name__ == '__main__':
    main()
