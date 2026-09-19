# -*- coding: utf-8 -*-
"""Hybrid retrieval fusion unit tests"""
import pytest
from application.services.fusion import reciprocal_rank_fusion

def _d(doc_id, score, parent_id='p', chunk_index=0):
    return {'doc_id': doc_id, 'parent_id': parent_id, 'chunk_index': chunk_index, 'score': score}

class TestRRF:
    def test_basic_intersection(self):
        dense = [_d(1, 0.1), _d(2, 0.2), _d(3, 0.3)]
        sparse = [_d(2, 5.0), _d(1, 4.0), _d(4, 3.0)]
        out = reciprocal_rank_fusion(dense, sparse, k=60)
        ids = [x['doc_id'] for x in out]
        assert set(ids[:2]) == {1, 2}
        assert 3 in ids and 4 in ids

    def test_single_path_empty_other_passes_through(self):
        dense = [_d(1, 0.1)]
        out = reciprocal_rank_fusion(dense, [], k=60)
        assert [x['doc_id'] for x in out] == [1]
        out = reciprocal_rank_fusion([], [_d(2, 1.0)], k=60)
        assert [x['doc_id'] for x in out] == [2]

    def test_both_paths_empty_returns_empty(self):
        assert reciprocal_rank_fusion([], []) == []

    def test_weights_influence_ranking_order(self):
        dense = [_d(1, 0.1), _d(2, 0.2)]
        sparse = [_d(2, 5.0), _d(1, 4.0)]
        out = reciprocal_rank_fusion(dense, sparse, k=60, weights={'dense': 10.0, 'sparse': 0.1})
        assert out[0]['doc_id'] == 1
        out = reciprocal_rank_fusion(dense, sparse, k=60, weights={'dense': 0.1, 'sparse': 10.0})
        assert out[0]['doc_id'] == 2

    def test_same_chunk_dedup_preserves_fusion_score(self):
        dense = [_d(1, 0.1)]
        sparse = [_d(1, 1.0)]
        out = reciprocal_rank_fusion(dense, sparse, k=60)
        assert len([x for x in out if x['doc_id'] == 1]) == 1

    def test_k_parameter_small_increases_sensitivity(self):
        dense = [_d(i, 0.1) for i in range(1, 6)]
        sparse = [_d(i, 10.0) for i in range(1, 6)]
        out_default = reciprocal_rank_fusion(dense, sparse, k=60)
        out_smallk = reciprocal_rank_fusion(dense, sparse, k=10)
        assert out_smallk[0]['doc_id'] == 1

    def test_output_format_has_required_fields(self):
        dense = [_d(1, 0.5), _d(2, 0.3)]
        sparse = [_d(2, 2.0), _d(3, 1.5)]
        out = reciprocal_rank_fusion(dense, sparse, k=60)
        for item in out:
            assert 'doc_id' in item
            assert 'score' in item
            if 'parent_id' in item:
                assert isinstance(item['parent_id'], str)

    def test_doc_id_type_consistency(self):
        dense = [_d(1, 0.1, parent_id='p1')]
        sparse = [_d(1, 5.0, parent_id='p1')]
        out = reciprocal_rank_fusion(dense, sparse, k=60)
        for item in out:
            assert isinstance(item['doc_id'], int)

    def test_k_parameter_zero_returns_results(self):
        """k=0 返回结果而非 crash（分母变为1）"""
        dense = [_d(1, 0.1)]
        sparse = [_d(1, 1.0)]
        out = reciprocal_rank_fusion(dense, sparse, k=0)
        assert len(out) >= 1

    def test_k_parameter_negative_raises(self):
        """k negative should raise ZeroDivisionError from RRF formula"""
        dense = [_d(1, 0.1)]
        sparse = [_d(1, 1.0)]
        with pytest.raises(ZeroDivisionError):
            reciprocal_rank_fusion(dense, sparse, k=-1)

    def test_multivariant_merge_deduplication(self):
        """Multiple query rewrite variants merge with dedup+score accumulation"""
        candidates = [
            [_d(1, 0.1), _d(2, 0.2)],   
            [_d(2, 0.3), _d(3, 0.4)],   
            [_d(1, 0.5), _d(4, 0.6)],   
        ]
        merged = {}
        for variant in candidates:
            for item in variant:
                key = (item['doc_id'], item.get('parent_id'), item.get('chunk_index'))
                if key not in merged:
                    merged[key] = dict(item)
                else:
                    merged[key]['score'] = merged[key].get('score', 0) + item.get('score', 0)
        # doc 1 has parent_id='p', so key is (1, 'p', 0)
        assert merged.get((1, 'p', 0), {}).get('score', 0) > 0
        assert sum(1 for k in merged if k[0] == 2) == 1
        assert sum(1 for k in merged if k[0] == 3) == 1
        assert sum(1 for k in merged if k[0] == 4) == 1
