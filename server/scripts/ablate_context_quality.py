# -*- coding: utf-8 -*-
"""上下文质量消融：父窗口 on/off × TopK 3/5/8 → 事实覆盖率
- 逐字版 FactCoverage：金标答案片段在上下文中精确出现（严格下界）
- 语义版 SemFactCoverage：事实 embedding 与上下文 embedding 余弦 ≥ 阈值（信息携带率）
每问只检索一次(top=8)，从同一结果派生各配置；
全局事实片段去重后批量 embed 一次，每问 6 个上下文一次 embed_documents 批量完成。
用法（server 目录、项目 venv）：
  ../.venv/bin/python scripts/ablate_context_quality.py [--semantic]
"""
import argparse
import json
import math
import os
import re
import sys

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

from application.services.rag_service import get_rag_service  # noqa: E402
from application.services.fusion import reciprocal_rank_fusion  # noqa: E402
from application.services.document_parser import _normalize_cjk_text  # noqa: E402
from application.rag.retrievers import _parent_map  # noqa: E402
from utils.config_handler import config  # noqa: E402
from utils.logger_handler import logger  # noqa: E402
import logging
logging.getLogger('rag_system').setLevel(logging.ERROR)

SEM_THRESHOLD = 0.82


def load_golden(path):
    items = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            q = (row.get('question') or '').strip()
            ans = (row.get('answer') or '').strip()
            rel = [int(i) for i in (row.get('relevant_doc_ids') or row.get('key_id') or [])]
            if not q or not ans or not rel:
                continue
            items.append({'question': q, 'answer': ans, 'relevant': set(rel)})
    return items


def split_facts(answer):
    parts = re.split(r'[；;。!\n]', _normalize_cjk_text(answer))
    return [p.strip() for p in parts if len(p.strip()) >= 2]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-9)


def embed_batch(svc, texts, batch=20):
    vecs = []
    for i in range(0, len(texts), batch):
        vecs.extend(svc.embeddings.embed_documents(texts[i:i + batch]))
    return vecs


def retrieve_ranked(svc, question, args):
    hybrid = config.get_section('rag').get('hybrid', {})
    rerank_cfg = config.get_section('rag').get('rerank', {})
    dense = svc._dense_search(question, args.tenant, args.user, args.clearance)
    sparse = svc.bm25.search(
        question, int(hybrid.get('bm25_top_k', 20)),
        args.tenant, args.user, args.clearance)
    fused = reciprocal_rank_fusion(dense, sparse, k=int(hybrid.get('rrf_k', 60)),
                                   weights=hybrid.get('weights') or {})
    merged = svc._merge_variants([fused])
    top_n = int(rerank_cfg.get('top_n', 8))
    if merged:
        merged = svc.reranker.rerank(question, merged[:int(hybrid.get('fusion_top_n', 15))], top_n)
    return merged[:top_n]


def build_texts(candidates, topk, parent):
    docs = candidates[:topk]
    texts = []
    for d in docs:
        txt = _parent_map.get(d.get('parent_id'), d.get('text')) if parent == 'on' else d.get('text')
        if txt:
            texts.append(txt)
    return _normalize_cjk_text('\n\n'.join(texts))


def run_ablation(items, svc, args):
    configs = [(t, p) for t in (3, 5, 8) for p in ('on', 'off')]
    acc = {f"k{t}_{p}": {'hit': 0, 'total': 0, 'doc_hit': 0, 'n': 0} for t, p in configs}

    fact_cache = {}
    if args.semantic:
        all_facts = sorted({f for it in items for f in split_facts(it['answer'])})
        print(f"全局唯一事实片段: {len(all_facts)}，批量 embedding...")
        fv = embed_batch(svc, all_facts)
        fact_cache = dict(zip(all_facts, fv))
        print("事实 embedding 完成")

    recs = []
    for idx, it in enumerate(items, 1):
        candidates = retrieve_ranked(svc, it['question'], args)
        facts = split_facts(it['answer'])
        relevant = it['relevant']
        if not facts:
            continue

        if args.semantic:
            ctx_texts = [build_texts(candidates, t, p) for t, p in configs]
            ctx_vecs = dict(zip(configs, embed_batch(svc, ctx_texts)))

        per_q = {}
        for t, p in configs:
            key = f"k{t}_{p}"
            blob = build_texts(candidates, t, p)
            if args.semantic:
                ctx_vec = ctx_vecs[(t, p)]
                covered = sum(1 for f in facts if cosine(fact_cache[f], ctx_vec) >= SEM_THRESHOLD)
            else:
                covered = sum(1 for f in facts if f in blob)
            doc_ids = {d.get('doc_id') for d in candidates[:t] if d.get('doc_id') is not None}
            acc[key]['hit'] += covered
            acc[key]['total'] += len(facts)
            acc[key]['doc_hit'] += int(bool(doc_ids & relevant))
            acc[key]['n'] += 1
            per_q[key] = covered / len(facts)
        recs.append({'question': it['question'], 'coverage': {k: round(v, 3) for k, v in per_q.items()}})
        if idx % 10 == 0:
            print(f"  进度: {idx}/{len(items)}")

    return configs, acc, recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--golden', default=os.path.join(SERVER_DIR, 'scripts', 'golden_set.jsonl'))
    ap.add_argument('--semantic', action='store_true', help='额外计算语义事实覆盖率(需调 embedding)')
    ap.add_argument('--tenant', type=int, default=None)
    ap.add_argument('--user', type=int, default=None)
    ap.add_argument('--clearance', type=int, default=None)
    args = ap.parse_args()

    items = load_golden(args.golden)
    mode = '逐字+语义' if args.semantic else '逐字'
    print(f"金标样本: {len(items)} | 模式: {mode} | 加载 RAG 服务...")
    svc = get_rag_service()
    configs, acc, recs = run_ablation(items, svc, args)

    label = '语义FactCoverage(@0.82)' if args.semantic else '逐字FactCoverage'
    print(f"\n========== 上下文质量消融（{label}） ==========")
    print(f"{'配置':<16}{'事实覆盖':<12}{'DocRecall@k':<12}{'事实数':<8}")
    print('-' * 50)
    rows = []
    for t, p in configs:
        a = acc[f"k{t}_{p}"]
        rows.append((t, p, a['hit'] / a['total'], a['doc_hit'] / a['n'], a['total']))
    for t, p, fc, dr, total in sorted(rows, key=lambda x: -x[2]):
        print(f"TopK={t} 父窗口{p:<9} {fc:.3f}       {dr:.3f}       {total}")

    best = max(rows, key=lambda x: (x[2], x[3]))
    print(f"\n[结论] 事实覆盖率最高: TopK={best[0]} 父窗口{best[1]} "
          f"(FactCoverage={best[2]:.3f}, DocRecall@{best[0]}={best[3]:.3f})")

    os.makedirs(os.path.join(SERVER_DIR, 'data'), exist_ok=True)
    out = os.path.join(SERVER_DIR, 'data',
                       f"ablation_context_quality_{'sem' if args.semantic else 'lex'}.json")
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'mode': 'semantic' if args.semantic else 'lexical',
                   'sem_threshold': SEM_THRESHOLD if args.semantic else None,
                   'report': [{'topk': t, 'parent': p,
                               'fact_coverage': round(fc, 4), 'doc_recall': round(dr, 4)}
                              for t, p, fc, dr, _ in rows],
                   'per_question': recs}, f, ensure_ascii=False, indent=2)
    print(f"报告: {out}")


if __name__ == '__main__':
    main()