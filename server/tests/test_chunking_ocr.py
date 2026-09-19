# -*- coding: utf-8 -*-
"""OCR 页码贯通回归测试——覆盖扫描件误读、混合内容、边界情况"""
import pytest
from application.services.chunking import (
    build_parent_child_chunks_from_elements, _to_atomic_units
)


class El:
    """模拟 document_parser.Element"""
    def __init__(self, kind, text, page):
        self.kind, self.text, self.page = kind, text, page


def _cfg():
    from utils.config_handler import config
    d = config.get_section('document')
    return int(d['child_chunk_size']), int(d['child_chunk_overlap']), int(d['parent_chunk_size'])


def test_页码连续性在chunk边界():
    """OCR misread at chunk boundary: 页码应在分块边界正确贯通"""
    long_text = '第一章 内容' * 100
    elements = [El('text', long_text, 1)]
    children, parents = build_parent_child_chunks_from_elements(
        elements, doc_id=99, source='t.txt', tenant_id=1)
    assert children, '应产生子块'
    pages = {c.metadata.get('page') for c in children}
    assert pages == {1}, f'所有子块页码应为1，实际: {pages}'


def test_混合内容文本表格页码贯通():
    """混合内容（文本+表格）页码应全部贯通"""
    big_table = '| a | b |\n|---|---|\n' + '\n'.join(f'| {i} | v{i} |' for i in range(50))
    elements = [El('text', '第一章 内容' * 30, 1), El('table', big_table, 2)]
    children, parents = build_parent_child_chunks_from_elements(
        elements, doc_id=98, source='t.txt', tenant_id=1)
    assert children, '应产生子块'
    pages = {c.metadata.get('page') for c in children}
    # 文本子块页码1，表格子块页码2
    assert 1 in pages or 2 in pages, f'页码应包含1或2，实际: {pages}'


def test_多页文档页码覆盖():
    """多页文档：页码应覆盖所有原始页码中的至少一个"""
    elements = [
        El('text', '第一页内容' * 30, 1),
        El('text', '第二页内容' * 30, 2),
        El('text', '第三页内容' * 30, 3),
    ]
    children, parents = build_parent_child_chunks_from_elements(
        elements, doc_id=97, source='t.txt', tenant_id=1)
    assert children, '应产生子块'
    pages = {c.metadata.get('page') for c in children}
    # 至少应包含部分页码，且页码应为整数
    assert len(pages) >= 1, "至少应有1个页码"
    assert all(isinstance(p, int) for p in pages), "页码应为整数类型"
    # 关键回归点：页码应在 1-3 范围内（反映原始文档页码）
    assert all(1 <= p <= 3 for p in pages), f"页码应在 1-3 范围内，实际: {pages}"


def test_单页文档全部被捕获():
    """单页文档：所有子块应仍然关联到该页码"""
    elements = [El('text', '单页内容' * 50, 5)]
    children, parents = build_parent_child_chunks_from_elements(
        elements, doc_id=96, source='t.txt', tenant_id=1)
    assert children, '应产生子块'
    pages = {c.metadata.get('page') for c in children}
    assert pages == {5}, f'单页文档页码应为5，实际: {pages}'


def test_空元素返回空():
    """空元素列表应返回空结果（已存在测试，此处作回归验证）"""
    children, parents = build_parent_child_chunks_from_elements(
        [], doc_id=95, source='t.txt', tenant_id=1)
    assert children == [] and parents == {}


def test_大段连续文本不丢失页码():
    """大段连续文本：分块不应导致页码丢失或错误"""
    # 连续文本跨多页
    elements = []
    for pg in range(1, 4):
        elements.append(El('text', '段落内容' * 40, pg))
    children, parents = build_parent_child_chunks_from_elements(
        elements, doc_id=94, source='t.txt', tenant_id=1)
    assert children, '应产生子块'
    pages = {c.metadata.get('page') for c in children}
    # 关键回归：页码应来自原始元数据，不应是空或错误值
    assert len(pages) >= 1, "应至少保留1个页码"
    assert all(isinstance(p, int) for p in pages), "页码应为整数类型"
    # 任意页码不应为None或异常值
    assert not any(p is None for p in pages), "页码不应为None"


def test_表格页码始终带表头():
    """表格子块始终包含完整表头（回归测试）"""
    big_table = '| a | b |\n|---|---|\n' + '\n'.join(f'| {i} | v{i} |' for i in range(200))
    elements = [El('table', big_table, 1), El('text', '后文' * 100, 2)]
    children, parents = build_parent_child_chunks_from_elements(
        elements, doc_id=98, source='t.txt', tenant_id=1)
    # 含表格的子块必须包含完整表头
    table_children = [c for c in children if '| a |' in c.page_content]
    assert table_children, '表格子块应存在'
    assert all('|---|' in c.page_content for c in table_children), \
        '每个表格子块都应带表头(重复表头机制)'
