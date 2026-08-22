# -*- coding: utf-8 -*-
"""
演示语料播种脚本
将 scripts/sample_docs/ 下的样例文档导入知识库（租户1/公司制度分类）。
- 同名文档已存在：先彻底删除旧版（向量/BM25/文件/DB）再导入新版
- 相同hash已存在：跳过（幂等）
用法（server目录）:
    ../.venv/bin/python scripts/seed_sample_docs.py
"""

import hashlib
import os
import shutil
import sys
import uuid

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

from application.services.rag_service import get_rag_service  # noqa: E402
from application.utils.db_utils import execute_insert, execute_query, execute_update  # noqa: E402

SAMPLE_DIR = os.path.join(SERVER_DIR, 'scripts', 'sample_docs')
TENANT_ID = 1
CATEGORY_ID = 1   # 公司制度
UPLOAD_BY = 1     # admin


def full_delete(doc_id):
    """彻底删除一个文档的所有痕迹"""
    svc = get_rag_service()
    svc.delete_document_from_vectorstore(doc_id)
    execute_update("DELETE FROM tb_document_acl WHERE document_id = %s", (doc_id,))
    rows = execute_query("SELECT file_path FROM tb_document WHERE id = %s", (doc_id,))
    if rows and rows[0].get('file_path') and os.path.isfile(rows[0]['file_path']):
        os.remove(rows[0]['file_path'])
    execute_update("DELETE FROM tb_document WHERE id = %s", (doc_id,))


def seed_one(svc, path):
    name = os.path.basename(path)
    title = os.path.splitext(name)[0]
    file_hash = hashlib.md5(open(path, 'rb').read()).hexdigest()

    same_hash = execute_query("SELECT id FROM tb_document WHERE file_hash = %s", (file_hash,))
    if same_hash:
        print(f"  [跳过] {title}: 内容未变化 (#{same_hash[0]['id']})")
        return False
    old = execute_query("SELECT id FROM tb_document WHERE title = %s", (title,))
    for r in old:
        print(f"  [替换] 删除旧版 #{r['id']} {title}")
        full_delete(r['id'])

    ext = os.path.splitext(name)[1].lstrip('.').lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    dest = os.path.join(DOCUMENT_UPLOAD_DIR, unique_name)
    shutil.copyfile(path, dest)

    doc_id = execute_insert(
        "INSERT INTO tb_document (title, file_path, file_name, file_type, file_size, "
        "file_hash, category_id, tenant_id, status, upload_by, doc_level, min_level) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'processing', %s, 'public', 1)",
        (title, dest, name, ext, os.path.getsize(dest), file_hash,
         CATEGORY_ID, TENANT_ID, UPLOAD_BY)
    )
    ok = svc.add_document_to_vectorstore(
        dest, doc_id=doc_id, tenant_id=TENANT_ID,
        doc_level='public', min_level=1, owner_id=UPLOAD_BY
    )
    execute_update("UPDATE tb_document SET status = %s WHERE id = %s",
                   ('completed' if ok else 'failed', doc_id))
    print(f"  [完成] #{doc_id} {title} -> {'成功' if ok else '失败'}")
    return ok


DOCUMENT_UPLOAD_DIR = os.path.join(SERVER_DIR, 'uploads')

if __name__ == '__main__':
    files = sorted(os.listdir(SAMPLE_DIR))
    if not files:
        print('sample_docs 目录为空')
        sys.exit(0)
    svc = get_rag_service()
    ok = fail = 0
    for f in files:
        p = os.path.join(SAMPLE_DIR, f)
        if os.path.isfile(p) and not f.startswith('.'):
            try:
                ok += bool(seed_one(svc, p))
            except Exception as e:
                fail += 1
                print(f"  [异常] {f}: {e}")
    total = execute_query("SELECT COUNT(*) AS n FROM tb_document")[0]['n']
    print(f"\n播种完成: 成功 {ok} | 失败 {fail} | 知识库现有文档 {total} 篇")
