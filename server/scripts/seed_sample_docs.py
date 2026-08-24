# -*- coding: utf-8 -*-
"""
演示语料播种脚本（全链路：文件→库文件→向量→状态）
- 同名文档已存在：先彻底删除旧版（向量/BM25/文件/DB）再导入新版
- 相同hash已存在：跳过（幂等）
- 支持批量导入、断点续传

用法（server目录）:
    ../.venv/bin/python scripts/seed_sample_docs.py
    或: ../.venv/bin/python scripts/seed_sample_docs.py --path 员工手册.txt 只种一份
"""

import hashlib
import os
import sys
import shutil
import uuid

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

from application.services.rag_service import get_rag_service  # noqa: E402
from application.utils.db_utils import execute_insert, execute_query, execute_update  # noqa: E402

SAMPLE_DIR = os.path.join(SERVER_DIR, 'scripts', 'sample_docs')
TENANT_ID = 1
CATEGORY_ID = 1   # 公司制度
UPLOAD_BY = 1     # admin
DOCUMENT_UPLOAD_DIR = os.path.join(SERVER_DIR, 'uploads')

# 确保上传目录存在
os.makedirs(DOCUMENT_UPLOAD_DIR, exist_ok=True)


def calc_hash(content: str) -> str:
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def full_delete(doc_id: int):
    """彻底删除一个文档的所有痕迹"""
    svc = get_rag_service()
    svc.delete_document_from_vectorstore(doc_id)
    execute_update("DELETE FROM tb_document_acl WHERE document_id = %s", (doc_id,))
    rows = execute_query("SELECT file_path FROM tb_document WHERE id = %s", (doc_id,))
    if rows and rows[0].get('file_path') and os.path.isfile(rows[0]['file_path']):
        os.remove(rows[0]['file_path'])
    execute_update("DELETE FROM tb_document WHERE id = %s", (doc_id,))


def seed_one(svc, path: str):
    """单文档入库（已封装幂等、删除旧版流程）"""
    name = os.path.basename(path)
    title = os.path.splitext(name)[0]
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    file_hash = calc_hash(content)

    # 1) 先按内容hash检查是否完全相同->跳过
    same_hash = execute_query("SELECT id FROM tb_document WHERE file_hash = %s", (file_hash,))
    if same_hash:
        print("  [跳过] %s: 内容未变化 (#%d)" % (title, same_hash[0]['id']))
        return False

    # 2) 若有同名旧文档，先全删
    old = execute_query("SELECT id FROM tb_document WHERE title = %s", (title,))
    for r in old:
        print("  [替换] 删除旧版 #%d %s" % (r['id'], title))
        full_delete(r['id'])

    # 3) 保存文件到 uploads/（使用uuid重名，避免覆盖源文件）
    ext = os.path.splitext(name)[1].lstrip('.').lower() or 'txt'
    unique_name = "%s.%s" % (uuid.uuid4().hex, ext)
    dest = os.path.join(DOCUMENT_UPLOAD_DIR, unique_name)
    shutil.copy2(path, dest)  # 保留元数据（修改时间等）

    # 4) 插入 tb_document（status='processing'）
    doc_id = execute_insert(
        "INSERT INTO tb_document (title, file_path, file_name, file_type, file_size, "
        "file_hash, category_id, tenant_id, status, upload_by, doc_level, min_level) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'processing', %s, 'public', 1)",
        (title, dest, name, ext, os.path.getsize(dest), file_hash,
         CATEGORY_ID, TENANT_ID, UPLOAD_BY)
    )

    # 5) 触发向量化
    ok = svc.add_document_to_vectorstore(
        dest, doc_id=doc_id, tenant_id=TENANT_ID,
        doc_level='public', min_level=1, owner_id=UPLOAD_BY
    )
    # 6) 标记完成/失败
    status = 'completed' if ok else 'failed'
    execute_update("UPDATE tb_document SET status = %s WHERE id = %s", (status, doc_id))
    print("  [完成] #%d %s -> %s" % (doc_id, title, '成功' if ok else '失败'))
    return ok


def main():
    import argparse
    parser = argparse.ArgumentParser(description="种子文档播种")
    parser.add_argument("--path", type=str, default="",
                        help="仅处理指定相对路径（相对于 scripts/sample_docs/)")
    parser.add_argument("--force", action="store_true",
                        help="即使hash相同也强制重入（慎用）")
    args = parser.parse_args()

    # 先列出样例目录下所有文件
    if not os.path.isdir(SAMPLE_DIR):
        print("[错误] 目录不存在: %s" % SAMPLE_DIR)
        sys.exit(1)

    files = sorted(os.listdir(SAMPLE_DIR))
    files = [f for f in files if os.path.isfile(os.path.join(SAMPLE_DIR, f)) and not f.startswith(".")]

    if not files:
        print("sample_docs 目录为空")
        sys.exit(0)

    svc = get_rag_service()
    # 若指定了 single file，仅处理该文件
    target_files = []
    if args.path:
        p = os.path.join(SAMPLE_DIR, args.path)
        if os.path.isfile(p):
            target_files = [args.path]
        else:
            print("[错误] 文件不在 sample_docs 目录下: %s" % args.path)
            sys.exit(1)
    else:
        target_files = files

    print("\n开始播种: 待处理 %d 篇" % len(target_files))
    ok = fail = 0
    for rel in target_files:
        p = os.path.join(SAMPLE_DIR, rel)
        try:
            ok += bool(seed_one(svc, p))
        except Exception as e:
            fail += 1
            print("[异常] %s: %s" % (rel, e))
    total = execute_query("SELECT COUNT(*) AS n FROM tb_document")[0]["n"]
    print("\n播种完成: 成功 %d | 失败 %d | 知识库现有文档 %d 篇" % (ok, fail, total))


if __name__ == "__main__":
    main()