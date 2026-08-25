# -*- coding: utf-8 -*-
"""分块单元测试——页码贯通(缺陷②修复)、表格不跨父窗口、原子单元"""
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


def test_页码写入子块元数据():
    elements = [El('text', '第一节 内容A' * 50, 3), El('text', '第二节 内容B' * 50, 7)]
    children, parents = build_parent_child_chunks_from_elements(
        elements, doc_id=99, source='t.txt', tenant_id=1)
    assert children, '应产生子块'
    pages = {c.metadata.get('page') for c in children}
    assert pages == {3, 7}, f'页码应贯通到子块元数据, 实际: {pages}'


def test_表格整体不跨父窗口():
    big_table = '| a | b |\n|---|---|\n' + '\n'.join(f'| {i} | v{i} |' for i in range(200))
    elements = [El('table', big_table, 1), El('text', '后文' * 100, 2)]
    children, parents = build_parent_child_chunks_from_elements(
        elements, doc_id=98, source='t.txt', tenant_id=1)
    # 含表格的子块必须包含完整表头
    table_children = [c for c in children if '| a |' in c.page_content]
    assert table_children, '表格子块应存在'
    assert all('|---|' in c.page_content for c in table_children), '每个表格子块都应带表头(重复表头机制)'


def test_原子单元携带页码():
    units = _to_atomic_units([El('text', '内容' * 30, 5)], child_size=100)
    assert all(u.get('page') == 5 for u in units)


def test_空元素返回空():
    children, parents = build_parent_child_chunks_from_elements(
        [], doc_id=97, source='t.txt', tenant_id=1)
    assert children == [] and parents == {}
