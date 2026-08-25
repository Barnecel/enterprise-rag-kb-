# -*- coding: utf-8 -*-
"""OCR断行修复(CJK规范化)单元测试——第14号发现的根因修复"""
import pytest
from application.services.document_parser import _normalize_cjk_text


def test_汉字间换行合并():
    assert _normalize_cjk_text('一名以\n上人民警察') == '一名以上人民警察'


def test_汉字间空格合并():
    assert _normalize_cjk_text('治安 调解 的原则') == '治安调解的原则'


def test_数字旁空格保留():
    assert _normalize_cjk_text('不满 16 周岁') == '不满 16 周岁'


def test_英文单词间空格保留():
    assert _normalize_cjk_text('OBD-II On Board Diagnostics') == 'OBD-II On Board Diagnostics'


def test_混合内容():
    src = '询问查证时间不得超过八小时；涉案人数众多。\n身份不明的，不得超过十二小时'
    assert _normalize_cjk_text(src) == '询问查证时间不得超过八小时；涉案人数众多。身份不明的，不得超过十二小时'


def test_空安全():
    assert _normalize_cjk_text('') == ''
    assert _normalize_cjk_text(None) == ''
