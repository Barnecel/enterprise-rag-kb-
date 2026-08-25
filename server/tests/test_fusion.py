# -*- coding: utf-8 -*-
"""RRF融合单元测试——锁定权重/排序/异常输入行为"""
import pytest
from application.services.fusion import reciprocal_rank_fusion


def _d(doc_id, score):
    return {'doc_id': doc_id, 'parent_id': f'p{doc_id}', 'chunk_index': 0,
            'source': 's', 'tenant_id': 1, 'text': f't{doc_id}', 'score': score}


def test_双路交集按倒数排名累加():
    dense = [_d(1, 0.1), _d(2, 0.2), _d(3, 0.3)]
    sparse = [_d(2, 5.0), _d(1, 4.0), _d(4, 3.0)]
    out = reciprocal_rank_fusion(dense, sparse, k=60)
    ids = [x['doc_id'] for x in out]
    # 1和2在两路都出现，应排在单路命中的3、4之前
    assert set(ids[:2]) == {1, 2}
    assert 3 in ids and 4 in ids


def test_单路为空时另一路透传():
    dense = [_d(1, 0.1)]
    out = reciprocal_rank_fusion(dense, [], k=60)
    assert [x['doc_id'] for x in out] == [1]
    out = reciprocal_rank_fusion([], [_d(2, 1.0)], k=60)
    assert [x['doc_id'] for x in out] == [2]


def test_双路均为空返回空():
    assert reciprocal_rank_fusion([], []) == []


def test_权重影响排序():
    dense = [_d(1, 0.1), _d(2, 0.2)]
    sparse = [_d(2, 5.0), _d(1, 4.0)]
    # dense权重压倒性 → 1应排前
    out = reciprocal_rank_fusion(dense, sparse, k=60, weights={'dense': 10.0, 'sparse': 0.1})
    assert out[0]['doc_id'] == 1
    # sparse权重压倒性 → 2应排前
    out = reciprocal_rank_fusion(dense, sparse, k=60, weights={'dense': 0.1, 'sparse': 10.0})
    assert out[0]['doc_id'] == 2


def test_同块去重保留融合分():
    dense = [_d(1, 0.1)]
    sparse = [_d(1, 1.0)]
    out = reciprocal_rank_fusion(dense, sparse, k=60)
    assert len([x for x in out if x['doc_id'] == 1]) == 1
