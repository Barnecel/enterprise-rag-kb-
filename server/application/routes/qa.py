# -*- coding: utf-8 -*-
"""
问答路由模块 - RAG核心模块
处理知识库问答、文档检索等操作
集成LangChain和Chroma向量数据库
"""

from flask import Blueprint, request, jsonify, Response
from functools import wraps
import json
from application.routes.auth import verify_token
from application.utils.db_utils import execute_query, execute_insert, execute_update
from application.services.rag_service import get_rag_service

qa_bp = Blueprint('qa', __name__)


def _fetch_acl_doc_ids(user_id):
    """查询用户被显式授权的文档ID列表（ACL覆盖部门与密级）"""
    rows = execute_query("SELECT document_id FROM tb_document_acl WHERE user_id = %s", (user_id,))
    return [r['document_id'] for r in rows]


def _permission_context(current_user):
    """解析当前用户的检索权限上下文（admin 传 None 可见全部）"""
    is_admin = current_user.get('role') == 'admin'
    return {
        'tenant_id': None if is_admin else current_user.get('tenant_id'),
        'user_id': None if is_admin else current_user['user_id'],
        'clearance_level': None if is_admin else current_user.get('clearance_level', 1),
        'acl_doc_ids': [] if is_admin else _fetch_acl_doc_ids(current_user['user_id'])
    }


def token_required(f):
    """装饰器：验证JWT令牌"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'code': 401, 'message': '未提供有效令牌'}), 401

        token = auth_header[7:]
        payload = verify_token(token)
        if not payload:
            return jsonify({'code': 401, 'message': '令牌已过期或无效'}), 401

        kwargs['current_user'] = payload
        return f(*args, **kwargs)
    return decorated


def _resolve_conversation(user_id, conversation_id, question=''):
    """
    确保会话存在且属于当前用户。
    会话不存在或不属于该用户时，自动创建一个新会话（标题取首问前50字）。
    Returns: (conversation_id, title)
    """
    if conversation_id:
        row = execute_query(
            "SELECT id, title FROM tb_qa_conversation WHERE id = %s AND user_id = %s",
            (conversation_id, user_id)
        )
        if row:
            return conversation_id, row[0]['title']
    title = question.strip()[:50] or '新对话'
    new_id = execute_insert(
        "INSERT INTO tb_qa_conversation (user_id, title) VALUES (%s, %s)",
        (user_id, title)
    )
    return new_id, title


def _touch_conversation(conversation_id):
    """把会话更新时间推到最新，让最近使用的会话排在最前"""
    try:
        execute_update("UPDATE tb_qa_conversation SET updated_at = NOW() WHERE id = %s", (conversation_id,))
    except Exception as e:
        print(f"touch conversation failed: {e}")


def _load_history(conversation_id, limit=3):
    """取会话最近几轮问答(时间正序)，供查询改写指代消解与LLM语境理解"""
    if not conversation_id:
        return []
    try:
        rows = execute_query(
            "SELECT question, answer FROM tb_qa_history "
            "WHERE conversation_id = %s ORDER BY created_at DESC LIMIT %s",
            (conversation_id, limit)
        )
    except Exception:
        return []
    return [
        {'question': r.get('question') or '', 'answer': r.get('answer') or ''}
        for r in reversed(rows)
    ]


@qa_bp.route('/ask', methods=['POST'])
@token_required
def ask_question(current_user):
    """
    问答接口 - RAG系统的核心入口
    用户提问，系统检索相关文档后由LLM生成回答

    Args:
        current_user: 当前登录用户信息

    Request Body:
        question: 用户问题

    Returns:
        JSON: 回答结果和相关文档
    """
    data = request.get_json()
    question = data.get('question', '').strip()
    conversation_id = data.get('conversation_id')

    if not question:
        return jsonify({'code': 400, 'message': '问题不能为空'}), 400

    # 会话不存在则自动创建（标题取首问前50字）
    conv_id, _ = _resolve_conversation(current_user['user_id'], conversation_id, question)

    # 调用RAG服务进行处理 (admin可见全部，普通用户按部门+密级+ACL裁剪)
    ctx = _permission_context(current_user)
    result = get_rag_service().answer_question(
        question=question,
        user_id=current_user['user_id'],
        tenant_id=ctx['tenant_id'],
        clearance_level=ctx['clearance_level'],
        acl_doc_ids=ctx['acl_doc_ids'],
        history=_load_history(conv_id)
    )

    # 记录问答历史
    doc_ids = json.dumps(result.get('source_documents', []))
    history_sql = """
        INSERT INTO tb_qa_history (user_id, conversation_id, question, answer, documents, model_used, token_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    execute_insert(history_sql, (
        current_user['user_id'],
        conv_id,
        question,
        result.get('answer', ''),
        doc_ids,
        result.get('model_used', 'Qwen3.5-9B-MLX-4bit'),
        result.get('token_count', 0)
    ))
    _touch_conversation(conv_id)

    result['conversation_id'] = conv_id
    return jsonify({
        'code': 200,
        'message': '回答生成成功',
        'data': result
    })


@qa_bp.route('/ask/stream', methods=['POST'])
@token_required
def ask_question_stream(current_user):
    """
    流式问答接口(SSE)
    事件序列: {type:status,phase:retrieving} -> {type:status,phase:thinking,retrieved_docs,stats}
              -> {type:token,delta}* -> {type:done,source_documents,stats,model_used}
    """
    data = request.get_json() or {}
    question = data.get('question', '').strip()
    conversation_id = data.get('conversation_id')
    if not question:
        return jsonify({'code': 400, 'message': '问题不能为空'}), 400

    # 会话不存在则自动创建（标题取首问前50字）
    conv_id, _ = _resolve_conversation(current_user['user_id'], conversation_id, question)

    ctx = _permission_context(current_user)
    user_id = current_user['user_id']

    def generate():
        answer_parts = []
        source_docs = []
        model_used = 'Qwen3.5-9B-MLX-4bit'
        try:
            # 先发会话事件，让前端拿到 conversation_id 并刷新会话列表
            yield f"data: {json.dumps({'type': 'status', 'phase': 'conversation', 'conversation_id': conv_id}, ensure_ascii=False)}\n\n"
            for event in get_rag_service().answer_question_stream(
                question=question,
                user_id=user_id,
                tenant_id=ctx['tenant_id'],
                clearance_level=ctx['clearance_level'],
                acl_doc_ids=ctx['acl_doc_ids'],
                history=_load_history(conv_id)
            ):
                etype = event.get('type')
                if etype == 'status' and event.get('phase') == 'thinking':
                    source_docs = [d['id'] for d in event.get('retrieved_docs', []) if d.get('id')]
                elif etype == 'token':
                    answer_parts.append(event.get('delta', ''))
                elif etype == 'done':
                    source_docs = event.get('source_documents', source_docs)
                    model_used = event.get('model_used', model_used)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

        # 记录问答历史
        try:
            full_answer = ''.join(answer_parts)
            history_sql = """
                INSERT INTO tb_qa_history (user_id, conversation_id, question, answer, documents, model_used, token_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            execute_insert(history_sql, (
                user_id, conv_id, question, full_answer,
                json.dumps(list(dict.fromkeys(source_docs))),
                model_used,
                len(question) + len(full_answer)
            ))
            _touch_conversation(conv_id)
        except Exception as e:
            print(f"record qa history failed: {e}")

    return Response(generate(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache, no-transform',
        'X-Accel-Buffering': 'no',
        'Connection': 'keep-alive'
    })


@qa_bp.route('/history', methods=['GET'])
@token_required
def get_qa_history(current_user):
    """
    获取问答历史记录

    Query Params:
        page: 页码(默认1)
        limit: 每页数量(默认10)

    Returns:
        JSON: 问答历史列表
    """
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 10))
    offset = (page - 1) * limit

    # 普通用户只能查看自己的历史，管理员可以查看所有
    if current_user['role'] == 'admin':
        where_clause = ""
        count_sql = "SELECT COUNT(*) as total FROM tb_qa_history"
        params = []
    else:
        where_clause = "WHERE user_id = %s"
        count_sql = "SELECT COUNT(*) as total FROM tb_qa_history WHERE user_id = %s"
        params = [current_user['user_id']]

    # 获取总数
    count_result = execute_query(count_sql, params)
    total = count_result[0]['total'] if count_result else 0

    # 获取历史记录
    sql = f"""
        SELECT h.id, h.question, h.answer, h.documents, h.model_used, h.token_count, h.created_at,
               u.username, u.real_name
        FROM tb_qa_history h
        LEFT JOIN tb_user u ON h.user_id = u.id
        {where_clause}
        ORDER BY h.created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    history = execute_query(sql, params)

    # 转换数据格式
    for item in history:
        item['created_at'] = item['created_at'].strftime('%Y-%m-%d %H:%M:%S') if item['created_at'] else None
        # 解析文档ID列表
        if item['documents']:
            try:
                item['documents'] = json.loads(item['documents'])
            except:
                item['documents'] = []

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': {
            'list': history,
            'total': total,
            'page': page,
            'limit': limit
        }
    })


@qa_bp.route('/history/<int:history_id>', methods=['GET'])
@token_required
def get_history_detail(current_user, history_id):
    """
    获取单条问答历史详情

    Args:
        current_user: 当前登录用户信息
        history_id: 历史记录ID

    Returns:
        JSON: 历史记录详情
    """
    sql = """
        SELECT h.*, u.username, u.real_name
        FROM tb_qa_history h
        LEFT JOIN tb_user u ON h.user_id = u.id
        WHERE h.id = %s
    """
    result = execute_query(sql, (history_id,))

    if not result:
        return jsonify({'code': 404, 'message': '记录不存在'}), 404

    history = result[0]

    # 普通用户只能查看自己的记录
    if current_user['role'] != 'admin' and history['user_id'] != current_user['user_id']:
        return jsonify({'code': 403, 'message': '无权查看此记录'}), 403

    history['created_at'] = history['created_at'].strftime('%Y-%m-%d %H:%M:%S') if history['created_at'] else None

    # 解析文档ID列表
    if history['documents']:
        try:
            history['documents'] = json.loads(history['documents'])
        except:
            history['documents'] = []

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': history
    })


@qa_bp.route('/search', methods=['GET'])
@token_required
def search_documents(current_user):
    """
    文档检索接口 - 基于向量相似度检索

    Query Params:
        query: 检索关键词
        top_k: 返回数量(默认5)

    Returns:
        JSON: 相关文档列表
    """
    query = request.args.get('query', '').strip()
    top_k = int(request.args.get('top_k', 5))

    if not query:
        return jsonify({'code': 400, 'message': '检索关键词不能为空'}), 400

    # 调用RAG服务的检索功能 (admin可见全部，普通用户按部门+密级+ACL裁剪)
    ctx = _permission_context(current_user)
    documents = get_rag_service().retrieve_documents(
        query, top_k,
        tenant_id=ctx['tenant_id'],
        user_id=ctx['user_id'],
        clearance_level=ctx['clearance_level'],
        acl_doc_ids=ctx['acl_doc_ids']
    )

    return jsonify({
        'code': 200,
        'message': '检索成功',
        'data': {
            'query': query,
            'results': documents
        }
    })


@qa_bp.route('/reload_vectors', methods=['POST'])
@token_required
def reload_vectors(current_user):
    """
    重新加载向量库(仅管理员)
    将数据库中的文档重新向量化并存储到Chroma

    Returns:
        JSON: 重载结果
    """
    if current_user['role'] != 'admin':
        return jsonify({'code': 403, 'message': '权限不足，仅管理员可操作'}), 403

    result = get_rag_service().reload_all_documents()

    return jsonify({
        'code': 200,
        'message': '向量库重载完成',
        'data': result
    })


# ==================== 多会话管理 ====================

@qa_bp.route('/conversations', methods=['GET'])
@token_required
def get_conversations(current_user):
    """
    获取当前用户的会话列表（按最近使用排序）
    Returns:
        JSON: 会话列表（含消息数、最后一条问题）
    """
    sql = """
        SELECT c.id, c.title, c.created_at, c.updated_at,
               (SELECT COUNT(*) FROM tb_qa_history h WHERE h.conversation_id = c.id) AS message_count,
               (SELECT h.question FROM tb_qa_history h WHERE h.conversation_id = c.id ORDER BY h.created_at DESC LIMIT 1) AS last_question
        FROM tb_qa_conversation c
        WHERE c.user_id = %s
        ORDER BY c.updated_at DESC
    """
    rows = execute_query(sql, (current_user['user_id'],))
    for r in rows:
        r['created_at'] = r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else None
        r['updated_at'] = r['updated_at'].strftime('%Y-%m-%d %H:%M:%S') if r['updated_at'] else None
        r['last_question'] = r['last_question'] or ''
        r['message_count'] = r['message_count'] or 0
    return jsonify({'code': 200, 'message': '获取成功', 'data': rows})


@qa_bp.route('/conversations', methods=['POST'])
@token_required
def create_conversation(current_user):
    """新建会话"""
    data = request.get_json() or {}
    title = (data.get('title') or '新对话').strip()[:100] or '新对话'
    conv_id = execute_insert(
        "INSERT INTO tb_qa_conversation (user_id, title) VALUES (%s, %s)",
        (current_user['user_id'], title)
    )
    return jsonify({'code': 200, 'message': '创建成功', 'data': {'id': conv_id, 'title': title}})


@qa_bp.route('/conversations/<int:conversation_id>', methods=['PUT'])
@token_required
def rename_conversation(current_user, conversation_id):
    """重命名会话"""
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()[:100]
    if not title:
        return jsonify({'code': 400, 'message': '标题不能为空'}), 400
    rowcount = execute_update(
        "UPDATE tb_qa_conversation SET title = %s WHERE id = %s AND user_id = %s",
        (title, conversation_id, current_user['user_id'])
    )
    if rowcount == 0:
        return jsonify({'code': 404, 'message': '会话不存在'}), 404
    return jsonify({'code': 200, 'message': '更新成功'})


@qa_bp.route('/conversations/<int:conversation_id>', methods=['DELETE'])
@token_required
def delete_conversation(current_user, conversation_id):
    """删除会话及其历史记录"""
    rowcount = execute_update(
        "DELETE FROM tb_qa_conversation WHERE id = %s AND user_id = %s",
        (conversation_id, current_user['user_id'])
    )
    if rowcount == 0:
        return jsonify({'code': 404, 'message': '会话不存在'}), 404
    execute_update("DELETE FROM tb_qa_history WHERE conversation_id = %s", (conversation_id,))
    return jsonify({'code': 200, 'message': '删除成功'})


@qa_bp.route('/conversations/<int:conversation_id>/messages', methods=['GET'])
@token_required
def get_conversation_messages(current_user, conversation_id):
    """
    获取某个会话的全部消息（按时间正序，并补充参考文档标题）
    Returns:
        JSON: 消息列表 [{question, answer, documents:[{id,title}], created_at}]
    """
    conv = execute_query(
        "SELECT id FROM tb_qa_conversation WHERE id = %s AND user_id = %s",
        (conversation_id, current_user['user_id'])
    )
    if not conv:
        return jsonify({'code': 404, 'message': '会话不存在'}), 404

    rows = execute_query(
        """SELECT id, question, answer, documents, created_at
           FROM tb_qa_history
           WHERE conversation_id = %s
           ORDER BY created_at ASC""",
        (conversation_id,)
    )

    # 收集参考文档ID并一次性查标题
    doc_ids = set()
    for r in rows:
        r['created_at'] = r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else None
        r['doc_ids'] = []
        if r['documents']:
            try:
                ids = json.loads(r['documents'])
                r['doc_ids'] = [int(i) for i in ids if str(i).isdigit()]
            except Exception:
                r['doc_ids'] = []
        doc_ids.update(r['doc_ids'])
        del r['documents']

    doc_titles = {}
    if doc_ids:
        ids = list(doc_ids)
        fmt = ','.join(['%s'] * len(ids))
        docs = execute_query(f"SELECT id, title FROM tb_document WHERE id IN ({fmt})", ids)
        doc_titles = {d['id']: d['title'] for d in docs}

    for r in rows:
        r['documents'] = [{'id': i, 'title': doc_titles.get(i) or ''} for i in r['doc_ids']]
        del r['doc_ids']

    return jsonify({'code': 200, 'message': '获取成功', 'data': rows})