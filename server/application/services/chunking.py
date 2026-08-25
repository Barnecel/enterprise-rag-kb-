# -*- coding: utf-8 -*-
"""
父子分块模块 (Parent-Child Indexing)
- 父窗口(大块)：用于LLM作答上下文
- 子块(小块)：用于检索召回，精度更高
子块携带 doc_id / parent_id / tenant_id 等元数据
"""
import uuid
from typing import List, Dict, Tuple, Any, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from utils.config_handler import config
from utils.logger_handler import logger

DOCUMENT_CONFIG = config.get_section('document')
RAG_CONFIG = config.get_section('rag')
PARENT_CHILD_ENABLED = RAG_CONFIG.get('parent_child', {}).get('enabled', True)


def build_parent_child_chunks(
    document: Any,
    doc_id: int,
    source: str,
    tenant_id: int = 1,
    doc_level: str = 'public',
    min_level: int = 1,
    owner_id: Optional[int] = None
) -> Tuple[List[Document], Dict[str, str]]:
    """
    将文档切分为父子块结构

    Args:
        document: LangChain Document对象
        doc_id: 数据库文档ID
        source: 文档来源标识(文件名)
        tenant_id: 所属租户ID
        doc_level: 文档级别(public/private)，权限过滤用
        min_level: 文档最低密级(1公开/2内部/3机密/4绝密)
        owner_id: 上传者用户ID

    Returns:
        (child_chunks, parent_map)
        child_chunks: 用于检索的小块(Document，带元数据)
        parent_map: {parent_id: 父窗口全文}
    """
    text = document.page_content or ''
    parent_map: Dict[str, str] = {}
    child_chunks: List[Document] = []

    if not text:
        logger.warning(f"Document {doc_id} has empty content")
        return child_chunks, parent_map

    if not PARENT_CHILD_ENABLED:
        # 兜底：单层分块（无父子结构）
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=DOCUMENT_CONFIG['chunk_size'],
            chunk_overlap=DOCUMENT_CONFIG['chunk_overlap'],
            length_function=len
        )
        chunks = splitter.split_text(text)
        for i, chunk in enumerate(chunks):
            parent_id = str(uuid.uuid4())
            parent_map[parent_id] = chunk
            child_chunks.append(Document(
                page_content=chunk,
                metadata={
                    'doc_id': doc_id,
                    'parent_id': parent_id,
                    'source': source,
                    'tenant_id': tenant_id,
                    'chunk_index': i,
                    'doc_level': doc_level,
                    'min_level': min_level,
                    'owner_id': owner_id
                }
            ))
        return child_chunks, parent_map

    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=DOCUMENT_CONFIG['parent_chunk_size'],
        chunk_overlap=DOCUMENT_CONFIG['parent_chunk_overlap'],
        length_function=len
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=DOCUMENT_CONFIG['child_chunk_size'],
        chunk_overlap=DOCUMENT_CONFIG['child_chunk_overlap'],
        length_function=len
    )

    parents = parent_splitter.split_text(text)
    chunk_index = 0
    for parent_text in parents:
        parent_id = str(uuid.uuid4())
        parent_map[parent_id] = parent_text

        children = child_splitter.split_text(parent_text)
        if not children:
            children = [parent_text]

        for child in children:
            child_chunks.append(Document(
                page_content=child,
                metadata={
                    'doc_id': doc_id,
                    'parent_id': parent_id,
                    'source': source,
                    'tenant_id': tenant_id,
                    'chunk_index': chunk_index,
                    'doc_level': doc_level,
                    'min_level': min_level,
                    'owner_id': owner_id
                }
            ))
            chunk_index += 1

    logger.info(f"Document {doc_id} split into {len(parents)} parents / {len(child_chunks)} children")
    return child_chunks, parent_map


# ---------------------------------------------------------------
# 元素化切块（document_parser 的 Element 流 → 父子块）
# 关键保证：表格单元在父窗口与子块中都保持完整（表格整体或按行拆分组内不切断）
# ---------------------------------------------------------------
_PARSER_TABLE = DOCUMENT_CONFIG.get('parser', {}).get('table', {})
TABLE_MAX_CHARS = int(_PARSER_TABLE.get('max_chars', 300))
TABLE_MAX_ROWS = int(_PARSER_TABLE.get('max_rows_per_group', 10))


def _split_table_pieces(md: str) -> List[str]:
    """大表格按行拆分为多段，每段重复表头，保证每段 ≤ max_chars 且行数 ≤ max_rows。"""
    lines = md.split('\n')
    if len(lines) < 3 or len(md) <= TABLE_MAX_CHARS:
        return [md]
    header, sep, data = lines[0], lines[1], lines[2:]
    pieces, cur, cur_len = [], [header, sep], len(header) + len(sep)
    for row in data:
        if len(cur) >= 3 and (cur_len + len(row) + 1 > TABLE_MAX_CHARS
                              or (len(cur) - 2) >= TABLE_MAX_ROWS):
            pieces.append('\n'.join(cur))
            cur, cur_len = [header, sep], len(header) + len(sep)
        cur.append(row)
        cur_len += len(row) + 1
    if len(cur) >= 3:
        pieces.append('\n'.join(cur))
    return pieces


def _to_atomic_units(elements: List[Any], child_size: int) -> List[Dict[str, str]]:
    """Element 流 → 原子单元（text/table）。

    - 连续 text（含 image 的 OCR/描述文本）累积到 ~child_size 合并为一个文本单元
    - table 整体一个单元；超过 max_chars 按行拆分为多段（每段重复表头）
    - 无文本的 image 跳过
    """
    units: List[Dict[str, Any]] = []
    buf: List[str] = []
    buf_len = 0
    buf_page = None

    def flush():
        nonlocal buf, buf_len, buf_page
        if buf:
            units.append({'kind': 'text', 'text': '\n\n'.join(buf), 'page': buf_page})
            buf, buf_len, buf_page = [], 0, None

    for el in elements:
        kind = getattr(el, 'kind', 'text')
        text = getattr(el, 'text', '') or ''
        page = getattr(el, 'page', None)
        if kind == 'table':
            flush()
            for piece in _split_table_pieces(text.strip()):
                if piece.strip():
                    units.append({'kind': 'table', 'text': piece, 'page': page})
        elif kind == 'image':
            if text.strip():
                if buf and buf_len + len(text) > child_size:
                    flush()
                if buf_page is None:
                    buf_page = page
                buf.append(text)
                buf_len += len(text)
        else:  # text
            if not text.strip():
                continue
            if len(text) >= child_size:
                flush()
                for i in range(0, len(text), child_size):
                    units.append({'kind': 'text', 'text': text[i:i + child_size], 'page': page})
            else:
                if buf and buf_len + len(text) > child_size:
                    flush()
                if buf_page is None:
                    buf_page = page
                buf.append(text)
                buf_len += len(text)
    flush()
    return units


def build_parent_child_chunks_from_elements(
    elements: List[Any],
    doc_id: int,
    source: str,
    tenant_id: int = 1,
    doc_level: str = 'public',
    min_level: int = 1,
    owner_id: Optional[int] = None
) -> Tuple[List[Document], Dict[str, str]]:
    """
    将解析后的 Element 流构建为父子块结构（元素化切块）。

    - 原子单元顺序打包进父窗口（≤ parent_size），任何单元不跨父窗口 → 表格永不被切
    - 父窗口 parent_map 内联表格 Markdown，命中表格子块时作答上下文含完整表格
    - 子块：文本单元用现有 RecursiveCharacterTextSplitter 切分，表格单元原样保留

    Args:
        elements: document_parser.parse_document 返回的 Element 列表
        doc_id / source / tenant_id: 同 build_parent_child_chunks
    Returns:
        (child_chunks, parent_map)
    """
    child_size = int(DOCUMENT_CONFIG['child_chunk_size'])
    child_overlap = int(DOCUMENT_CONFIG['child_chunk_overlap'])
    parent_size = int(DOCUMENT_CONFIG['parent_chunk_size'])

    units = _to_atomic_units(elements, child_size)
    if not units:
        logger.warning(f"Elements of doc {doc_id} produced no atomic units")
        return [], {}

    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=child_size, chunk_overlap=child_overlap, length_function=len
    )

    # 1. 打包父窗口：顺序累加，超限即闭合（单元本身 ≤ parent_size）
    windows: List[List[Dict[str, str]]] = []
    cur, cur_len = [], 0
    for u in units:
        l = len(u['text'])
        if cur and cur_len + l > parent_size:
            windows.append(cur)
            cur, cur_len = [u], l
        else:
            cur.append(u)
            cur_len += l
    if cur:
        windows.append(cur)

    # 2. 每个父窗口 → parent_map + 子块
    parent_map: Dict[str, str] = {}
    child_chunks: List[Document] = []
    chunk_index = 0
    for unit_list in windows:
        parent_id = str(uuid.uuid4())
        parent_map[parent_id] = '\n\n'.join(u['text'] for u in unit_list)
        for u in unit_list:
            children = [u['text']] if u['kind'] == 'table' else (child_splitter.split_text(u['text']) or [u['text']])
            for child in children:
                child_chunks.append(Document(
                    page_content=child,
                    metadata={
                        'doc_id': doc_id,
                        'parent_id': parent_id,
                        'source': source,
                        'tenant_id': tenant_id,
                        'chunk_index': chunk_index,
                        'doc_level': doc_level,
                        'min_level': min_level,
                        'owner_id': owner_id,
                        'page': u.get('page')
                    }
                ))
                chunk_index += 1

    logger.info(f"Doc {doc_id} -> {len(windows)} parents / {len(child_chunks)} children (elements={len(elements)})")
    return child_chunks, parent_map
