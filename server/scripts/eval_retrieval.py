# -*- coding: utf-8 -*-
"""
检索评测脚本（Recall@K / MRR / HitRate）
对 golden set 中每个问题执行与线上一致的检索管线（不含查询改写，避免LLM依赖与随机性），
计算指标并输出最差用例，用于驱动检索调参与 badcase 复盘。

用法（在 server 目录、使用项目 venv）：
    ../.venv/bin/python scripts/eval_retrieval.py --golden scripts/golden_set.jsonl --topk 5
可选参数：
    --no-rerank      关闭重排做对照实验
    --tenant/--user/--clearance  模拟指定用户权限视角
"""

import argparse
import json
import os
import sys
from datetime import datetime

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

from application.services.rag_service import get_rag_service  # noqa: E402
from application.services.fusion import reciprocal_rank_fusion  # noqa: E402
from utils.config_handler import config  # noqa: E402


def load_golden(path: str):
    items = []
    with open(path, 'r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                print(f"[跳过] 第{line_no}行不是合法JSON")
                continue
            q = (row.get('question') or '').strip()
            # 兼容两种字段名：relevant_doc_ids（标准）/ key_id（简写）
            rel_raw = row.get('relevant_doc_ids') or row.get('key_id') or []
            rel = [int(i) for i in rel_raw]
            if not q or not rel:
                print(f"[跳过] 第{line_no}行缺少 question 或相关文档ID")
                continue
            note = row.get('note') or '/'.join(row.get('tags') or [])
            must = [str(k) for k in (row.get('must_contain') or [])]
            items.append({'question': q, 'relevant': set(rel), 'note': note,
                          'must_contain': must})
    return items


def retrieve_once(svc, question, args):
    """单问题检索：双路召回 + RRF + 可选重排（复用线上管线，不走查询改写）
    Returns: (ranked_doc_ids, chunk_texts)"""
    hybrid = config.get_section('rag').get('hybrid', {})
    rerank_cfg = config.get_section('rag').get('rerank', {})

    dense = svc._dense_search(question, args.tenant, args.user, args.clearance)
    sparse = svc.bm25.search(
        question, int(hybrid.get('bm25_top_k', 20)),
        args.tenant, args.user, args.clearance
    )
    fused = reciprocal_rank_fusion(dense, sparse,
                                   k=int(hybrid.get('rrf_k', 60)),
                                   weights=hybrid.get('weights') or {})
    merged = svc._merge_variants([fused])

    top_n = int(rerank_cfg.get('top_n', 8))
    if not args.no_rerank and merged:
        merged = svc.reranker.rerank(question, merged[:int(hybrid.get('fusion_top_n', 15))], top_n)
    else:
        merged = merged[:top_n]

    ranked_ids, texts = [], []
    for c in merged:
        did = c.get('doc_id')
        if did is not None and did not in ranked_ids:
            ranked_ids.append(did)
        txt = c.get('text') or c.get('content') or ''
        if txt:
            texts.append(txt)
    return ranked_ids, texts


def evaluate(items, svc, args):
    results = []
    for it in items:
        ranked, texts = retrieve_once(svc, it['question'], args)
        ranked = ranked[:args.topk]
        blob = '\n'.join(texts)
        hit_set = set(ranked) & it['relevant']
        recall = len(hit_set) / len(it['relevant'])
        mrr = 0.0
        for rank, did in enumerate(ranked, 1):
            if did in it['relevant']:
                mrr = 1.0 / rank
                break
        # 章节级关键词命中（must_contain 非空时计算）
        kw_found, kw_total = 0, len(it['must_contain'])
        for kw in it['must_contain']:
            if kw in blob:
                kw_found += 1
        kw_hit = (kw_found / kw_total) if kw_total else None
        results.append({
            'question': it['question'],
            'note': it['note'],
            'relevant': sorted(it['relevant']),
            'retrieved': ranked,
            'recall': recall,
            'mrr': mrr,
            'hit': int(bool(hit_set)),
            'must_contain': it['must_contain'],
            'kw_found': kw_found,
            'kw_total': kw_total,
            'kw_hit': kw_hit,
        })
    return results


def main():
    parser = argparse.ArgumentParser(description='RAG检索评测')
    parser.add_argument('--golden', default=os.path.join(SERVER_DIR, 'scripts', 'golden_set.jsonl'))
    parser.add_argument('--topk', type=int, default=5)
    parser.add_argument('--no-rerank', action='store_true')
    parser.add_argument('--tenant', type=int, default=None)
    parser.add_argument('--user', type=int, default=None)
    parser.add_argument('--clearance', type=int, default=None)
    args = parser.parse_args()

    if not os.path.exists(args.golden):
        print(f"未找到标注集: {args.golden}")
        print("请复制 golden_set.example.jsonl 为 golden_set.jsonl 并填入真实标注后重跑")
        sys.exit(1)

    items = load_golden(args.golden)
    if len(items) < 10:
        print(f"警告：有效样本仅 {len(items)} 条，建议 ≥30 条后再据其调参")

    print(f"加载 RAG 服务中（Chroma/BM25 从磁盘加载，不调用LLM）...")
    svc = get_rag_service()

    results = evaluate(items, svc, args)
    n = len(results)
    avg_recall = sum(r['recall'] for r in results) / n
    avg_mrr = sum(r['mrr'] for r in results) / n
    hit_rate = sum(r['hit'] for r in results) / n
    kw_rows = [r for r in results if r['kw_total']]
    avg_kw = (sum(r['kw_hit'] for r in kw_rows) / len(kw_rows)) if kw_rows else None

    print("\n========== 检索评测报告 ==========")
    print(f"样本数: {n} | topk: {args.topk} | rerank: {'off' if args.no_rerank else 'on'}")
    print(f"Recall@{args.topk}: {avg_recall:.3f}")
    print(f"MRR@{args.topk}:    {avg_mrr:.3f}")
    print(f"HitRate@{args.topk}: {hit_rate:.3f}")
    if avg_kw is not None:
        print(f"章节关键词命中率: {avg_kw:.3f} ({len(kw_rows)}条带must_contain)")

    # 最差用例：优先关键词低命中，其次低MRR
    worst = sorted(results, key=lambda r: (r['kw_hit'] if r['kw_hit'] is not None else 1,
                                           r['mrr']))[:8]
    print("\n---- 最差用例（优先复盘） ----")
    for w in worst:
        if (w['kw_hit'] in (None, 1.0)) and w['mrr'] == 1.0:
            continue
        kwinfo = f"关键词{w['kw_found']}/{w['kw_total']}" if w['kw_total'] else "-"
        print(f"Q: {w['question'][:40]} [{kwinfo}]")
        print(f"   期望文档: {w['relevant']} | 实际返回: {w['retrieved']}")

    report_dir = os.path.join(SERVER_DIR, 'data')
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(
        report_dir, f"eval_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump({
            'summary': {'n': n, 'topk': args.topk, 'rerank': not args.no_rerank,
                        'recall': round(avg_recall, 4), 'mrr': round(avg_mrr, 4),
                        'hit_rate': round(hit_rate, 4)},
            'results': results
        }, f, ensure_ascii=False, indent=2)
    print(f"\n完整报告已保存: {report_path}")


if __name__ == '__main__':
    main()
