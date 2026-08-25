# -*- coding: utf-8 -*-
"""
管理员后台路由模块
处理系统统计、数据管理等功能
"""

from flask import Blueprint, request, jsonify
from functools import wraps
from datetime import datetime, timedelta
from application.routes.auth import verify_token
from application.utils.db_utils import execute_query
from application.services.rag_service import get_rag_service

admin_bp = Blueprint('admin', __name__)


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

        if payload['role'] != 'admin':
            return jsonify({'code': 403, 'message': '权限不足，仅管理员可访问'}), 403

        kwargs['current_user'] = payload
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/dashboard', methods=['GET'])
@token_required
def get_dashboard_stats(current_user):
    """
    获取仪表盘统计数据

    Returns:
        JSON: 统计数据包括用户数、文档数、问答数等
    """
    stats = {}

    # 用户总数
    user_sql = "SELECT COUNT(*) as total FROM tb_user"
    result = execute_query(user_sql)
    stats['total_users'] = result[0]['total'] if result else 0

    # 管理员数量
    admin_sql = "SELECT COUNT(*) as total FROM tb_user WHERE role = 'admin'"
    result = execute_query(admin_sql)
    stats['admin_count'] = result[0]['total'] if result else 0

    # 普通用户数量
    normal_sql = "SELECT COUNT(*) as total FROM tb_user WHERE role = 'user'"
    result = execute_query(normal_sql)
    stats['normal_user_count'] = result[0]['total'] if result else 0

    # 文档总数
    doc_sql = "SELECT COUNT(*) as total FROM tb_document"
    result = execute_query(doc_sql)
    stats['total_documents'] = result[0]['total'] if result else 0

    # 已完成处理的文档数
    completed_sql = "SELECT COUNT(*) as total FROM tb_document WHERE status = 'completed'"
    result = execute_query(completed_sql)
    stats['completed_documents'] = result[0]['total'] if result else 0

    # 分类总数
    cat_sql = "SELECT COUNT(*) as total FROM tb_category"
    result = execute_query(cat_sql)
    stats['total_categories'] = result[0]['total'] if result else 0

    # 问答记录总数
    qa_sql = "SELECT COUNT(*) as total FROM tb_qa_history"
    result = execute_query(qa_sql)
    stats['total_questions'] = result[0]['total'] if result else 0

    # 总token消耗
    token_sql = "SELECT SUM(token_count) as total FROM tb_qa_history"
    result = execute_query(token_sql)
    stats['total_tokens'] = result[0]['total'] if result and result[0]['total'] else 0

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': stats
    })


@admin_bp.route('/statistics/daily', methods=['GET'])
@token_required
def get_daily_statistics(current_user):
    """
    获取近30天每日统计数据

    Query Params:
        days: 统计天数(默认30)

    Returns:
        JSON: 每日统计数据列表
    """
    days = int(request.args.get('days', 30))

    # 转换日期格式
    date_list = []
    for i in range(days - 1, -1, -1):
        date_list.append((datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'))

    result_list = []
    for date in date_list:
        # 每日新增用户
        user_sql = "SELECT COUNT(*) as count FROM tb_user WHERE DATE(created_at) = %s"
        user_result = execute_query(user_sql, (date,))
        user_count = user_result[0]['count'] if user_result else 0

        # 每日新增文档
        doc_sql = "SELECT COUNT(*) as count FROM tb_document WHERE DATE(created_at) = %s"
        doc_result = execute_query(doc_sql, (date,))
        doc_count = doc_result[0]['count'] if doc_result else 0

        # 每日问答数
        qa_sql = "SELECT COUNT(*) as count FROM tb_qa_history WHERE DATE(created_at) = %s"
        qa_result = execute_query(qa_sql, (date,))
        qa_count = qa_result[0]['count'] if qa_result else 0

        result_list.append({
            'date': date,
            'new_users': user_count,
            'new_documents': doc_count,
            'questions': qa_count
        })

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': result_list
    })


@admin_bp.route('/statistics/category', methods=['GET'])
@token_required
def get_category_statistics(current_user):
    """
    获取各分类下的文档数量统计

    Returns:
        JSON: 分类统计列表
    """
    sql = """
        SELECT c.id, c.name, c.parent_id,
               COUNT(d.id) as document_count
        FROM tb_category c
        LEFT JOIN tb_document d ON c.id = d.category_id
        GROUP BY c.id, c.name, c.parent_id
        ORDER BY document_count DESC
    """
    result = execute_query(sql)

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': result
    })


@admin_bp.route('/statistics/user_activity', methods=['GET'])
@token_required
def get_user_activity(current_user):
    """
    获取用户活跃度统计(问答数量前10的用户)

    Query Params:
        limit: 返回数量(默认10)

    Returns:
        JSON: 用户活跃度列表
    """
    limit = int(request.args.get('limit', 10))

    sql = """
        SELECT u.id, u.username, u.real_name, u.role,
               COUNT(h.id) as question_count
        FROM tb_user u
        LEFT JOIN tb_qa_history h ON u.id = h.user_id
        GROUP BY u.id, u.username, u.real_name, u.role
        ORDER BY question_count DESC
        LIMIT %s
    """
    result = execute_query(sql, (limit,))

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': result
    })


@admin_bp.route('/statistics/token_usage', methods=['GET'])
@token_required
def get_token_usage(current_user):
    """
    获取Token消耗统计

    Query Params:
        days: 统计天数(默认7)

    Returns:
        JSON: Token消耗统计数据
    """
    days = int(request.args.get('days', 7))

    sql = """
        SELECT DATE(created_at) as date,
               COUNT(*) as question_count,
               SUM(token_count) as total_tokens,
               AVG(token_count) as avg_tokens
        FROM tb_qa_history
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
        GROUP BY DATE(created_at)
        ORDER BY date DESC
    """
    result = execute_query(sql, (days,))

    # 转换日期格式
    for item in result:
        item['date'] = item['date'].strftime('%Y-%m-%d') if item['date'] else ''

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': result
    })


@admin_bp.route('/login_logs', methods=['GET'])
@token_required
def get_login_logs(current_user):
    """
    获取登录日志

    Query Params:
        page: 页码(默认1)
        limit: 每页数量(默认20)
        keyword: 搜索关键词(可选)

    Returns:
        JSON: 登录日志列表
    """
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    keyword = request.args.get('keyword', '').strip()

    offset = (page - 1) * limit

    if keyword:
        where_clause = "WHERE username LIKE %s"
        params = (f'%{keyword}%', limit, offset)
        count_sql = "SELECT COUNT(*) as total FROM tb_login_log WHERE username LIKE %s"
    else:
        where_clause = ""
        params = (limit, offset)
        count_sql = "SELECT COUNT(*) as total FROM tb_login_log"

    # 获取总数
    count_result = execute_query(count_sql, params[:1] if keyword else None)
    total = count_result[0]['total'] if count_result else 0

    # 获取日志列表
    sql = f"""
        SELECT id, user_id, username, ip_address, login_status, login_message, created_at
        FROM tb_login_log {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """
    logs = execute_query(sql, params)

    # 转换日期格式
    for log in logs:
        log['created_at'] = log['created_at'].strftime('%Y-%m-%d %H:%M:%S') if log['created_at'] else None

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': {
            'list': logs,
            'total': total,
            'page': page,
            'limit': limit
        }
    })

# ==================== 运行指标（最小可观测性） ====================
import time as _time
_PS_START = _time.time()


@admin_bp.route('/metrics', methods=['GET'])
@token_required
def system_metrics(current_user):
    """
    系统运行指标快照（管理员）
    - 资源：文档/用户/向量块/BM25块
    - 使用：问答总数/会话数/反馈满意度
    - 进程：运行时长
    """
    svc = get_rag_service()
    docs_by_status = execute_query(
        "SELECT status, COUNT(*) AS n FROM tb_document GROUP BY status")
    qa_total = execute_query("SELECT COUNT(*) AS n FROM tb_qa_history")[0]['n']
    conv_total = execute_query("SELECT COUNT(*) AS n FROM tb_qa_conversation")[0]['n']
    user_total = execute_query("SELECT COUNT(*) AS n FROM tb_user")[0]['n']
    fb = execute_query(
        "SELECT COALESCE(SUM(rating=1),0) AS likes, COALESCE(SUM(rating=-1),0) AS dislikes, "
        "COUNT(*) AS total FROM tb_qa_feedback")[0]

    try:
        chunks = svc.vectorstore._collection.count() if svc.vectorstore else 0
    except Exception:
        chunks = 0
    bm25_chunks = len(svc.bm25._chunks)

    total_fb = int(fb['total'] or 0)
    likes = int(fb['likes'] or 0)
    return jsonify({'code': 200, 'data': {
        'uptime_seconds': round(_time.time() - _PS_START),
        'documents': {'by_status': {r['status']: r['n'] for r in docs_by_status}},
        'users': user_total,
        'qa': {'total': qa_total, 'conversations': conv_total},
        'feedback': {'likes': likes, 'dislikes': int(fb['dislikes'] or 0),
                     'total': total_fb,
                     'satisfaction': round(likes / total_fb, 4) if total_fb else None},
        'index': {'chroma_chunks': chunks, 'bm25_chunks': bm25_chunks,
                  'consistent': chunks == bm25_chunks},
    }})
