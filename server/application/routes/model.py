# -*- coding: utf-8 -*-
"""
模型API接入管理路由
接入局域网/互联网的OpenAI兼容端点（oMLX/LM Studio/Ollama/vLLM/DeepSeek/通义/Kimi/OpenAI...）
- 每个角色(llm/embedding)同时仅一个启用配置；未启用任何配置时回退YAML
- 切换LLM：热生效并清空答案缓存
- 切换嵌入：先探测维度，不兼容则要求重建向量库后才真正生效（防静默污染）
"""

import time
import functools
import threading

from flask import Blueprint, request, jsonify

from application.routes.auth import verify_token
from application.utils.db_utils import execute_query, execute_insert, execute_update
from application.services.rag_service import get_rag_service, OMLXEmbeddings

model_bp = Blueprint('model', __name__)

# 向量库重建任务状态（简易单例）
_rebuild_state = {'status': 'idle', 'detail': ''}


def token_admin(f):
    """鉴权+管理员校验（verify_token是工具函数，需在此包装成装饰器）"""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        token = auth[7:] if auth.startswith('Bearer ') else ''
        user = verify_token(token) if token else None
        if not user:
            return jsonify({'code': 401, 'message': '未登录或令牌过期'}), 401
        if user.get('role') != 'admin':
            return jsonify({'code': 403, 'message': '权限不足，仅管理员可操作'}), 403
        return f(current_user=user, *args, **kwargs)
    return decorated


def _mask(key: str) -> str:
    if not key:
        return ''
    return key[:4] + '****' + key[-4:] if len(key) > 8 else '****'


def _row_public(r: dict) -> dict:
    r = dict(r)
    r['api_key_masked'] = _mask(r.get('api_key') or '')
    r.pop('api_key', None)
    return r


@model_bp.route('/list', methods=['GET'])

@token_admin
def list_models(current_user):
    rows = execute_query("SELECT * FROM tb_model_config ORDER BY model_type, is_active DESC, id")
    return jsonify({'code': 200, 'data': [_row_public(r) for r in rows]})


def _validate_payload(data, need_model_name=True):
    name = (data.get('name') or '').strip()
    mtype = data.get('model_type')
    api_base = (data.get('api_base') or '').strip().rstrip('/')
    api_key = (data.get('api_key') or '').strip()
    model_name = (data.get('model_name') or '').strip()
    remark = (data.get('remark') or '').strip()[:255] or None
    if not name:
        return None, '名称不能为空'
    if mtype not in ('llm', 'embedding'):
        return None, 'model_type 必须是 llm 或 embedding'
    if not api_base.startswith(('http://', 'https://')):
        return None, 'api_base 必须以 http(s):// 开头'
    if need_model_name and not model_name:
        return None, '模型名不能为空'
    return {'name': name, 'model_type': mtype, 'provider': 'openai_compatible',
            'api_base': api_base, 'api_key': api_key,
            'model_name': model_name, 'remark': remark}, None


@model_bp.route('', methods=['POST'])

@token_admin
def add_model(current_user):
    cfg, err = _validate_payload(request.get_json() or {})
    if err:
        return jsonify({'code': 400, 'message': err}), 400
    # 同类型如为首条且无启用项 → 自动启用，避免空档
    active = execute_query(
        "SELECT COUNT(*) AS n FROM tb_model_config WHERE model_type=%s AND is_active=1",
        (cfg['model_type'],))
    auto_active = 1 if active[0]['n'] == 0 else 0
    mid = execute_insert(
        "INSERT INTO tb_model_config (name, model_type, provider, api_base, api_key, model_name, is_active, remark) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (cfg['name'], cfg['model_type'], cfg['provider'], cfg['api_base'],
         cfg['api_key'], cfg['model_name'], auto_active, cfg['remark']))
    return jsonify({'code': 201, 'message': '已添加', 'data': {'id': mid, 'auto_active': bool(auto_active)}}), 201


@model_bp.route('/<int:model_id>', methods=['PUT'])

@token_admin
def update_model(current_user, model_id):
    cfg, err = _validate_payload(request.get_json() or {})
    if err:
        return jsonify({'code': 400, 'message': err}), 400
    n = execute_update(
        "UPDATE tb_model_config SET name=%s, api_base=%s, api_key=%s, model_name=%s, remark=%s "
        "WHERE id=%s",
        (cfg['name'], cfg['api_base'], cfg['api_key'], cfg['model_name'],
         cfg['remark'], model_id))
    if not n:
        return jsonify({'code': 404, 'message': '配置不存在'}), 404
    # 若该条正处于启用状态，同步刷新运行时
    row = execute_query("SELECT model_type FROM tb_model_config WHERE id=%s", (model_id,))[0]
    svc = get_rag_service()
    applied = svc.apply_active_models()
    _ = row, applied
    return jsonify({'code': 200, 'message': '已更新并同步运行时'})


@model_bp.route('/<int:model_id>', methods=['DELETE'])

@token_admin
def delete_model(current_user, model_id):
    n = execute_update("DELETE FROM tb_model_config WHERE id=%s", (model_id,))
    if not n:
        return jsonify({'code': 404, 'message': '配置不存在'}), 404
    get_rag_service().apply_active_models()  # 若删的是启用项，回退YAML
    return jsonify({'code': 200, 'message': '已删除'})


@model_bp.route('/<int:model_id>/test', methods=['POST'])

@token_admin
def test_model(current_user, model_id):
    """连通性测试：LLM发5token试生成；嵌入探测维度。返回延迟与样例"""
    rows = execute_query("SELECT * FROM tb_model_config WHERE id=%s", (model_id,))
    if not rows:
        return jsonify({'code': 404, 'message': '配置不存在'}), 404
    r = rows[0]
    t0 = time.time()
    try:
        if r['model_type'] == 'llm':
            import requests as _rq
            resp = _rq.post(
                f"{r['api_base']}/chat/completions",
                headers={'Authorization': f"Bearer {r['api_key'] or 'dummy'}"},
                json={'model': r['model_name'], 'max_tokens': 5,
                      'messages': [{'role': 'user', 'content': '回复OK'}]},
                timeout=20)
            j = resp.json()
            if resp.status_code != 200:
                return jsonify({'code': 502, 'ok': False,
                                'error': j.get('error', {}).get('message', resp.text[:120])})
            sample = (j['choices'][0]['message'].get('content') or '').strip()
            return jsonify({'code': 200, 'data': {
                'ok': True, 'latency_ms': int((time.time()-t0)*1000),
                'sample': sample[:40]}})
        else:
            tmp = OMLXEmbeddings(api_base=r['api_base'], api_key=r['api_key'] or '',
                                 model_name=r['model_name'])
            dim = len(tmp.embed_documents(['连接测试'])[0])
            return jsonify({'code': 200, 'data': {
                'ok': True, 'latency_ms': int((time.time()-t0)*1000),
                'dim': dim}})
    except Exception as e:
        return jsonify({'code': 502, 'ok': False,
                        'latency_ms': int((time.time()-t0)*1000),
                        'error': str(e)[:160]})


@model_bp.route('/<int:model_id>/activate', methods=['POST'])

@token_admin
def activate_model(current_user, model_id):
    rows = execute_query("SELECT * FROM tb_model_config WHERE id=%s", (model_id,))
    if not rows:
        return jsonify({'code': 404, 'message': '配置不存在'}), 404
    r = rows[0]

    # 同类型互斥启用
    execute_update("UPDATE tb_model_config SET is_active=0 WHERE model_type=%s", (r['model_type'],))
    execute_update("UPDATE tb_model_config SET is_active=1 WHERE id=%s", (model_id,))

    svc = get_rag_service()
    cfg = {'api_base': r['api_base'], 'api_key': r['api_key'], 'model_name': r['model_name']}

    if r['model_type'] == 'llm':
        svc.hot_swap_llm(cfg)
        execute_update("UPDATE tb_model_config SET pending_rebuild=0 WHERE id=%s", (model_id,))
        return jsonify({'code': 200, 'message': f"LLM已切换为「{r['name']}」，缓存已清空",
                        'data': {'swapped': True}})

    res = svc.hot_swap_embedding(cfg)
    if res['swapped']:
        execute_update("UPDATE tb_model_config SET pending_rebuild=0 WHERE id=%s", (model_id,))
        msg = f"嵌入模型已切换为「{r['name']}」(维度{res['new_dim']})"
    else:
        execute_update("UPDATE tb_model_config SET pending_rebuild=1 WHERE id=%s", (model_id,))
        msg = (f"维度不兼容({res['old_dim']}→{res['new_dim']})，"
               f"已记录待重建。请点击「重建向量库」完成切换")
    return jsonify({'code': 200, 'message': msg, 'data': res})


@model_bp.route('/rebuild_vectors', methods=['POST'])

@token_admin
def rebuild_vectors(current_user):
    """全量重建向量库（嵌入模型更换后的必经步骤），后台线程执行"""
    if _rebuild_state['status'] == 'running':
        return jsonify({'code': 409, 'message': '重建已在进行中'}), 409

    def _job():
        try:
            _rebuild_state.update(status='running', detail='')
            svc = get_rag_service()
            svc._initialize_embeddings()          # 应用新嵌入配置
            result = svc.reload_all_documents()   # 清空集合+BM25并全量重嵌
            execute_update("UPDATE tb_model_config SET pending_rebuild=0 "
                           "WHERE model_type='embedding' AND is_active=1")
            _rebuild_state.update(status='done', detail=str(result))
        except Exception as e:
            _rebuild_state.update(status='failed', detail=str(e)[:200])

    threading.Thread(target=_job, daemon=True).start()
    return jsonify({'code': 200, 'message': '重建任务已启动'})


@model_bp.route('/rebuild_status', methods=['GET'])

@token_admin
def rebuild_status(current_user):
    return jsonify({'code': 200, 'data': _rebuild_state})


@model_bp.route('/active', methods=['GET'])

@token_admin
def active_runtime(current_user):
    """当前运行时实际生效的模型（含YAML回退情况）"""
    from application.services.rag_service import LLM_CONFIG, EMBEDDING_CONFIG
    return jsonify({'code': 200, 'data': {
        'llm': {'api_base': LLM_CONFIG.get('api_base'), 'model_name': LLM_CONFIG.get('model_name')},
        'embedding': {'api_base': EMBEDDING_CONFIG.get('api_base'), 'model_name': EMBEDDING_CONFIG.get('model_name')}
    }})
