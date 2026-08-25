# -*- coding: utf-8 -*-
"""
一键备份：MySQL数据 + 向量库 + 索引文件 → data/backups/<时间戳>/
保留最近 N=5 份，自动清理更旧的。

用法（server目录）:
    ../.venv/bin/python scripts/backup.py               # 常规备份
    ../.venv/bin/python scripts/backup.py --with-uploads # 含原始文件(可能很大)
建议停机或低峰时执行（Chroma 运行中备份有极小的一致性风险）。
"""

import argparse
import os
import shutil
import subprocess
import sys
import time

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

BACKUP_ROOT = os.path.join(SERVER_DIR, 'data', 'backups')
KEEP = 5


def find_mysqldump():
    for p in ['/opt/homebrew/opt/mysql@8.4/bin/mysqldump', '/opt/homebrew/bin/mysqldump', '/usr/local/bin/mysqldump']:
        if os.path.isfile(p):
            return p
    return 'mysqldump'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--with-uploads', action='store_true', help='同时备份uploads原始文件(可能很大)')
    args = ap.parse_args()

    from utils.config_handler import config
    db = config.get_section('database') if 'database' in str(config.get_section) else None
    # database.yml 的段名可能是 database；直接读环境/配置兜底
    try:
        from application.utils.db_utils import DB_CONFIG
        host, port, user, password, name = (DB_CONFIG['host'], DB_CONFIG['port'],
                                            DB_CONFIG['user'], DB_CONFIG['password'],
                                            DB_CONFIG['database'])
    except Exception:
        print('无法读取DB配置')
        sys.exit(1)

    ts = time.strftime('%Y%m%d_%H%M%S')
    dest = os.path.join(BACKUP_ROOT, ts)
    os.makedirs(dest, exist_ok=True)

    # 1) MySQL 逻辑备份
    dump = os.path.join(dest, 'database.sql')
    cmd = [find_mysqldump(), f'-h{host}', f'-P{port}', f'-u{user}',
           f'-p{password}', '--single-transaction', '--default-character-set=utf8mb4', name]
    with open(dump, 'w', encoding='utf-8') as f:
        subprocess.run(cmd, stdout=f, check=True)
    print(f'✓ MySQL: {dump} ({os.path.getsize(dump)//1024}KB)')

    # 2) 向量库 + 索引文件
    shutil.copytree(os.path.join(SERVER_DIR, 'chroma_data'),
                    os.path.join(dest, 'chroma_data'), dirs_exist_ok=True)
    print('✓ chroma_data')
    for f in ('parent_map.pkl', 'bm25_index.pkl', 'parse_stats.jsonl'):
        src = os.path.join(SERVER_DIR, 'data', f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dest, f))
    print('✓ 索引文件(parent_map/bm25/parse_stats)')

    # 3) 原始文件（可选）
    if args.with_uploads:
        up = os.path.join(SERVER_DIR, 'uploads')
        if os.path.isdir(up):
            shutil.copytree(up, os.path.join(dest, 'uploads'), dirs_exist_ok=True)
            print('✓ uploads（含原始文件）')

    # 4) 清理旧备份（保留最近KEEP份）
    dirs = sorted(d for d in os.listdir(BACKUP_ROOT)
                  if os.path.isdir(os.path.join(BACKUP_ROOT, d)))
    for old in dirs[:-KEEP]:
        shutil.rmtree(os.path.join(BACKUP_ROOT, old))
        print(f'清理旧备份: {old}')

    print(f'\n备份完成: {dest}')


if __name__ == '__main__':
    main()
