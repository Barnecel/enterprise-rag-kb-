# -*- coding: utf-8 -*-
"""
用户管理路由模块
处理用户信息查询、修改等操作
"""

from flask import Blueprint, request, jsonify
from functools import wraps
from application.routes.auth import verify_token
from application.utils.db_utils import execute_query, execute_update

user_bp = Blueprint('user', __name__)


def token_required(f):
    """
    装饰器：验证请求的JWT令牌
    """
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


@user_bp.route('/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    """
    获取当前用户详细信息

    Args:
        current_user: 装饰器注入的当前用户信息

    Returns:
        JSON: 用户详细信息
    """
    sql = """
        SELECT u.id, u.username, u.real_name, u.email, u.phone, u.role, u.clearance_level, u.tenant_id,
               u.status, u.created_at, t.name as tenant_name
        FROM tb_user u
        LEFT JOIN tb_tenant t ON u.tenant_id = t.id
        WHERE u.id = %s
    """
    users = execute_query(sql, (current_user['user_id'],))

    if not users:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404

    user = users[0]
    # 转换datetime为字符串
    user['created_at'] = user['created_at'].strftime('%Y-%m-%d %H:%M:%S') if user['created_at'] else None

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': user
    })


@user_bp.route('/profile', methods=['PUT'])
@token_required
def update_profile(current_user):
    """
    更新当前用户信息

    Args:
        current_user: 装饰器注入的当前用户信息

    Request Body:
        real_name: 真实姓名
        email: 邮箱
        phone: 手机号

    Returns:
        JSON: 更新结果
    """
    data = request.get_json()
    real_name = data.get('real_name', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()

    update_sql = "UPDATE tb_user SET real_name = %s, email = %s, phone = %s WHERE id = %s"
    rows = execute_update(update_sql, (real_name, email, phone, current_user['user_id']))

    if rows > 0:
        return jsonify({'code': 200, 'message': '更新成功'})
    else:
        return jsonify({'code': 400, 'message': '更新失败'})


@user_bp.route('/list', methods=['GET'])
@token_required
def get_user_list(current_user):
    """
    获取用户列表(仅管理员可用)

    Args:
        current_user: 装饰器注入的当前用户信息

    Query Params:
        page: 页码(默认1)
        limit: 每页数量(默认10)
        keyword: 搜索关键词(可选)

    Returns:
        JSON: 用户列表和分页信息
    """
    if current_user['role'] != 'admin':
        return jsonify({'code': 403, 'message': '权限不足，仅管理员可访问'}), 403

    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 10))
    keyword = request.args.get('keyword', '').strip()

    offset = (page - 1) * limit

    if keyword:
        where_clause = "WHERE u.username LIKE %s OR u.real_name LIKE %s"
        params = (f'%{keyword}%', f'%{keyword}%', limit, offset)
        count_sql = "SELECT COUNT(*) as total FROM tb_user u " + where_clause
    else:
        where_clause = ""
        params = (limit, offset)
        count_sql = "SELECT COUNT(*) as total FROM tb_user u"

    # 获取总数
    count_result = execute_query(count_sql, params[:2] if keyword else None)
    total = count_result[0]['total'] if count_result else 0

    # 获取用户列表
    sql = f"""
        SELECT u.id, u.username, u.real_name, u.email, u.phone, u.role, u.clearance_level, u.tenant_id,
               u.status, u.created_at, t.name as tenant_name
        FROM tb_user u
        LEFT JOIN tb_tenant t ON u.tenant_id = t.id
        {where_clause}
        ORDER BY u.created_at DESC
        LIMIT %s OFFSET %s
    """
    users = execute_query(sql, params)

    # 转换日期格式
    for user in users:
        user['created_at'] = user['created_at'].strftime('%Y-%m-%d %H:%M:%S') if user['created_at'] else None

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': {
            'list': users,
            'total': total,
            'page': page,
            'limit': limit
        }
    })


@user_bp.route('/<int:user_id>', methods=['DELETE'])
@token_required
def delete_user(current_user, user_id):
    """
    删除用户(仅管理员可用)

    Args:
        current_user: 装饰器注入的当前用户信息
        user_id: 要删除的用户ID

    Returns:
        JSON: 删除结果
    """
    if current_user['role'] != 'admin':
        return jsonify({'code': 403, 'message': '权限不足，仅管理员可访问'}), 403

    # 不允许删除自己
    if user_id == current_user['user_id']:
        return jsonify({'code': 400, 'message': '不能删除自己的账号'}), 400

    sql = "DELETE FROM tb_user WHERE id = %s"
    rows = execute_update(sql, (user_id,))

    if rows > 0:
        return jsonify({'code': 200, 'message': '删除成功'})
    else:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404


@user_bp.route('/<int:user_id>/status', methods=['PUT'])
@token_required
def update_user_status(current_user, user_id):
    """
    更新用户状态(启用/禁用，仅管理员可用)

    Args:
        current_user: 装饰器注入的当前用户信息
        user_id: 要更新的用户ID

    Request Body:
        status: 1=启用, 0=禁用

    Returns:
        JSON: 更新结果
    """
    if current_user['role'] != 'admin':
        return jsonify({'code': 403, 'message': '权限不足，仅管理员可访问'}), 403

    data = request.get_json()
    status = data.get('status')

    if status not in [0, 1]:
        return jsonify({'code': 400, 'message': '状态值无效'}), 400

    sql = "UPDATE tb_user SET status = %s WHERE id = %s"
    rows = execute_update(sql, (status, user_id))

    if rows > 0:
        return jsonify({'code': 200, 'message': '状态更新成功'})
    else:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404


@user_bp.route('/tenants', methods=['GET'])
@token_required
def get_tenants(current_user):
    """
    获取部门租户列表（供管理端选择用户所属部门）
    """
    rows = execute_query("SELECT id, name, description FROM tb_tenant ORDER BY id")
    return jsonify({'code': 200, 'data': rows})


@user_bp.route('/<int:user_id>', methods=['PUT'])
@token_required
def update_user(current_user, user_id):
    """
    更新用户角色/部门/密级（仅管理员可用）
    密级变更对已登录用户需重新登录后 JWT 生效

    Body: {role?, tenant_id?, clearance_level?}
    """
    if current_user['role'] != 'admin':
        return jsonify({'code': 403, 'message': '权限不足，仅管理员可访问'}), 403

    data = request.get_json() or {}
    sets = []
    params = []

    role = data.get('role')
    if role:
        if role not in ('admin', 'user'):
            return jsonify({'code': 400, 'message': '角色值无效'}), 400
        sets.append("role = %s")
        params.append(role)

    tenant_id = data.get('tenant_id')
    if tenant_id is not None:
        try:
            tenant_id = int(tenant_id)
        except (TypeError, ValueError):
            return jsonify({'code': 400, 'message': '部门ID无效'}), 400
        if not execute_query("SELECT id FROM tb_tenant WHERE id = %s", (tenant_id,)):
            return jsonify({'code': 400, 'message': '部门不存在'}), 400
        sets.append("tenant_id = %s")
        params.append(tenant_id)

    clearance_level = data.get('clearance_level')
    if clearance_level is not None:
        try:
            clearance_level = int(clearance_level)
        except (TypeError, ValueError):
            return jsonify({'code': 400, 'message': '密级无效'}), 400
        if clearance_level not in (1, 2, 3, 4):
            return jsonify({'code': 400, 'message': '密级需为1-4'}), 400
        sets.append("clearance_level = %s")
        params.append(clearance_level)

    if not sets:
        return jsonify({'code': 400, 'message': '没有可更新的字段'}), 400

    params.append(user_id)
    rows = execute_update(f"UPDATE tb_user SET {', '.join(sets)} WHERE id = %s", tuple(params))

    if rows > 0:
        return jsonify({'code': 200, 'message': '更新成功'})
    else:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404