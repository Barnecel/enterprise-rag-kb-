# -*- coding: utf-8 -*-
"""
模型 A/B 对比测试（RAG地狱五题）
自动完成：切换模型A → 逐题问答计时 → 切换模型B → 同样流程 → 输出盲评格式结果
- 主结果文件只含 样本A/样本B，不含型号（供LLM裁判盲评）
- 型号映射写入独立文件 compare_mapping.json（自己留好，别贴给裁判）

用法（server目录）:
    ../.venv/bin/python scripts/compare_models.py --a 1 --b 2
    可选: --limit 1   # 每个模型只跑前N题（快速冒烟）
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

from application.services.rag_service import get_rag_service  # noqa: E402
from application.utils.db_utils import execute_query, execute_update  # noqa: E402

# RAG地狱五题（与评分锚点配套，见答辩材料）
QUESTIONS = [
    {"id": "Q1", "type": "多跳对比", "q": "传唤和继续盘问有什么区别？各自的时限是多久？"},
    {"id": "Q2", "type": "否定排除", "q": "哪些人不适用继续盘问？"},
    {"id": "Q3", "type": "双档数字", "q": "行政案件立案审查期限是多久？疑难复杂案件呢？"},
    {"id": "Q4", "type": "全局综合", "q": "从受案到处罚决定，这份资料覆盖了办案的哪些主要环节？"},
    {"id": "Q5", "type": "改写桥接", "q": "行政拘留可以暂缓执行吗？需要提供担保人还是保证金？"},
]


def load_llm_config(model_id):
    rows = execute_query("SELECT * FROM tb_model_config WHERE id=%s", (model_id,))
    if not rows:
        print(f"模型配置 #{model_id} 不存在")
        sys.exit(1)
    r = rows[0]
    if r['model_type'] != 'llm':
        print(f"配置 #{model_id}「{r['name']}」不是生成模型（{r['model_type']}），对比仅支持 llm 类型")
        sys.exit(1)
    return r


def activate(svc, cfg):
    """与 /api/model/<id>/activate 的 LLM 分支一致：DB标记 + 热切换 + 清缓存"""
    execute_update("UPDATE tb_model_config SET is_active=0 WHERE model_type='llm'")
    execute_update("UPDATE tb_model_config SET is_active=1 WHERE id=%s", (cfg['id'],))
    svc.hot_swap_llm({'api_base': cfg['api_base'], 'api_key': cfg['api_key'], 'model_name': cfg['model_name']})


def run_suite(svc, label, limit):
    results = []
    for i, item in enumerate(QUESTIONS[:limit]):
        t0 = time.time()
        try:
            r = svc.answer_question(item['q'], user_id=1, tenant_id=1, clearance_level=5)
            answer = r.get('answer') or ''
            sources = [s if isinstance(s, int) else s.get('id') for s in r.get('source_documents', [])]
        except Exception as e:
            answer, sources = f"（调用失败: {str(e)[:120]}）", []
        dt = time.time() - t0
        results.append({
            'qid': item['id'], 'type': item['type'], 'question': item['q'],
            'answer': answer, 'seconds': round(dt, 1), 'cited_docs': sources
        })
        print(f"  [{label}] {item['id']} {item['type']} {dt:.0f}s 答案{len(answer)}字")
    return results


def main():
    ap = argparse.ArgumentParser(description='模型A/B对比（RAG地狱五题）')
    ap.add_argument('--a', type=int, required=True, help='模型配置ID·样本A')
    ap.add_argument('--b', type=int, required=True, help='模型配置ID·样本B')
    ap.add_argument('--limit', type=int, default=5, help='每模型题数上限（默认5）')
    args = ap.parse_args()

    cfg_a, cfg_b = load_llm_config(args.a), load_llm_config(args.b)
    svc = get_rag_service()

    out_dir = os.path.join(SERVER_DIR, 'data')
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

    print(f"=== 样本A：先跑 #{cfg_a['id']} ===")
    activate(svc, cfg_a)
    res_a = run_suite(svc, 'A', args.limit)

    print(f"=== 样本B：#{cfg_b['id']} ===")
    activate(svc, cfg_b)
    res_b = run_suite(svc, 'B', args.limit)

    # 收尾：恢复A为启用态（避免停留在B）
    activate(svc, cfg_a)

    # 盲评主文件（无型号信息）
    blind = {
        'generated_at': ts,
        'note': '盲评用。样本A=先测者，样本B=后测者；型号映射见 compare_mapping.json',
        'questions': QUESTIONS[:args.limit],
        'sample_A': res_a,
        'sample_B': res_b,
    }
    blind_path = os.path.join(out_dir, f'compare_results_{ts}.json')
    with open(blind_path, 'w', encoding='utf-8') as f:
        json.dump(blind, f, ensure_ascii=False, indent=2)

    # 型号映射（勿贴给裁判）
    mapping = {
        'generated_at': ts,
        'sample_A': {'config_id': cfg_a['id'], 'name': cfg_a['name'], 'model_name': cfg_a['model_name'], 'api_base': cfg_a['api_base']},
        'sample_B': {'config_id': cfg_b['id'], 'name': cfg_b['name'], 'model_name': cfg_b['model_name'], 'api_base': cfg_b['api_base']},
    }
    map_path = os.path.join(out_dir, f'compare_mapping_{ts}.json')
    with open(map_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    print(f"\n完成。盲评结果: {blind_path}")
    print(f"型号映射(自己留): {map_path}")
    print("把盲评结果JSON贴给裁判即可，评测后自行对答案。")


if __name__ == '__main__':
    main()
