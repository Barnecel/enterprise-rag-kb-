# -*- coding: utf-8 -*-
"""
知识库分类路由模块
处理分类的增删改查操作
"""

from flask import Blueprint, request, jsonify
from functools import wraps
from application.routes.auth import verify_token
from application.utils.db_utils import execute_query, execute_update, execute_insert

category_bp = Blueprint('category', __name__)


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


@category_bp.route('/list', methods=['GET'])
@token_required
def get_category_list(current_user):
    """
    获取分类列表(树形结构)

    Returns:
        JSON: 分类树形列表
    """
    sql = """
        SELECT id, name, description, parent_id, sort_order, created_at
        FROM tb_category
        ORDER BY sort_order ASC, id ASC
    """
    categories = execute_query(sql)

    # 转换为树形结构
    tree = build_category_tree(categories)

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': tree
    })


def build_category_tree(categories, parent_id=0):
    """
    递归构建分类树形结构

    Args:
        categories: 所有分类列表
        parent_id: 父分类ID

    Returns:
        List: 树形结构列表
    """
    tree = []
    for cat in categories:
        if cat['parent_id'] == parent_id:
            cat['created_at'] = cat['created_at'].strftime('%Y-%m-%d %H:%M:%S') if cat['created_at'] else None
            cat['children'] = build_category_tree(categories, cat['id'])
            tree.append(cat)
    return tree


@category_bp.route('/<int:category_id>', methods=['GET'])
@token_required
def get_category_detail(current_user, category_id):
    """
    获取分类详细信息

    Args:
        current_user: 当前登录用户信息
        category_id: 分类ID

    Returns:
        JSON: 分类详细信息
    """
    sql = "SELECT * FROM tb_category WHERE id = %s"
    categories = execute_query(sql, (category_id,))

    if not categories:
        return jsonify({'code': 404, 'message': '分类不存在'}), 404

    category = categories[0]
    category['created_at'] = category['created_at'].strftime('%Y-%m-%d %H:%M:%S') if category['created_at'] else None

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': category
    })


@category_bp.route('', methods=['POST'])
@token_required
def create_category(current_user):
    """
    创建新分类(仅管理员)

    Args:
        current_user: 当前登录用户信息

    Request Body:
        name: 分类名称
        description: 分类描述
        parent_id: 父分类ID(可选)
        sort_order: 排序序号(可选)

    Returns:
        JSON: 创建结果
    """
    if current_user['role'] != 'admin':
        return jsonify({'code': 403, 'message': '权限不足，仅管理员可创建分类'}), 403

    data = request.get_json()
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    parent_id = data.get('parent_id', 0)
    sort_order = data.get('sort_order', 0)

    if not name:
        return jsonify({'code': 400, 'message': '分类名称不能为空'}), 400

    # 检查父分类是否存在
    if parent_id > 0:
        check_sql = "SELECT id FROM tb_category WHERE id = %s"
        if not execute_query(check_sql, (parent_id,)):
            return jsonify({'code': 400, 'message': '父分类不存在'}), 400

    sql = """
        INSERT INTO tb_category (name, description, parent_id, sort_order, created_by)
        VALUES (%s, %s, %s, %s, %s)
    """
    category_id = execute_insert(sql, (name, description, parent_id, sort_order, current_user['user_id']))

    return jsonify({
        'code': 201,
        'message': '创建成功',
        'data': {'id': category_id}
    }), 201


@category_bp.route('/<int:category_id>', methods=['PUT'])
@token_required
def update_category(current_user, category_id):
    """
    更新分类信息(仅管理员)

    Args:
        current_user: 当前登录用户信息
        category_id: 分类ID

    Request Body:
        name: 分类名称
        description: 分类描述
        sort_order: 排序序号

    Returns:
        JSON: 更新结果
    """
    if current_user['role'] != 'admin':
        return jsonify({'code': 403, 'message': '权限不足，仅管理员可更新分类'}), 403

    data = request.get_json()
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    sort_order = data.get('sort_order', 0)

    if not name:
        return jsonify({'code': 400, 'message': '分类名称不能为空'}), 400

    sql = "UPDATE tb_category SET name = %s, description = %s, sort_order = %s WHERE id = %s"
    rows = execute_update(sql, (name, description, sort_order, category_id))

    if rows > 0:
        return jsonify({'code': 200, 'message': '更新成功'})
    else:
        return jsonify({'code': 404, 'message': '分类不存在'}), 404


@category_bp.route('/<int:category_id>', methods=['DELETE'])
@token_required
def delete_category(current_user, category_id):
    """
    删除分类(仅管理员)
    如果分类下有文档或子分类，则不允许删除

    Args:
        current_user: 当前登录用户信息
        category_id: 分类ID

    Returns:
        JSON: 删除结果
    """
    if current_user['role'] != 'admin':
        return jsonify({'code': 403, 'message': '权限不足，仅管理员可删除分类'}), 403

    # 检查是否有子分类
    child_sql = "SELECT id FROM tb_category WHERE parent_id = %s"
    if execute_query(child_sql, (category_id,)):
        return jsonify({'code': 400, 'message': '该分类下存在子分类，请先删除子分类'}), 400

    # 检查是否有文档
    doc_sql = "SELECT id FROM tb_document WHERE category_id = %s"
    if execute_query(doc_sql, (category_id,)):
        return jsonify({'code': 400, 'message': '该分类下存在文档，请先删除或移动文档'}), 400

    sql = "DELETE FROM tb_category WHERE id = %s"
    rows = execute_update(sql, (category_id,))

    if rows > 0:
        return jsonify({'code': 200, 'message': '删除成功'})
    else:
        return jsonify({'code': 404, 'message': '分类不存在'}), 404