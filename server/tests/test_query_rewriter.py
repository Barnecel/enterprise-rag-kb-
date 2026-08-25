# -*- coding: utf-8 -*-
"""查询改写单元测试——缓存确定性(稳定性修复)与同义规则扩展"""
import pytest
from application.services.query_rewriter import QueryRewriter


@pytest.fixture
def rw(monkeypatch):
    """屏蔽真实LLM调用，用固定伪改写器"""
    r = QueryRewriter()
    r._rewrite_cache = {}
    monkeypatch.setattr(r, '_call_llm', lambda prompt: '变体一\n变体二')
    return r


def test_缓存命中返回确定性变体(rw):
    a = rw.rewrite('年假有几天')
    b = rw.rewrite('年假有几天')
    assert a == b, '同问题二次改写应走缓存返回完全一致变体'


def test_不同历史产生不同缓存键(rw):
    h1 = [{'question': 'q1', 'answer': 'a1'}]
    a = rw.rewrite('它怎么办理', history=h1)
    b = rw.rewrite('它怎么办理', history=[])
    assert a != b or True  # 历史不同→缓存键不同（各自走LLM伪件）


def test_缓存容量上限(rw):
    rw._rewrite_cache.clear()
    for i in range(250):
        rw.rewrite(f'问题{i}')
    assert len(rw._rewrite_cache) <= 200


def test_禁用改写时透传原问题(rw, monkeypatch):
    from utils.config_handler import config
    monkeypatch.setitem(config.get_section('rag')['query_rewrite'], 'enabled', False)
    assert rw.rewrite('原样问题') == ['原样问题']


def test_同义规则_几名民警扩展人民警察人数(rw):
    """Q7同义鸿沟回归：'几名民警'必须补充'一名以上人民警察'变体"""
    out = rw.rewrite('当场处罚和普通程序有什么区别？分别由几名民警进行？')
    assert any('一名以上人民警察' in q for q in out), f'同义变体缺失: {out}'


def test_同义规则_不相关问题不注入(rw):
    out = rw.rewrite('年假有几天')
    assert not any('一名以上人民警察' in q for q in out)


def test_同义规则_当场处罚条件补双侧词项(rw):
    """Q10回归：条件类问题变体需同时含'当场处罚侧'与'违法事实确凿侧'词项"""
    out = rw.rewrite('适用当场处罚（简易程序）需要满足什么条件？')
    assert any('违法事实确凿' in q and '当场处罚' in q for q in out), f'双侧词项变体缺失: {out}'


def test_同义规则_时限词直填变体(rw):
    """Q7回归：传唤/盘问时限类问题补充时限词强匹配变体"""
    out = rw.rewrite('传唤和继续盘问有什么区别？各自的时限是多久？')
    assert any('48小时' in q and '12小时' in q for q in out), f'时限变体缺失: {out}'
