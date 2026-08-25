# -*- coding: utf-8 -*-
"""配置插值单元测试——${VAR:default}机制与环境变量覆盖"""
import os
import pytest
from utils.config_handler import config


def test_环境变量默认值插值():
    # embedding.yml 的 api_base 使用 ${EMBEDDING_API_BASE:...} —— 当前环境未设置时应取默认
    v = config.get_section('embedding').get('api_base', '')
    assert '${' not in str(v), '插值后不应残留占位符'
    assert str(v).startswith('http')


def test_环境变量覆盖默认(monkeypatch):
    monkeypatch.setenv('LLM_API_BASE', 'http://override.test/v1')
    # config_handler 在导入时已加载一次；这里验证机制：重新解析一段含占位符的文本
    resolved = config._interpolate('${LLM_API_BASE:http://default/v1}') if hasattr(config, '_interpolate') else None
    if resolved is None:
        pytest.skip('config_handler 未暴露内部插值函数，跳过白盒断言')
    assert 'override.test' in resolved


def test_密级配置结构():
    rag = config.get_section('rag')
    assert 'score_threshold' in rag, 'L2阈值必须存在'
    assert 'hybrid' in rag and 'rerank' in rag


def test_文档分块参数存在():
    d = config.get_section('document')
    for key in ('child_chunk_size', 'child_chunk_overlap', 'parent_chunk_size'):
        assert key in d, f'缺少分块参数 {key}'
        assert int(d[key]) > 0
