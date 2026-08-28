# -*- coding: utf-8 -*-
"""BM25-only 检索评测（对照实验：证明混合检索优于单路词法召回）
复用 eval_retrieval.py 的指标口径，仅用 svc.bm25.search 做召回，再走 Cross-Encoder 重排。
用法: ../.venv/bin/python scripts/eval_retrieval_bm25only.py --golden scripts/golden_set.jsonl --topk 5
"""
import argparse, json, os, sys
from datetime import datetime
SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)
from application.services.rag_service import get_rag_service
from utils.config_handler import config

def load_golden(path):
    items = []
    with open(path, 'r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line: continue
            try: row = json.loads(line)
            except: continue
            q = (row.get('question') or '').strip()
            rel = [int(i) for i in (row.get('relevant_doc_ids') or row.get('key_id') or [])]
            if not q or not rel: continue
            items.append({'question': q, 'relevant': set(rel),
                          'must_contain': [str(k) for k in (row.get('must_contain') or [])]})
    return items

def retrieve_once(svc, question, args):
    hybrid = config.get_section('rag').get('hybrid', {})
    rerank_cfg = config.get_section('rag').get('rerank', {})
    # 仅 BM25 召回
    sparse = svc.bm25.search(question, int(hybrid.get('bm25_top_k', 20)),
                             args.tenant, args.user, args.clearance)
    merged = sparse
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
        if txt: texts.append(txt)
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
                mrr = 1.0 / rank; break
        kw_found = sum(1 for kw in it['must_contain'] if kw in blob)
        kw_total = len(it['must_contain'])
        results.append({'question': it['question'], 'relevant': sorted(it['relevant']),
                        'retrieved': ranked, 'recall': recall, 'mrr': mrr,
                        'hit': int(bool(hit_set)), 'kw_found': kw_found, 'kw_total': kw_total})
    return results

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--golden', default=os.path.join(SERVER_DIR, 'scripts', 'golden_set.jsonl'))
    p.add_argument('--topk', type=int, default=5)
    p.add_argument('--no-rerank', action='store_true')
    p.add_argument('--tenant', type=int, default=None)
    p.add_argument('--user', type=int, default=None)
    p.add_argument('--clearance', type=int, default=None)
    args = p.parse_args()
    items = load_golden(args.golden)
    print(f"加载 RAG 服务(BM25-only 评测)...")
    svc = get_rag_service()
    results = evaluate(items, svc, args)
    n = len(results)
    avg_recall = sum(r['recall'] for r in results)/n
    avg_mrr = sum(r['mrr'] for r in results)/n
    hit_rate = sum(r['hit'] for r in results)/n
    kw_rows = [r for r in results if r['kw_total']]
    avg_kw = (sum(r['kw_hit'] if False else r['kw_found']/r['kw_total'] for r in kw_rows)/len(kw_rows)) if kw_rows else None
    print(f"\n====== BM25-only 检索评测报告 ======")
    print(f"样本数: {n} | topk: {args.topk} | rerank: {'off' if args.no_rerank else 'on'}")
    print(f"Recall@{args.topk}: {avg_recall:.3f}")
    print(f"MRR@{args.topk}:    {avg_mrr:.3f}")
    print(f"HitRate@{args.topk}: {hit_rate:.3f}")
    if avg_kw is not None:
        print(f"章节关键词命中率: {avg_kw:.3f}")
    report_dir = os.path.join(SERVER_DIR, 'data')
    os.makedirs(report_dir, exist_ok=True)
    rp = os.path.join(report_dir, f"eval_report_bm25only_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(rp, 'w', encoding='utf-8') as f:
        json.dump({'summary': {'mode':'bm25-only','n':n,'topk':args.topk,
                  'recall':round(avg_recall,4),'mrr':round(avg_mrr,4),'hit_rate':round(hit_rate,4)},
                  'results': results}, f, ensure_ascii=False, indent=2)
    print(f"\n报告: {rp}")

if __name__ == '__main__':
    main()
