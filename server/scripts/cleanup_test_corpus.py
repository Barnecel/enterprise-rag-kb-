# -*- coding: utf-8 -*-
"""
测试语料清理脚本
默认 dry-run 仅列出目标文档；人工确认后加 --apply 真正执行。

对每个目标文档依次执行：
  1. 删除向量库/BM25索引/父窗口映射中的数据
  2. 删除 ACL 授权记录
  3. 删除磁盘文件
  4. 删除 tb_document 记录

用法（server 目录下）：
  ../.venv/bin/python scripts/cleanup_test_corpus.py                 # 预览
  ../.venv/bin/python scripts/cleanup_test_corpus.py --apply         # 执行删除
  可选: --keep 12,13     白名单ID（保留不删）
       --category-id 3   改为按分类删除指定分类下的全部文档
"""

import argparse
import os
import sys

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

from application.services.rag_service import get_rag_service  # noqa: E402
from application.utils.db_utils import execute_query, execute_update  # noqa: E402


def fetch_targets(args):
    """确定待删除文档集合：默认无分类(category_id IS NULL)，可改按分类"""
    params = []
    conds = []
    if args.category_id:
        conds.append("category_id = %s")
        params.append(args.category_id)
    else:
        conds.append("category_id IS NULL")
    if args.keep:
        keep_ids = [int(i) for i in args.keep.split(',') if i.strip()]
        fmt = ','.join(['%s'] * len(keep_ids))
        conds.append(f"id NOT IN ({fmt})")
        params.extend(keep_ids)

    sql = (f"SELECT id, title, file_name, file_type, file_path "
           f"FROM tb_document WHERE {' AND '.join(conds)} ORDER BY id")
    return execute_query(sql, tuple(params))


def main():
    parser = argparse.ArgumentParser(description='知识库测试语料清理')
    parser.add_argument('--apply', action='store_true', help='真正执行删除（默认仅预览）')
    parser.add_argument('--keep', default='', help='白名单文档ID，逗号分隔')
    parser.add_argument('--category-id', type=int, default=None, help='改为按分类删除')
    args = parser.parse_args()

    targets = fetch_targets(args)
    total_size = sum(os.path.getsize(t['file_path']) for t in targets
                     if os.path.isfile(t['file_path']))

    print(f"\n待删除文档: {len(targets)} 篇 | 文件体积约 {total_size/1024/1024:.1f} MB")
    print("-" * 80)
    for t in targets[:50]:
        print(f"  #{t['id']:<5} [{t['file_type']}] {t['title']}")
    if len(targets) > 50:
        print(f"  ... 其余 {len(targets)-50} 篇省略")
    print("-" * 80)

    if not targets:
        print("没有需要删除的文档")
        return

    if not args.apply:
        print("当前为预览模式。如需保留个别文档，用 --keep id1,id2 排除后重跑；")
        print(f"确认后执行: python scripts/cleanup_test_corpus.py --apply"
              + (f" --keep {args.keep}" if args.keep else ""))
        return

    input(f"\n即将永久删除 {len(targets)} 篇文档及其向量数据！回车确认，Ctrl+C 取消 > ")

    svc = get_rag_service()
    ok = fail = missing_file = 0
    for i, t in enumerate(targets, 1):
        try:
            svc.delete_document_from_vectorstore(t['id'])
            execute_update("DELETE FROM tb_document_acl WHERE document_id = %s", (t['id'],))
            if t.get('file_path') and os.path.isfile(t['file_path']):
                os.remove(t['file_path'])
            else:
                missing_file += 1
            execute_update("DELETE FROM tb_document WHERE id = %s", (t['id'],))
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  [失败] #{t['id']} {t['title']}: {e}")
        if i % 20 == 0:
            print(f"  进度 {i}/{len(targets)}")

    left = execute_query("SELECT COUNT(*) AS n FROM tb_document")
    print(f"\n完成: 成功 {ok} | 失败 {fail} | 文件本就缺失 {missing_file}")
    print(f"剩余文档总数: {left[0]['n']}")
    print("提示: 缓存已随删除自动清空；若前端列表异常可刷新页面")


if __name__ == '__main__':
    main()
