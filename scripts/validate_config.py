#!/usr/bin/env python3
"""配置校验脚本 - 启动前检查必需配置项是否就绪"""
import os, sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'server'))
from utils.config_handler import config

def _get(section, key, default=None):
    try: return config.get_section(section).get(key, default)
    except: return default

def check(cond, msg, fix=None):
    if cond:
        print(f"  [OK] {msg}"); return True
    else:
        print(f"  [MISSING] {msg}")
        if fix: print(f"    -> {fix}")
        return False

def main():
    print("="*60)
    print(" 企业RAG系统配置校验")
    print("="*60)
    results = []

    # 1. 数据库
    print("\n[1/7] 数据库配置")
    r1 = check(_get('database','host') not in (None,''), f"数据库主机: {_get('database','host','未设置')}",
               "在 server/config/database.yml 中设置 host"); results.append(r1)
    r2 = check(_get('database','port') not in (None,''), f"数据库端口: {_get('database','port','未设置')}",
               "在 server/config/database.yml 中设置 port"); results.append(r2)
    r3 = check(_get('database','user') not in (None,''), f"数据库用户: {_get('database','user','未设置')}",
               "在 server/config/database.yml 中设置 user"); results.append(r3)
    r4 = check(_get('database','database') not in (None,''), f"数据库名: {_get('database','database','未设置')}",
               "在 server/config/database.yml 中设置 database"); results.append(r4)
    r5 = check(_get('database','password') not in (None,''), "数据库密码: 已设置(或留空)",
               "在 server/config/database.yml 或 env DB_PASSWORD 中设置"); results.append(r5)

    # 2. Chroma
    print("\n[2/7] Chroma 向量数据库配置")
    r6 = check(_get('chroma','persist_directory') not in (None,''), f"Chroma路径: {_get('chroma','persist_directory','未设置')}",
               "在 server/config/chroma.yml 中设置 persist_directory"); results.append(r6)
    r7 = check(_get('chroma','collection_name') not in (None,''), f"集合名: {_get('chroma','collection_name','未设置')}",
               "在 server/config/chroma.yml 中设置 collection_name"); results.append(r7)

    # 3. Flask
    print("\n[3/7] Flask 配置")
    r8 = check(_get('flask','secret_key') not in (None,''), "Flask SECRET_KEY: 已设置",
               "在 server/config/flask.yml 中设置 secret_key 或 env FLASK_SECRET_KEY"); results.append(r8)
    r9 = check(_get('flask','debug') not in (None,''), "Flask DEBUG: 已设置",
               "在 server/config/flask.yml 中设置 debug"); results.append(r9)

    # 4. JWT
    print("\n[4/7] JWT 配置")
    js = _get('flask','jwt_secret_key','')
    r10 = check(js not in (None,''), "JWT secret_key: 已设置",
                "在 server/config/flask.yml 中设置 jwt_secret_key 或 env JWT_SECRET_KEY"); results.append(r10)

    # 5. 文档
    print("\n[5/7] 文档处理配置")
    r11 = check(_get('document','chunk_size') not in (None,''), f"分块大小: {_get('document','chunk_size','未设置')}",
                "在 server/config/document.yml 中设置 chunk_size"); results.append(r11)
    r12 = check(_get('document','allowed_extensions') not in (None,''), "allowed_extensions: 已设置",
                "在 server/config/document.yml 中设置 allowed_extensions"); results.append(r12)

    # 6. RAG
    print("\n[6/7] RAG 核心配置")
    r13 = check(_get('rag','score_threshold') not in (None,''), "score_threshold: 已设置",
                "在 server/config/rag.yml 中设置 score_threshold"); results.append(r13)
    hy = _get('rag','hybrid',{}).get('enabled')
    r14 = check(hy not in (None,''), "RAG hybrid 检索: 已配置",
                "在 server/config/rag.yml 中设置 hybrid.enabled"); results.append(r14)

    # 7. 环境变量
    print("\n[7/7] 环境变量检查")
    import yaml
    cfg_path = os.path.join(BASE_DIR, 'config')
    ef = os.path.exists(os.path.join(cfg_path, '.env.example'))
    if ef:
        with open(os.path.join(cfg_path, '.env.example'),'r',encoding='utf-8') as f:
            if '${' in f.read(): print("  [INFO] .env.example 含变量占位符")
    if not ef: print("  [WARN] 未找到 .env.example，建议复制一份填真值")

    # 汇总
    print("\n" + "\n" + "="*60)
    passed = sum(1 for r in results if r is True)
    total = len(results)
    print(f"  结果: {passed}/{total} 检查通过")
    if passed == total:
        print("  ✅ 所有检查通过，可以启动项目"); return 0
    else:
        print(f"  ⚠️  {total-passed} 项配置缺失"); return 1

if __name__ == '__main__':
    sys.exit(main())
