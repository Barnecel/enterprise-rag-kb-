# -*- coding: utf-8 -*-
"""
RRF(Reciprocal Rank Fusion) 融合模块
融合 BM25 稀疏召回与 Embedding 稠密召回结果
"""
from typing import List, Dict, Optional


def _key_of(item: Dict) -> tuple:
    """候选去重键：doc_id + parent_id + chunk_index"""
    return (item.get('doc_id'), item.get('parent_id'), item.get('chunk_index'))


def reciprocal_rank_fusion(
    dense_results: List[Dict],
    sparse_results: List[Dict],
    k: int = 60,
    weights: Optional[Dict[str, float]] = None
) -> List[Dict]:
    """
    RRF融合两路召回结果

    Args:
        dense_results: 稠密召回(Embedding)，score 为 L2距离(越小越相关)
        sparse_results: 稀疏召回(BM25)，score 为 BM25分数(越大越相关)
        k: RRF常数(默认60)
        weights: 两路权重 {'dense': x, 'sparse': y}

    Returns:
        融合后按RRF分数降序的候选列表，字段:
        {doc_id, parent_id, source, tenant_id, chunk_index, text,
         score(RRF), dense_score, sparse_score}
    """
    weights = weights or {'dense': 1.0, 'sparse': 1.0}
    fused: Dict[tuple, Dict] = {}

    def _init(key, item):
        if key not in fused:
            fused[key] = dict(item)
            fused[key]['dense_score'] = None
            fused[key]['sparse_score'] = None
            fused[key]['score'] = 0.0

    # 稠密路：排名越小贡献越大 (score为L2距离，不影响RRF仅用于记录)
    for rank, item in enumerate(dense_results):
        key = _key_of(item)
        _init(key, item)
        fused[key]['score'] += weights['dense'] / (k + rank + 1)
        fused[key]['dense_score'] = item.get('score')

    # 稀疏路
    for rank, item in enumerate(sparse_results):
        key = _key_of(item)
        _init(key, item)
        fused[key]['score'] += weights['sparse'] / (k + rank + 1)
        fused[key]['sparse_score'] = item.get('score')

    results = sorted(fused.values(), key=lambda x: x['score'], reverse=True)
    return results
