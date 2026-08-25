# -*- coding: utf-8 -*-
"""
复杂文档解析模块 (Document Parser)
统一将 txt/md/docx/doc/wps/rtf/ppt/pptx/pdf 解析为结构化 Element 流
- 表格 -> Markdown（保持行列结构）
- 图片 -> OCR 文本（RapidOCR，离线）
- 无文字图片 -> 视觉模型中文描述（oMLX 现有多模态模型，失败降级）
- 扫描页 -> 整页 OCR
- 永不抛异常，失败降级不阻塞入库
"""
import os
import re
import shutil
import subprocess
import threading
import tempfile
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

from utils.config_handler import config
from utils.logger_handler import logger

DOCUMENT_CONFIG = config.get_section('document')
PARSER_CONFIG = DOCUMENT_CONFIG.get('parser', {})
OCR_CONFIG = PARSER_CONFIG.get('ocr', {})
TABLE_CONFIG = PARSER_CONFIG.get('table', {})
IMAGE_CONFIG = PARSER_CONFIG.get('image', {})
CONVERT_CONFIG = PARSER_CONFIG.get('convert', {})

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class Element:
    """文档中的一个结构化元素"""
    kind: str           # 'text' | 'table' | 'image'
    text: str           # table->Markdown；image->OCR文本(+描述)；text->正文
    page: int = 0       # 1-based 页码（docx 为启发式）
    order: int = 0      # 全局序号，保证文档顺序
    extra: dict = field(default_factory=dict)

_CJK_GAP = re.compile(r'(?<=[\u4e00-\u9fff\u3000-\u303f\uff01-\uffee])\s+(?=[\u4e00-\u9fff\u3000-\u303f\uff01-\uffee])')


def _normalize_cjk_text(text: str) -> str:
    """OCR断行修复：合并汉字之间的空白/换行（"一名以\n上"→"一名以上"）。
    数字/拉丁字符旁的空格保留（避免"不满 16 周岁"黏连）。"""
    return _CJK_GAP.sub('', text or '')



# ---------------------------------------------------------------
# 惰性 OCR 单例（RapidOCR，模型内置在 wheel，离线可用）
# ---------------------------------------------------------------
_ocr_engine = None
_ocr_available = None          # None=未探测
_ocr_lock = threading.Lock()


def _get_ocr():
    global _ocr_engine, _ocr_available
    if _ocr_available is not None:
        return _ocr_engine if _ocr_available else None
    with _ocr_lock:
        if _ocr_available is not None:
            return _ocr_engine if _ocr_available else None
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()
            _ocr_available = True
            logger.info("RapidOCR initialized (ocr ready)")
        except Exception as e:
            _ocr_available = False
            logger.error(f"RapidOCR init failed: {e}. OCR disabled.")
    return _ocr_engine if _ocr_available else None


def _ocr_image(image_bytes: bytes) -> str:
    """对图片字节做 OCR，返回文本；失败/禁用返回空串"""
    if not OCR_CONFIG.get('enabled', True):
        return ''
    engine = _get_ocr()
    if engine is None:
        return ''
    try:
        import io
        import numpy as np
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        result, _ = engine(np.array(img))
        if not result:
            return ''
        lines = [ln[1] for ln in result if ln and len(ln) > 1 and ln[1]]
        return '\n'.join(lines)
    except Exception as e:
        logger.warning(f"OCR failed: {e}")
        return ''


def _caption_image(image_bytes: bytes, ocr_text: str) -> str:
    """无文字图片用视觉模型生成中文描述；失败返回空串"""
    if not IMAGE_CONFIG.get('caption_enabled', True):
        return ''
    min_len = int(IMAGE_CONFIG.get('caption_min_ocr_len', 20))
    if len(ocr_text.strip()) >= min_len:
        return ''
    try:
        from application.services.vision_captioner import caption_image
        return caption_image(image_bytes)
    except Exception as e:
        logger.warning(f"Vision caption call failed: {e}")
        return ''


# ---------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------
def parse_document(file_path: str, progress_cb=None) -> Tuple[List[Element], dict]:
    """按扩展名分派解析，永不抛异常。

    Args:
        progress_cb: 可选回调 progress_cb(done_pages, total_pages)，用于上报解析/OCR进度

    Returns:
        (elements, stats); elements 为空表示解析失败/无内容
    """
    stats = {'pages': 0, 'text_blocks': 0, 'table_count': 0, 'image_count': 0,
             'ocr_pages': 0, 'converted_from': None, 'warnings': []}
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ('.txt', '.md'):
            elements = _parse_text(file_path, stats)
        elif ext == '.docx':
            elements = _parse_docx(file_path, stats)
        elif ext in ('.doc', '.wps', '.rtf', '.ppt', '.pptx'):
            elements = _parse_via_libreoffice(file_path, ext, stats)
        elif ext == '.pdf':
            elements = _parse_pdf(file_path, stats, progress_cb=progress_cb)
        else:
            stats['warnings'].append(f"unsupported extension {ext}")
            return [], stats

        for i, el in enumerate(elements):
            el.order = i
        stats['text_blocks'] = sum(1 for e in elements if e.kind == 'text')
        stats['table_count'] = sum(1 for e in elements if e.kind == 'table')
        stats['image_count'] = sum(1 for e in elements if e.kind == 'image')
        for _el in elements:
            try:
                _el.text = _normalize_cjk_text(_el.text)
            except Exception:
                pass
        return elements, stats
    except Exception as e:
        stats['warnings'].append(f"parse failed: {e}")
        logger.error(f"parse_document failed for {file_path}: {e}")
        return [], stats


# ---------------------------------------------------------------
# 文本
# ---------------------------------------------------------------
def _parse_text(path: str, stats: dict) -> List[Element]:
    text = ''
    for enc in ('utf-8', 'gb18030'):
        try:
            with open(path, 'r', encoding=enc) as f:
                text = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if not text.strip():
        stats['warnings'].append('empty text file')
        return []
    stats['pages'] = 1
    return [Element('text', text, 1, 0)]


# ---------------------------------------------------------------
# DOCX（body 顺序迭代：段落/表格/图片）
# ---------------------------------------------------------------
_DRAWING_NS_A = '{http://schemas.openxmlformats.org/drawingml/2006/main}blip'
_DRAWING_NS_R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed'
_REL_NS_ID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'


def _extract_drawing_blob(drawing, doc) -> bytes:
    """从 w:drawing 提取图片字节"""
    for blip in drawing.iter(_DRAWING_NS_A):
        rid = blip.get(_DRAWING_NS_R)
        if rid:
            try:
                rel = doc.part.related_parts[rid]
                if hasattr(rel, 'blob') and getattr(rel, 'content_type', '').startswith('image'):
                    return rel.blob
            except Exception:
                continue
    return None


def _extract_pict_blob(pict, doc) -> bytes:
    """从 w:pict (VML) 提取图片字节"""
    for node in pict.iter():
        rid = node.get(_REL_NS_ID)
        if rid:
            try:
                rel = doc.part.related_parts[rid]
                if hasattr(rel, 'blob') and getattr(rel, 'content_type', '').startswith('image'):
                    return rel.blob
            except Exception:
                continue
    return None


def _table_to_markdown(table) -> str:
    """表格序列化为 Markdown（首行表头）；合并单元格去重（用底层 tc 元素身份，避免 _Cell 包装对象被 GC 复用）"""
    seen = set()
    rows = []
    for r in table.rows:
        cells = []
        for c in r.cells:
            tc = c._tc
            if tc in seen:
                cells.append('')
            else:
                seen.add(tc)
                cells.append(c.text.replace('|', '\\|').replace('\n', '<br>').strip())
        rows.append(cells)
    rows = [r for r in rows if any(x for x in r)]
    if not rows:
        return ''
    ncols = max(len(r) for r in rows)
    lines = []
    for i, r in enumerate(rows):
        cells = [(r[j] if j < len(r) else '') for j in range(ncols)]
        lines.append('| ' + ' | '.join(cells) + ' |')
        if i == 0:
            lines.append('| ' + ' | '.join(['---'] * ncols) + ' |')
    return '\n'.join(lines)


def _parse_docx(path: str, stats: dict) -> List[Element]:
    from docx import Document as DocxDocument
    from docx.text.paragraph import Paragraph
    from docx.table import Table
    from docx.oxml.ns import qn

    doc = DocxDocument(path)
    elements: List[Element] = []
    page = 1
    order = 0

    def handle_image(blob: bytes) -> None:
        nonlocal order
        ocr = _ocr_image(blob)
        cap = _caption_image(blob, ocr)
        parts = []
        if ocr:
            parts.append(f"[图片文字] {ocr}")
        if cap:
            parts.append(f"[图片描述] {cap}")
        if parts:
            elements.append(Element('image', '\n'.join(parts), page, order, {'ocr': bool(ocr)}))
            order += 1

    def handle_paragraph(p_el) -> None:
        nonlocal page, order
        p = Paragraph(p_el, doc)
        for br in p_el.iter(qn('w:br')):
            if br.get(qn('w:type')) == 'page':
                page += 1
        for drawing in p_el.iter(qn('w:drawing')):
            blob = _extract_drawing_blob(drawing, doc)
            if blob:
                handle_image(blob)
        for pict in p_el.iter(qn('w:pict')):
            blob = _extract_pict_blob(pict, doc)
            if blob:
                handle_image(blob)
        text = p.text.strip()
        if text:
            elements.append(Element('text', text, page, order))
            order += 1

    for child in doc.element.body.iterchildren():
        if child.tag == qn('w:p'):
            handle_paragraph(child)
        elif child.tag == qn('w:tbl'):
            table = Table(child, doc)
            md = _table_to_markdown(table)
            if md:
                elements.append(Element('table', md, page, order,
                                        {'rows': len(table.rows), 'cols': len(table.columns)}))
                order += 1
        elif child.tag == qn('w:sectPr'):
            page += 1

    stats['pages'] = page
    return elements


# ---------------------------------------------------------------
# PDF（PyMuPDF 文本 + pdfplumber 表格 + 扫描页 OCR）
# ---------------------------------------------------------------
def _table_md_from_cells(cells) -> str:
    rows = [r for r in (cells or []) if any((c or '').strip() for c in r)]
    if not rows:
        return ''
    ncols = max(len(r) for r in rows)

    def esc(i, r):
        v = (r[i] if i < len(r) else '') or ''
        return v.replace('|', '\\|').replace('\n', '<br>').strip()

    lines = []
    lines.append('| ' + ' | '.join(esc(i, rows[0]) for i in range(ncols)) + ' |')
    lines.append('| ' + ' | '.join(['---'] * ncols) + ' |')
    for r in rows[1:]:
        lines.append('| ' + ' | '.join(esc(i, r) for i in range(ncols)) + ' |')
    return '\n'.join(lines)


def _borderless_table_grid(page) -> Tuple[List[List[str]], tuple]:
    """保守的无框线表格探测（word 网格列聚类）。

    仅在有边框线检测(pdfplumber find_tables)返回空时作为兜底：
    将 word 按 y 聚成行、按 x0 聚成列，要求列在多行中稳定出现，
    再按 x0 最近列映射生成网格。误报率经测试很低（散文/英文整段不会命中）。

    Returns:
        (grid, bbox); grid=行x单元格的二维数组，bbox=(x0,y0,x1,y1)；非表格返回 (None, None)
    """
    words = page.get_text('words')
    if not words:
        return None, None
    words.sort(key=lambda w: (round(w[1], 1), w[0]))
    heights = [w[3] - w[1] for w in words]
    tol = max(3.0, (sum(heights) / len(heights)) * 0.6)
    rows = []
    for w in words:
        for r in rows:
            if abs(r['y0'] - w[1]) <= tol:
                r['words'].append(w)
                break
        else:
            rows.append({'y0': w[1], 'words': [w]})
    rows = [r for r in rows if len(r['words']) >= 2]
    if len(rows) < 3:
        return None, None

    x0s = sorted(w[0] for r in rows for w in r['words'])
    col_tol = max(4.0, (sum(w[2] - w[0] for r in rows for w in r['words']) / max(1, len(x0s))) * 0.9)
    clusters = []
    for x in x0s:
        if clusters and x - clusters[-1][-1] <= col_tol:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    nrows = len(rows)
    stable = [c for c in clusters
              if sum(any(c[0] - col_tol <= w[0] <= c[-1] + col_tol for w in r['words']) for r in rows)
              >= max(2, round(nrows * 0.4))]
    if len(stable) < 2:
        return None, None

    centers = [sum(c) / len(c) for c in stable]
    grid = []
    for r in rows:
        row_cells = [''] * len(stable)
        for w in sorted(r['words'], key=lambda w: w[0]):
            idx = min(range(len(centers)), key=lambda i: abs(centers[i] - w[0]))
            row_cells[idx] += w[4]
        if sum(1 for c in row_cells if c.strip()) >= 2:
            grid.append(row_cells)
    if len(grid) < 3:
        return None, None
    maxcol = max(i for row in grid for i, c in enumerate(row) if c.strip())
    grid = [row[:maxcol + 1] for row in grid]

    xs = [w[0] for r in rows for w in r['words']]
    ys = [w[1] for r in rows for w in r['words']]
    bbox = (min(xs), min(ys), max(w[2] for r in rows for w in r['words']), max(w[3] for r in rows for w in r['words']))
    return grid, bbox


def _parse_pdf(path: str, stats: dict, progress_cb=None) -> List[Element]:
    import fitz
    import pdfplumber

    elements: List[Element] = []
    order = 0
    min_chars = int(OCR_CONFIG.get('min_chars_empty_page', 20))
    max_ocr_pages = int(OCR_CONFIG.get('max_pages', 50))
    dpi = int(OCR_CONFIG.get('dpi', 200))
    ocr_count = 0

    doc = fitz.open(path)
    stats['pages'] = doc.page_count
    try:
        with pdfplumber.open(path) as pdf:
            for pno in range(doc.page_count):
                page = doc[pno]
                ppt = pdf.pages[pno]

                # 1. 表格（pdfplumber 有框线检测优先；无框线时 word 网格聚类兜底）
                table_infos = []
                try:
                    for t in ppt.find_tables():
                        md = _table_md_from_cells(t.extract())
                        if md:
                            table_infos.append((t.bbox, md))
                except Exception as e:
                    stats['warnings'].append(f"pdfplumber table err p{pno}: {e}")
                if not table_infos:
                    try:
                        grid, gbox = _borderless_table_grid(page)
                        if grid:
                            md = _table_md_from_cells(grid)
                            if md:
                                table_infos.append((gbox, md))
                                stats['warnings'].append(f"p{pno+1}: borderless table via column clustering")
                    except Exception as e:
                        stats['warnings'].append(f"borderless table err p{pno}: {e}")

                # 2. 文本块（剔除落在表格区域内的）
                blocks = []
                try:
                    for b in page.get_text('dict')['blocks']:
                        if b.get('type') != 0:
                            continue
                        txt = ''.join(sp['text'] for ln in b.get('lines', []) for sp in ln.get('spans', []))
                        if not txt.strip():
                            continue
                        br = fitz.Rect(b['bbox'])
                        if any(br.intersects(fitz.Rect(tb)) for tb, _ in table_infos):
                            continue
                        blocks.append(txt)
                except Exception:
                    blocks = []

                page_chars = sum(len(b) for b in blocks)
                if page_chars < min_chars and ocr_count < max_ocr_pages:
                    pix = page.get_pixmap(dpi=dpi)
                    ocr_text = _ocr_image(pix.tobytes('png'))
                    if ocr_text:
                        elements.append(Element('text', ocr_text, pno + 1, order, {'ocr': True}))
                        order += 1
                        ocr_count += 1
                        stats['ocr_pages'] += 1
                    continue  # 扫描页：不再单独处理文本/表格

                for txt in blocks:
                    elements.append(Element('text', txt, pno + 1, order))
                    order += 1
                for bbox, md in table_infos:
                    elements.append(Element('table', md, pno + 1, order))
                    order += 1

                # 页级进度上报（供批量任务进度条展示"第x/N页"）
                if progress_cb:
                    try:
                        progress_cb(pno + 1, doc.page_count, 'parse')
                    except Exception:
                        pass
    finally:
        doc.close()
    return elements


# ---------------------------------------------------------------
# LibreOffice 转换（doc/wps/rtf -> docx；ppt/pptx -> pdf 复用 PDF 解析）
# ---------------------------------------------------------------
_convert_lock = threading.Lock()


def _parse_via_libreoffice(path: str, ext: str, stats: dict) -> List[Element]:
    if not CONVERT_CONFIG.get('enabled', True):
        stats['warnings'].append(f"conversion disabled, skip {ext}")
        return []
    soffice = (CONVERT_CONFIG.get('soffice_bin')
               or shutil.which('soffice')
               or '/Applications/LibreOffice.app/Contents/MacOS/soffice')
    profile = os.path.join(SERVER_DIR, CONVERT_CONFIG.get('profile_dir', 'data/lo_profile'))
    tmp = tempfile.mkdtemp(prefix='lo_conv_')
    try:
        with _convert_lock:
            target = 'pdf' if ext in ('.ppt', '.pptx') else 'docx'
            cmd = [soffice, '--headless', '--norestore', '--nolockcheck', '--nologo',
                   f'-env:UserInstallation=file://{profile}',
                   '--convert-to', target, '--outdir', tmp, path]
            res = subprocess.run(cmd, timeout=int(CONVERT_CONFIG.get('timeout_seconds', 120)),
                                 capture_output=True)
        if res.returncode != 0:
            stats['warnings'].append(f"soffice convert failed: {res.stderr.decode('utf-8', 'ignore')[:200]}")
            return []
        suffix = '.' + target
        out = next((os.path.join(tmp, f) for f in os.listdir(tmp)
                    if f.lower().endswith(suffix)), None)
        if not out:
            stats['warnings'].append(f"soffice produced no {target} for {ext}")
            return []
        elements = _parse_pdf(out, stats) if target == 'pdf' else _parse_docx(out, stats)
        stats['converted_from'] = ext.lstrip('.')
        logger.info(f"LibreOffice converted {ext} -> {target}: {len(elements)} elements")
        return elements
    except Exception as e:
        stats['warnings'].append(f"libreoffice convert err: {e}")
        return []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
