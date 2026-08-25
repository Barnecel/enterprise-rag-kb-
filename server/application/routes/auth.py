# -*- coding: utf-8 -*-
"""
用户认证路由模块
处理用户登录、注册、登出等认证相关请求
"""

from flask import Blueprint, request, jsonify, session
import hashlib
from application.utils.db_utils import execute_query, execute_update, execute_insert
from config.settings import JWT_CONFIG
import jwt
import time

auth_bp = Blueprint('auth', __name__)


def md5_encrypt(password):
    """
    MD5密码加密函数（仅用于存量旧数据兼容校验，新密码一律使用bcrypt）

    Args:
        password: 明文密码

    Returns:
        str: MD5加密后的32位十六进制字符串
    """
    return hashlib.md5(password.encode()).hexdigest()


def hash_password(password):
    """bcrypt哈希（新密码标准，自带盐值）"""
    import bcrypt
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password, stored):
    """
    双算法校验：$2开头走bcrypt；否则回退MD5（存量用户兼容）。
    Returns:
        (是否匹配, 是否为需升级的旧MD5哈希)
    """
    if not stored:
        return False, False
    if stored.startswith('$2'):
        try:
            import bcrypt
            return bcrypt.checkpw(password.encode('utf-8'), stored.encode('utf-8')), False
        except Exception:
            return False, False
    return stored == md5_encrypt(password), True


def generate_token(user_info):
    """
    生成JWT访问令牌

    Args:
        user_info: 用户信息字典，包含id, username, role等

    Returns:
        str: JWT令牌字符串
    """
    payload = {
        'user_id': user_info['id'],
        'username': user_info['username'],
        'role': user_info['role'],
        'tenant_id': user_info.get('tenant_id', 1),
        'clearance_level': user_info.get('clearance_level', 1),
        'exp': int(time.time()) + JWT_CONFIG['expire_hours'] * 3600
    }
    return jwt.encode(payload, JWT_CONFIG['secret_key'], algorithm='HS256')


def verify_token(token):
    """
    验证JWT令牌有效性

    Args:
        token: JWT令牌字符串

    Returns:
        Dict|None: 解码后的用户信息，失败返回None
    """
    try:
        payload = jwt.decode(token, JWT_CONFIG['secret_key'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    用户登录接口
    请求参数: username, password
    返回: 用户信息+访问令牌
    """
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'code': 400, 'message': '用户名和密码不能为空'}), 400

    # 查询用户（按用户名，密码用双算法校验）
    sql = "SELECT id, username, password, real_name, email, phone, role, clearance_level, tenant_id, status FROM tb_user WHERE username = %s"
    users = execute_query(sql, (username,))

    if not users or not verify_password(password, users[0]['password'])[0]:
        # 记录登录失败日志
        log_sql = "INSERT INTO tb_login_log (username, ip_address, login_status, login_message) VALUES (%s, %s, %s, '密码错误或用户不存在')"
        execute_insert(log_sql, (username, request.remote_addr, 0))
        return jsonify({'code': 401, 'message': '用户名或密码错误'}), 401

    user = users[0]

    # 旧MD5哈希透明升级为bcrypt
    _, need_upgrade = verify_password(password, user['password'])
    if need_upgrade:
        try:
            execute_update("UPDATE tb_user SET password = %s WHERE id = %s",
                           (hash_password(password), user['id']))
            print(f"[auth] 用户 {username} 密码哈希已升级为bcrypt")
        except Exception as e:
            print(f"密码哈希升级失败: {e}")

    # 检查用户状态
    if user['status'] != 1:
        return jsonify({'code': 403, 'message': '账号已被禁用'}), 403

    # 生成令牌
    token = generate_token(user)

    # 记录登录成功日志
    log_sql = "INSERT INTO tb_login_log (user_id, username, ip_address, login_status, login_message) VALUES (%s, %s, %s, 1, '登录成功')"
    execute_insert(log_sql, (user['id'], username, request.remote_addr))

    return jsonify({
        'code': 200,
        'message': '登录成功',
        'data': {
            'token': token,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'real_name': user['real_name'],
                'email': user['email'],
                'phone': user['phone'],
                'role': user['role'],
                'tenant_id': user['tenant_id'],
                'clearance_level': user.get('clearance_level', 1)
            }
        }
    })


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    用户注册接口
    请求参数: username, password, real_name, email, phone
    返回: 注册结果
    """
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    real_name = data.get('real_name', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    tenant_id = data.get('tenant_id', 1) or 1

    # 参数验证
    if not username or not password:
        return jsonify({'code': 400, 'message': '用户名和密码不能为空'}), 400

    if len(username) < 3 or len(username) > 20:
        return jsonify({'code': 400, 'message': '用户名长度需在3-20个字符之间'}), 400

    if len(password) < 6:
        return jsonify({'code': 400, 'message': '密码长度至少6位'}), 400

    # 校验租户是否存在
    try:
        tenant_id = int(tenant_id)
    except (TypeError, ValueError):
        return jsonify({'code': 400, 'message': '租户ID无效'}), 400
    if not execute_query("SELECT id FROM tb_tenant WHERE id = %s", (tenant_id,)):
        return jsonify({'code': 400, 'message': '租户不存在'}), 400

    # 检查用户名是否已存在
    check_sql = "SELECT id FROM tb_user WHERE username = %s"
    if execute_query(check_sql, (username,)):
        return jsonify({'code': 409, 'message': '用户名已存在'}), 409

    # 密码bcrypt哈希
    encrypted_password = hash_password(password)

    # 插入新用户
    insert_sql = """
        INSERT INTO tb_user (username, password, real_name, email, phone, role, tenant_id, status)
        VALUES (%s, %s, %s, %s, %s, 'user', %s, 1)
    """
    try:
        user_id = execute_insert(insert_sql, (username, encrypted_password, real_name, email, phone, tenant_id))
        return jsonify({
            'code': 201,
            'message': '注册成功',
            'data': {'user_id': user_id, 'tenant_id': tenant_id}
        }), 201
    except Exception as e:
        return jsonify({'code': 500, 'message': f'注册失败: {str(e)}'}), 500


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """
    用户登出接口
    返回: 登出结果
    """
    # 清除session
    session.clear()
    return jsonify({'code': 200, 'message': '登出成功'})


@auth_bp.route('/verify', methods=['GET'])
def verify():
    """
    验证当前登录状态
    请求头: Authorization: Bearer <token>
    返回: 用户信息
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'code': 401, 'message': '未提供有效令牌'}), 401

    token = auth_header[7:]  # 去掉"Bearer "前缀
    payload = verify_token(token)

    if not payload:
        return jsonify({'code': 401, 'message': '令牌已过期或无效'}), 401

    # 获取最新用户信息
    sql = "SELECT id, username, real_name, email, phone, role, clearance_level, tenant_id, status FROM tb_user WHERE id = %s"
    users = execute_query(sql, (payload['user_id'],))

    if not users:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404

    user = users[0]
    if user['status'] != 1:
        return jsonify({'code': 403, 'message': '账号已被禁用'}), 403

    return jsonify({
        'code': 200,
        'message': '验证成功',
        'data': {
            'id': user['id'],
            'username': user['username'],
            'real_name': user['real_name'],
            'email': user['email'],
            'phone': user['phone'],
            'role': user['role'],
            'tenant_id': user['tenant_id'],
            'clearance_level': user.get('clearance_level', 1)
        }
    })


@auth_bp.route('/change_password', methods=['POST'])
def change_password():
    """
    修改密码接口
    请求参数: old_password, new_password
    返回: 修改结果
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'code': 401, 'message': '未提供有效令牌'}), 401

    token = auth_header[7:]
    payload = verify_token(token)
    if not payload:
        return jsonify({'code': 401, 'message': '令牌已过期或无效'}), 401

    data = request.get_json()
    old_password = data.get('old_password', '').strip()
    new_password = data.get('new_password', '').strip()

    if not old_password or not new_password:
        return jsonify({'code': 400, 'message': '旧密码和新密码不能为空'}), 400

    if len(new_password) < 6:
        return jsonify({'code': 400, 'message': '新密码长度至少6位'}), 400

    # 验证旧密码（双算法兼容）
    row = execute_query("SELECT password FROM tb_user WHERE id = %s", (payload['user_id'],))
    if not row or not verify_password(old_password, row[0]['password'])[0]:
        return jsonify({'code': 400, 'message': '旧密码错误'}), 400

    # 更新新密码（bcrypt）
    new_encrypted = hash_password(new_password)
    update_sql = "UPDATE tb_user SET password = %s WHERE id = %s"
    execute_update(update_sql, (new_encrypted, payload['user_id']))

    return jsonify({'code': 200, 'message': '密码修改成功'})