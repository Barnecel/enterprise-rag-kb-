# -*- coding: utf-8 -*-
"""
文档管理路由模块
处理文档上传、删除、查询等操作
"""

from flask import Blueprint, request, jsonify, send_from_directory, send_file, abort
from functools import wraps
import os
import io
import threading
import time
import uuid
import hashlib
from werkzeug.utils import secure_filename
from application.routes.auth import verify_token
from application.utils.db_utils import execute_query, execute_update, execute_insert
from config.settings import DOCUMENT_CONFIG
from application.services.rag_service import get_rag_service


def calculate_file_hash(file_path):
    """
    计算文件内容的SHA256哈希值

    Args:
        file_path: 文件路径

    Returns:
        str: 文件哈希值，失败返回None
    """
    try:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        print(f"计算文件Hash失败: {e}")
        return None

document_bp = Blueprint('document', __name__)


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


def allowed_file(filename):
    """
    检查文件扩展名是否允许

    Args:
        filename: 文件名

    Returns:
        bool: 是否允许
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in DOCUMENT_CONFIG['allowed_extensions']


def _parse_min_level(value):
    """解析表单中的文档密级(1公开/2内部/3机密/4绝密)，非法或缺失返回1"""
    try:
        ml = int(value)
        if 1 <= ml <= 4:
            return ml
    except (TypeError, ValueError):
        pass
    return 1


def _can_access_doc(doc, current_user):
    """
    单文档可见性判据（非admin）：所有者 or ACL显式授权 or 同部门+公开+密级达标。
    admin 恒可见。
    """
    if current_user.get('role') == 'admin':
        return True
    user_id = current_user['user_id']
    if doc.get('upload_by') == user_id:
        return True
    acl = execute_query(
        "SELECT 1 FROM tb_document_acl WHERE document_id = %s AND user_id = %s",
        (doc['id'], user_id)
    )
    if acl:
        return True
    return (
        doc.get('tenant_id') == current_user.get('tenant_id', 1)
        and doc.get('doc_level') == 'public'
        and doc.get('min_level', 1) <= current_user.get('clearance_level', 1)
    )


def admin_required(f):
    """装饰器：验证管理员权限"""
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


@document_bp.route('/upload', methods=['POST'])
@token_required
def upload_document(current_user):
    """
    上传文档接口
    支持txt, pdf, doc, docx, md格式文件

    Args:
        current_user: 当前登录用户信息

    Form Data:
        file: 文档文件
        title: 文档标题
        category_id: 分类ID
        doc_level: 文档级别(public/private)

    Returns:
        JSON: 上传结果
    """
    # 检查文件是否上传
    if 'file' not in request.files:
        return jsonify({'code': 400, 'message': '请选择要上传的文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'code': 400, 'message': '文件名为空'}), 400

    if not allowed_file(file.filename):
        return jsonify({'code': 400, 'message': '不支持的文件类型'}), 400

    # 获取其他参数
    title = request.form.get('title', '').strip()
    category_id = request.form.get('category_id', type=int)
    doc_level = request.form.get('doc_level', 'public')
    min_level = _parse_min_level(request.form.get('min_level'))

    # 自动识别文档类型并生成标题
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if not title:
        # 使用原文件名（不含扩展名）作为标题，保留中文
        title = file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename

    # 生成唯一文件名
    ext = file.filename.rsplit('.', 1)[1].lower()
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(DOCUMENT_CONFIG['upload_folder'], unique_filename)

    # 保存文件
    file.save(file_path)

    # 获取文件大小
    file_size = os.path.getsize(file_path)

    # 计算文件Hash并检查重复
    file_hash = calculate_file_hash(file_path)
    if file_hash:
        # 检查是否已存在相同Hash的文档
        check_sql = "SELECT id, title FROM tb_document WHERE file_hash = %s"
        existing_docs = execute_query(check_sql, (file_hash,))
        if existing_docs:
            # 删除刚保存的文件
            os.remove(file_path)
            return jsonify({
                'code': 409,
                'message': f'文档已存在: {existing_docs[0]["title"]}',
                'data': {'existing_id': existing_docs[0]['id']}
            }), 409

    # 插库。大文件走异步(pending，后台批量线程向量化)，小文件同步(processing)
    _async_cfg = DOCUMENT_CONFIG.get('async_upload', {}) if isinstance(DOCUMENT_CONFIG, dict) else {}
    use_async = (bool(_async_cfg.get('enabled', True))
                 and file_size > float(_async_cfg.get('size_mb', 10)) * 1024 * 1024)
    init_status = 'pending' if use_async else 'processing'
    insert_sql = """
        INSERT INTO tb_document (title, file_path, file_name, file_type, file_size, file_hash, category_id, tenant_id, status, upload_by, doc_level, min_level)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    doc_id = execute_insert(insert_sql, (
        title,
        file_path,
        file.filename,
        ext,
        file_size,
        file_hash,
        category_id,
        current_user.get('tenant_id', 1),
        init_status,
        current_user['user_id'],
        doc_level,
        min_level
    ))

    # 大文件自动转异步：立即返回 batch_id，前端轮询进度（含OCR页级进度）
    if use_async:
        batch_id = _launch_batch(
            [(doc_id, file_path, file.filename, title)],
            current_user.get('tenant_id', 1), doc_level, min_level, current_user['user_id']
        )
        return jsonify({
            'code': 201,
            'message': f'文件较大({file_size/1024/1024:.0f}MB)，已转入后台处理',
            'data': {'id': doc_id, 'title': title, 'file_name': file.filename,
                     'batch_id': batch_id, 'async': True}
        }), 201

    # 异步触发向量化和内容提取(这里直接调用)
    try:
        rag_service = get_rag_service()
        if rag_service.add_document_to_vectorstore(
            file_path,
            doc_id=doc_id,
            tenant_id=current_user.get('tenant_id', 1),
            doc_level=doc_level,
            min_level=min_level,
            owner_id=current_user['user_id']
        ):
            # 向量化成功，更新状态
            update_status_sql = "UPDATE tb_document SET status = 'completed' WHERE id = %s"
            execute_update(update_status_sql, (doc_id,))
        else:
            # 向量化失败，更新状态为failed
            update_status_sql = "UPDATE tb_document SET status = 'failed' WHERE id = %s"
            execute_update(update_status_sql, (doc_id,))
    except Exception as e:
        print(f"文档向量化失败: {e}")
        update_status_sql = "UPDATE tb_document SET status = 'failed' WHERE id = %s"
        execute_update(update_status_sql, (doc_id,))

    return jsonify({
        'code': 201,
        'message': '文件上传成功',
        'data': {
            'id': doc_id,
            'title': title,
            'file_name': file.filename
        }
    }), 201


# ---------------------------------------------------------------
# 异步批量上传（暂存+插库立即返回，后台线程逐个向量化）
# ---------------------------------------------------------------
MAX_BATCH_SIZE = 200          # 异步处理，放开原 20 限制，仍留合理保护
_batch_jobs = {}              # batch_id -> state
_batch_lock = threading.Lock()


def _perform_batch_cancel(state, mode='pending', rag=None):
    """取消清理：按 mode 抹除向量库/DB/文件。
    mode='all' 删除该批次全部文档；mode='pending' 只删未处理的（已上传保留）。
    仅在确认后台线程已停止(无进行中的向量化)后调用，避免与线程竞态。
    """
    work_ids = state.get('doc_ids') or []
    processed_ids = set(state.get('processed_ids') or [])
    targets = work_ids if mode == 'all' else [d for d in work_ids if d not in processed_ids]

    if rag is None:
        try:
            rag = get_rag_service()
        except Exception as e:
            print(f"cancel: RAG init failed: {e}")
            rag = None

    removed_vector = 0
    removed_rows = 0
    for doc_id in targets:
        # 仅对已索引的文档删除向量；未处理的没有向量
        if mode == 'all' and doc_id in processed_ids and rag is not None:
            try:
                if rag.delete_document_from_vectorstore(doc_id):
                    removed_vector += 1
            except Exception as e:
                print(f"cancel: delete vector doc {doc_id} failed: {e}")
        # 删除文件 + DB 行
        rows = execute_query("SELECT file_path FROM tb_document WHERE id = %s", (doc_id,))
        if rows:
            fp = rows[0].get('file_path')
            if fp and os.path.exists(fp):
                try:
                    os.remove(fp)
                except OSError:
                    pass
            try:
                execute_update("DELETE FROM tb_document WHERE id = %s", (doc_id,))
                removed_rows += 1
            except Exception as e:
                print(f"cancel: delete row doc {doc_id} failed: {e}")

    with _batch_lock:
        state['cancel_result'] = {
            'mode': mode,
            'removed_rows': removed_rows,
            'removed_from_vector': removed_vector
        }
        state['status'] = 'cancelled'
        state['current_file'] = ''
        state['finished_at'] = time.strftime('%Y-%m-%d %H:%M:%S')


def _wait_then_cancel(state, mode):
    """等后台线程完全停止后执行取消清理（避免与进行中的向量化竞态）。"""
    while True:
        with _batch_lock:
            stopped = state.get('thread_stopped')
        if stopped:
            break
        time.sleep(0.5)
    _perform_batch_cancel(state, mode)


def _launch_batch(work, tenant_id, doc_level, min_level, owner_id,
                  stage_fail_count=0, stage_fail_list=None):
    """创建批量任务状态并启动后台线程（单文件大文档异步化与批量上传共用）"""
    batch_id = uuid.uuid4().hex
    state = {
        'batch_id': batch_id,
        'total': len(work),
        'processed': 0,
        'success_count': 0,
        'fail_count': 0,
        'stage_fail_count': stage_fail_count,
        'stage_fail_list': stage_fail_list or [],
        'current_file': '',
        'detail': '',
        'status': 'running',
        'paused': False,
        'cancelled': False,
        'processing': False,
        'thread_stopped': False,
        'doc_ids': [d[0] for d in work],
        'processed_ids': [],
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'results': []
    }
    with _batch_lock:
        _batch_jobs[batch_id] = state
    threading.Thread(
        target=_process_batch,
        args=(batch_id, work, tenant_id, doc_level, min_level, owner_id),
        daemon=True
    ).start()
    return batch_id


def _process_batch(batch_id, work, tenant_id, doc_level, min_level, owner_id):
    """后台线程：逐个向量化 work 中的 (doc_id, file_path, filename, title)。支持暂停/恢复/取消。"""
    state = _batch_jobs.get(batch_id)
    try:
        rag_service = get_rag_service()
    except Exception as e:
        print(f"批量任务 {batch_id} 初始化RAG失败: {e}")
        with _batch_lock:
            if state:
                state['thread_stopped'] = True
                state['status'] = 'done'
        return

    try:
        for doc_id, file_path, filename, title in work:
            with _batch_lock:
                if state is None or state.get('cancelled'):
                    break
                state['current_file'] = filename
                state['processing'] = True
            # 暂停等待（每0.5s检查一次，取消则退出）
            while True:
                with _batch_lock:
                    if state is None or state.get('cancelled'):
                        break
                    if not state.get('paused'):
                        break
                time.sleep(0.5)
            with _batch_lock:
                if state is None or state.get('cancelled'):
                    if state:
                        state['processing'] = False
                    break
            try:
                def _progress(done, total, stage='parse'):
                    """解析/向量化进度 → 写入批量状态供前端轮询展示"""
                    label = {'parse': '解析', 'embed': '向量化'}.get(stage, stage)
                    with _batch_lock:
                        if state is not None:
                            state['detail'] = f"{label} {done}/{total}"

                ok = rag_service.add_document_to_vectorstore(
                    file_path, doc_id=doc_id, tenant_id=tenant_id,
                    doc_level=doc_level, min_level=min_level, owner_id=owner_id,
                    progress_cb=_progress)
            except Exception as e:
                print(f"批量向量化失败 {filename}: {e}")
                ok = False
            status = 'completed' if ok else 'failed'
            try:
                execute_update("UPDATE tb_document SET status = %s WHERE id = %s", (status, doc_id))
            except Exception as e:
                print(f"更新状态失败 {filename}: {e}")
            with _batch_lock:
                if state is not None:
                    state.pop('detail', None)
                if state:
                    state['processed'] += 1
                    state['processed_ids'].append(doc_id)
                    state['processing'] = False
                    if ok:
                        state['success_count'] += 1
                        state['results'].append({'id': doc_id, 'file_name': filename, 'title': title})
                    else:
                        state['fail_count'] += 1
                        state['results'].append({'id': doc_id, 'file_name': filename, 'title': title, 'error': '向量化失败'})
    finally:
        with _batch_lock:
            if state:
                state['thread_stopped'] = True
                state['processing'] = False
                if not state.get('cancelled'):
                    state['status'] = 'done'
                    state['current_file'] = ''
                    state['finished_at'] = time.strftime('%Y-%m-%d %H:%M:%S')


@document_bp.route('/upload/batch', methods=['POST'])
@token_required
def batch_upload_documents(current_user):
    """
    批量上传文档接口（异步）
    请求内完成：保存文件 + hash去重 + 插库(status=pending)，立即返回 batch_id；
    后台线程逐个向量化并更新 status。前端轮询 /upload/batch/status?batch_id= 查看进度。

    Form Data:
        files: 多个文档文件
        category_id: 分类ID（可选，所有文件共用）
        doc_level: 文档级别(public/private)

    Returns:
        JSON: {batch_id, total, stage_fail_count, stage_fail_list}
    """
    if 'files' not in request.files:
        return jsonify({'code': 400, 'message': '请选择要上传的文件'}), 400

    files = request.files.getlist('files')
    if not files or len(files) == 0:
        return jsonify({'code': 400, 'message': '请选择至少一个文件'}), 400

    if len(files) > MAX_BATCH_SIZE:
        return jsonify({'code': 400, 'message': f'单次批量上传最多{MAX_BATCH_SIZE}个文件'}), 400

    category_id = request.form.get('category_id', type=int)
    doc_level = request.form.get('doc_level', 'public')
    min_level = _parse_min_level(request.form.get('min_level'))
    tenant_id = current_user.get('tenant_id', 1)
    owner_id = current_user['user_id']

    work = []          # (doc_id, file_path, filename, title)
    stage_fail = []    # 暂存阶段失败（空名/类型/重复/保存异常）
    stage_fail_count = 0

    for file in files:
        try:
            if file.filename == '':
                stage_fail_count += 1
                stage_fail.append({'file_name': '未知文件', 'error': '文件名为空'})
                continue

            if not allowed_file(file.filename):
                stage_fail_count += 1
                stage_fail.append({'file_name': file.filename, 'error': '不支持的文件类型'})
                continue

            title = request.form.get('title', '').strip()
            if not title:
                title = file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename

            ext = file.filename.rsplit('.', 1)[1].lower()
            unique_filename = f"{uuid.uuid4().hex}.{ext}"
            file_path = os.path.join(DOCUMENT_CONFIG['upload_folder'], unique_filename)
            file.save(file_path)
            file_size = os.path.getsize(file_path)

            # hash 去重
            file_hash = calculate_file_hash(file_path)
            if file_hash:
                existing_docs = execute_query("SELECT id, title FROM tb_document WHERE file_hash = %s", (file_hash,))
                if existing_docs:
                    os.remove(file_path)
                    stage_fail_count += 1
                    stage_fail.append({
                        'file_name': file.filename,
                        'error': f'与已有文档重复: {existing_docs[0]["title"]}'
                    })
                    continue

            # 插库，status=pending（等待后台向量化）
            insert_sql = """
                INSERT INTO tb_document (title, file_path, file_name, file_type, file_size, file_hash, category_id, tenant_id, status, upload_by, doc_level, min_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s)
            """
            doc_id = execute_insert(insert_sql, (
                title, file_path, file.filename, ext, file_size, file_hash,
                category_id, tenant_id, current_user['user_id'], doc_level, min_level
            ))
            work.append((doc_id, file_path, file.filename, title))
        except Exception as e:
            print(f"批量暂存失败: {e}")
            stage_fail_count += 1
            stage_fail.append({
                'file_name': file.filename if file else '未知',
                'error': str(e)
            })

    if not work:
        return jsonify({
            'code': 200,
            'message': f'暂存完成，0个待处理，{stage_fail_count}个失败',
            'data': {'batch_id': None, 'total': 0, 'stage_fail_count': stage_fail_count, 'stage_fail_list': stage_fail}
        })

    batch_id = _launch_batch(work, tenant_id, doc_level, min_level, owner_id,
                             stage_fail_count=stage_fail_count, stage_fail_list=stage_fail)

    return jsonify({
        'code': 200,
        'message': f'批量任务已开始，共{len(work)}个文件，{stage_fail_count}个暂存失败',
        'data': {'batch_id': batch_id, 'total': len(work), 'stage_fail_count': stage_fail_count, 'stage_fail_list': stage_fail}
    })


@document_bp.route('/upload/batch/status', methods=['GET'])
@token_required
def batch_upload_status(current_user):
    """查询批量任务进度"""
    batch_id = request.args.get('batch_id', '')
    if not batch_id:
        return jsonify({'code': 400, 'message': '缺少 batch_id'}), 400
    with _batch_lock:
        state = _batch_jobs.get(batch_id)
    if not state:
        return jsonify({'code': 404, 'message': '任务不存在或已过期'}), 404
    return jsonify({'code': 200, 'data': state})


@document_bp.route('/upload/batch/control', methods=['POST'])
@token_required
def batch_upload_control(current_user):
    """
    批量任务控制：暂停 / 恢复 / 取消

    Body:
        action: pause | resume | cancel
        mode:   仅 cancel 使用，'all' 取消此次全部（抹除向量+DB+文件）；
                'pending' 只取消未上传的（已上传的保留）
    """
    data = request.get_json() or {}
    batch_id = data.get('batch_id', '')
    action = data.get('action', '')
    mode = data.get('mode', 'pending')
    if not batch_id or action not in ('pause', 'resume', 'cancel'):
        return jsonify({'code': 400, 'message': '缺少 batch_id 或 action 非法'}), 400

    with _batch_lock:
        state = _batch_jobs.get(batch_id)
    if not state:
        return jsonify({'code': 404, 'message': '任务不存在或已结束'}), 404

    if action == 'pause':
        with _batch_lock:
            state['paused'] = True
            state['status'] = 'paused'
        return jsonify({'code': 200, 'message': '已暂停', 'data': state})

    if action == 'resume':
        with _batch_lock:
            state['paused'] = False
            state['status'] = 'running'
        return jsonify({'code': 200, 'message': '已恢复', 'data': state})

    # ---- cancel ----
    with _batch_lock:
        state['cancelled'] = True
        state['cancel_mode'] = mode
        thread_stopped = state.get('thread_stopped')
    if thread_stopped:
        # 线程已停止：当前请求内直接清理（无进行中的向量化，无竞态）
        _perform_batch_cancel(state, mode)
    else:
        # 线程仍在运行：由守护线程等其停止后清理，立即返回
        threading.Thread(target=_wait_then_cancel, args=(state, mode), daemon=True).start()
    return jsonify({'code': 200, 'message': '取消请求已提交', 'data': state})


@document_bp.route('/list', methods=['GET'])
@token_required
def get_document_list(current_user):
    """
    获取文档列表

    Query Params:
        page: 页码(默认1)
        limit: 每页数量(默认10)
        category_id: 分类ID(可选)
        keyword: 搜索关键词(可选)
        status: 文档状态(可选)

    Returns:
        JSON: 文档列表和分页信息
    """
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 10))
    category_id = request.args.get('category_id', type=int)
    keyword = request.args.get('keyword', '').strip()
    status = request.args.get('status', '').strip()

    offset = (page - 1) * limit
    conditions = []
    params = []

    # 普通用户可见性：同部门+公开+密级达标 OR 所有者 OR ACL显式授权(覆盖部门/密级)
    if current_user['role'] != 'admin':
        conditions.append(
            "((d.tenant_id = %s AND d.doc_level = 'public' AND d.min_level <= %s) "
            "OR d.upload_by = %s "
            "OR d.id IN (SELECT document_id FROM tb_document_acl WHERE user_id = %s))"
        )
        params.extend([
            current_user.get('tenant_id', 1),
            current_user.get('clearance_level', 1),
            current_user['user_id'],
            current_user['user_id']
        ])

    if category_id:
        conditions.append("d.category_id = %s")
        params.append(category_id)

    if keyword:
        conditions.append("(d.title LIKE %s OR d.content LIKE %s)")
        params.extend([f'%{keyword}%', f'%{keyword}%'])

    if status:
        conditions.append("d.status = %s")
        params.append(status)

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # 获取总数
    count_sql = f"SELECT COUNT(*) as total FROM tb_document d {where_clause}"
    count_result = execute_query(count_sql, params)
    total = count_result[0]['total'] if count_result else 0

    # 获取文档列表
    sql = f"""
        SELECT d.id, d.title, d.content, d.file_name, d.file_type, d.file_size,
               d.category_id, d.tenant_id, d.status, d.doc_level, d.min_level, d.view_count, d.created_at,
               c.name as category_name, u.username as upload_by_name, t.name as tenant_name
        FROM tb_document d
        LEFT JOIN tb_category c ON d.category_id = c.id
        LEFT JOIN tb_user u ON d.upload_by = u.id
        LEFT JOIN tb_tenant t ON d.tenant_id = t.id
        {where_clause}
        ORDER BY d.created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    documents = execute_query(sql, params)

    # 转换日期格式
    for doc in documents:
        doc['created_at'] = doc['created_at'].strftime('%Y-%m-%d %H:%M:%S') if doc['created_at'] else None
        # 转换文件大小为可读格式
        doc['file_size'] = format_file_size(doc['file_size']) if doc['file_size'] else '0 B'

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': {
            'list': documents,
            'total': total,
            'page': page,
            'limit': limit
        }
    })


@document_bp.route('/<int:doc_id>', methods=['GET'])
@token_required
def get_document_detail(current_user, doc_id):
    """
    获取文档详细信息

    Args:
        current_user: 当前登录用户信息
        doc_id: 文档ID

    Returns:
        JSON: 文档详细信息
    """
    sql = """
        SELECT d.*, c.name as category_name, u.username as upload_by_name
        FROM tb_document d
        LEFT JOIN tb_category c ON d.category_id = c.id
        LEFT JOIN tb_user u ON d.upload_by = u.id
        WHERE d.id = %s
    """
    docs = execute_query(sql, (doc_id,))

    if not docs:
        return jsonify({'code': 404, 'message': '文档不存在'}), 404

    doc = docs[0]

    # 检查权限：所有者 or ACL授权 or 同部门+公开+密级达标
    if not _can_access_doc(doc, current_user):
        return jsonify({'code': 403, 'message': '无权访问此文档'}), 403

    # 增加浏览次数
    update_sql = "UPDATE tb_document SET view_count = view_count + 1 WHERE id = %s"
    execute_update(update_sql, (doc_id,))

    doc['created_at'] = doc['created_at'].strftime('%Y-%m-%d %H:%M:%S') if doc['created_at'] else None
    doc['updated_at'] = doc['updated_at'].strftime('%Y-%m-%d %H:%M:%S') if doc['updated_at'] else None

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': doc
    })


@document_bp.route('/<int:doc_id>', methods=['DELETE'])
@token_required
def delete_document(current_user, doc_id):
    """
    删除文档(文档所有者或管理员可删除)

    Args:
        current_user: 当前登录用户信息
        doc_id: 文档ID

    Returns:
        JSON: 删除结果
    """
    # 先查询文档信息
    sql = "SELECT id, file_path, upload_by, tenant_id, doc_level FROM tb_document WHERE id = %s"
    docs = execute_query(sql, (doc_id,))

    if not docs:
        return jsonify({'code': 404, 'message': '文档不存在'}), 404

    doc = docs[0]

    # 检查权限：文档所有者或管理员可删除
    if doc['upload_by'] != current_user['user_id'] and current_user['role'] != 'admin':
        return jsonify({'code': 403, 'message': '无权删除此文档'}), 403
    # 租户校验：非管理员仅能删除本租户文档
    if current_user['role'] != 'admin' and doc['tenant_id'] != current_user.get('tenant_id', 1):
        return jsonify({'code': 403, 'message': '无权删除其他租户的文档'}), 403

    # 清理向量库/BM25/父窗口映射（尽力而为，失败不阻断删除）
    try:
        get_rag_service().delete_document_from_vectorstore(doc_id)
    except Exception as e:
        print(f"清理文档 {doc_id} 向量数据失败: {e}")

    # 清理ACL授权记录
    try:
        execute_update("DELETE FROM tb_document_acl WHERE document_id = %s", (doc_id,))
    except Exception as e:
        print(f"清理文档 {doc_id} ACL记录失败: {e}")

    # 删除文件
    if os.path.exists(doc['file_path']):
        os.remove(doc['file_path'])

    # 删除数据库记录
    delete_sql = "DELETE FROM tb_document WHERE id = %s"
    execute_update(delete_sql, (doc_id,))

    return jsonify({'code': 200, 'message': '删除成功'})


@document_bp.route('/download/<int:doc_id>', methods=['GET'])
@token_required
def download_document(current_user, doc_id):
    """
    下载文档

    Args:
        current_user: 当前登录用户信息
        doc_id: 文档ID

    Returns:
        File: 文档文件
    """
    sql = "SELECT id, file_path, file_name, doc_level, min_level, upload_by, tenant_id FROM tb_document WHERE id = %s"
    docs = execute_query(sql, (doc_id,))

    if not docs:
        return jsonify({'code': 404, 'message': '文档不存在'}), 404

    doc = docs[0]

    # 检查权限：所有者 or ACL授权 or 同部门+公开+密级达标
    if not _can_access_doc(doc, current_user):
        return jsonify({'code': 403, 'message': '无权下载此文档'}), 403

    file_dir = os.path.dirname(doc['file_path'])
    return send_from_directory(file_dir, os.path.basename(doc['file_path']), as_attachment=True)


# ---------- 在线查看 / 预览 ----------


_convert_lock = threading.Lock()  # 防止并发调用 LibreOffice（document_parser 也是全局单锁）


def _load_doc_or_404(doc_id, fields='id, file_path, file_name, file_type, doc_level, min_level, upload_by, tenant_id'):
    rows = execute_query(f"SELECT {fields} FROM tb_document WHERE id = %s", (doc_id,))
    return (rows[0] if rows else None)


def _store_parsed_text(doc_id, elements, content):
    """把预览文本/摘要写回 tb_document.content"""
    try:
        text_parts = [e.text for e in elements if e.text and e.text.strip()]
        text = '\n'.join(text_parts).strip()
        extracted = text or (content or '')[:2000]
        execute_update("UPDATE tb_document SET content = %s WHERE id = %s", (extracted or '暂无摘要', doc_id))
        return extracted
    except Exception as e:
        print(f"store parsed text failed: {e}")
        return content


@document_bp.route('/view/<int:doc_id>', methods=['GET'])
@token_required
def view_document(current_user, doc_id):
    """
    文档在线预览（新标签页内嵌）
    - txt/md/doc/docx/wps/rtf：写 UTF-8 文本内容（text/txt 或转换/读取后送纯文本）
      - txt/md 直接读文件；doc/docx/wps/rtf 用 LibreOffice 永久转为 docx 再读取文本
    - pdf/ppt/pptx：原文件直接内嵌（文字制位，浏览器渲染稳定）；ppt/pptx 走 /document/parsed 预览纯文本
    与 download 共用 _can_access_doc 权限判断。
    """
    doc = _load_doc_or_404(doc_id)
    if not doc:
        return jsonify({'code': 404, 'message': '文档不存在'}), 404
    if not _can_access_doc(doc, current_user):
        return jsonify({'code': 403, 'message': '无权预览此文档'}), 403

    fp = doc['file_path']
    ftype = (doc.get('file_type') or '').lower()

    # ---- 已存在的转换产物（doc->docx 文本等）直接送 ----
    converted_txt = os.path.join(os.path.dirname(fp), f".view_{os.path.basename(fp)}.txt")
    if os.path.isfile(converted_txt):
        return send_file(converted_txt, mimetype='text/plain; charset=utf-8')

    # ---- PDF / PPT / PPTX：原文件直接内嵌（浏览器可渲染） ----
    if ftype == 'pdf':
        if os.path.isfile(fp):
            return send_file(fp, mimetype='application/pdf')

    if ftype in ('.ppt', '.pptx'):
        # ppt/pptx 转 PDF 预览（走解析管线产物）；转换失败回退原文件
        converted = os.path.join(os.path.dirname(fp), f".view_{os.path.basename(fp)}.pdf")
        if os.path.isfile(converted):
            return send_file(converted, mimetype='application/pdf')

    # ---- 文本类：读/转后送 UTF-8 文本，避免乱码与浏览器下载 ----
    try:
        text = ''
        if ftype in ('txt', 'md'):
            with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        elif ftype in ('doc', 'docx', 'wps', 'rtf'):
            try:
                from application.services.document_parser import _parse_via_libreoffice
            except Exception as e:
                print(f"doc2txt import failed: {e}")
                text = ''
            if text == '':
                stats = {'warnings': []}
                with _convert_lock:
                    elements = _parse_via_libreoffice(fp, '.' + ftype, stats)
                if elements:
                    text = '\n'.join(e.text for e in elements if e.text and e.text.strip())
                if text:
                    try:
                        with open(converted_txt, 'w', encoding='utf-8') as f:
                            f.write(text)
                    except OSError:
                        pass
        if text:
            return send_file(io.BytesIO(text.encode('utf-8')), mimetype='text/plain; charset=utf-8')
    except Exception as e:
        print(f"view_document read {doc_id} failed: {e}")

    return jsonify({'code': 415, 'message': '不支持在线预览该格式，请下载后查看'}), 415


@document_bp.route('/parsed/<int:doc_id>', methods=['GET'])
@token_required
def parsed_document(current_user, doc_id):
    """
    文档内容/摘要预览（全屏详情页正文区）
    小文档（≤0.5MB）返回全部可读文本；大文档返回摘要（前 ~2000 字符）。
    解析结果缓存回 tb_document.content。
    """
    doc = _load_doc_or_404(doc_id, 'id, file_path, file_name, file_type, doc_level, min_level, upload_by, tenant_id, content')
    if not doc:
        return jsonify({'code': 404, 'message': '文档不存在'}), 404
    if not _can_access_doc(doc, current_user):
        return jsonify({'code': 403, 'message': '无权预览此文档'}), 403

    ftype = (doc.get('file_type') or '').lower()
    size = os.path.getsize(doc['file_path']) if os.path.isfile(doc['file_path']) else 0
    small = size > 0 and size <= 0.5 * 1024 * 1024
    cached = (doc.get('content') or '').strip()

    # 有缓存一律直接用（与文件大小无关）：大文档重新解析=重跑整本OCR，代价不可接受
    has_cache = bool(cached) and ('暂无摘要' not in cached)
    if has_cache:
        text = cached
        source = 'cache'
    else:
        try:
            from application.services.document_parser import parse_document
            stats = {'warnings': []}
            elements, parse_stats = parse_document(doc['file_path'])
            text = '\n'.join(e.text for e in elements if e.text and e.text.strip())
            text = text or cached
            source = 'parsed'
            _store_parsed_text(doc_id, elements, cached)
        except Exception as e:
            print(f"parsed_document {doc_id} failed: {e}")
            text = cached
            source = 'cache'

    if small:
        body, truncated = text, False
    elif request.args.get('full') in ('1', 'true') and has_cache:
        # 大文档全文模式：缓存的解析全文直接返回（前端滚动阅读）
        body, truncated = text, False
    else:
        # 大文档：取开头摘要（截断时提示）
        body = text[:2000]
        truncated = len(text) > 2000

    return jsonify({
        'code': 200,
        'message': '获取成功',
        'data': {
            'id': doc_id,
            'title': doc['file_name'],
            'file_type': ftype,
            'size': size,
            'small': small,
            'total_length': len(text),
            'text': body or '（该文档暂无文字内容）',
            'truncated': truncated,
            'source': source
        }
    })


def _can_manage_doc(current_user, doc):
    """ACL/文档更新管理权限：管理员或文档所有者"""
    return current_user.get('role') == 'admin' or doc.get('upload_by') == current_user['user_id']


@document_bp.route('/<int:doc_id>/acl', methods=['GET'])
@token_required
def get_document_acl(current_user, doc_id):
    """获取文档已授权用户列表（管理员或所有者）"""
    docs = execute_query("SELECT id, upload_by FROM tb_document WHERE id = %s", (doc_id,))
    if not docs:
        return jsonify({'code': 404, 'message': '文档不存在'}), 404
    if not _can_manage_doc(current_user, docs[0]):
        return jsonify({'code': 403, 'message': '无权管理此文档授权'}), 403

    rows = execute_query(
        "SELECT a.user_id, a.granted_by, a.created_at, u.username, u.real_name "
        "FROM tb_document_acl a LEFT JOIN tb_user u ON a.user_id = u.id "
        "WHERE a.document_id = %s ORDER BY a.created_at DESC",
        (doc_id,)
    )
    for r in rows:
        r['created_at'] = r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r.get('created_at') else None
    return jsonify({'code': 200, 'data': rows})


@document_bp.route('/<int:doc_id>/acl', methods=['POST'])
@token_required
def grant_document_acl(current_user, doc_id):
    """授权用户访问文档（管理员或所有者；覆盖部门与密级）"""
    docs = execute_query("SELECT id, upload_by FROM tb_document WHERE id = %s", (doc_id,))
    if not docs:
        return jsonify({'code': 404, 'message': '文档不存在'}), 404
    if not _can_manage_doc(current_user, docs[0]):
        return jsonify({'code': 403, 'message': '无权管理此文档授权'}), 403

    data = request.get_json() or {}
    user_id = data.get('user_id')
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({'code': 400, 'message': 'user_id 无效'}), 400
    if not execute_query("SELECT id FROM tb_user WHERE id = %s", (user_id,)):
        return jsonify({'code': 400, 'message': '用户不存在'}), 400

    try:
        execute_insert(
            "INSERT INTO tb_document_acl (document_id, user_id, granted_by) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE granted_by = VALUES(granted_by)",
            (doc_id, user_id, current_user['user_id'])
        )
    except Exception as e:
        return jsonify({'code': 500, 'message': f'授权失败: {str(e)}'}), 500
    return jsonify({'code': 200, 'message': '授权成功'})


@document_bp.route('/<int:doc_id>/acl', methods=['DELETE'])
@token_required
def revoke_document_acl(current_user, doc_id):
    """撤销用户对文档的授权（管理员或所有者）"""
    docs = execute_query("SELECT id, upload_by FROM tb_document WHERE id = %s", (doc_id,))
    if not docs:
        return jsonify({'code': 404, 'message': '文档不存在'}), 404
    if not _can_manage_doc(current_user, docs[0]):
        return jsonify({'code': 403, 'message': '无权管理此文档授权'}), 403

    data = request.get_json() or {}
    user_id = data.get('user_id')
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({'code': 400, 'message': 'user_id 无效'}), 400

    execute_update(
        "DELETE FROM tb_document_acl WHERE document_id = %s AND user_id = %s",
        (doc_id, user_id)
    )
    return jsonify({'code': 200, 'message': '撤销授权成功'})


@document_bp.route('/<int:doc_id>', methods=['PUT'])
@token_required
def update_document(current_user, doc_id):
    """
    更新文档元数据（标题/分类/密级），管理员或所有者
    Body: {title?, category_id?, min_level?}
    """
    docs = execute_query(
        "SELECT id, upload_by, tenant_id FROM tb_document WHERE id = %s", (doc_id,)
    )
    if not docs:
        return jsonify({'code': 404, 'message': '文档不存在'}), 404
    doc = docs[0]
    if not _can_manage_doc(current_user, doc):
        return jsonify({'code': 403, 'message': '无权修改此文档'}), 403
    if current_user['role'] != 'admin' and doc['tenant_id'] != current_user.get('tenant_id', 1):
        return jsonify({'code': 403, 'message': '无权修改其他租户的文档'}), 403

    data = request.get_json() or {}
    sets = []
    params = []
    if 'title' in data and data.get('title'):
        sets.append("title = %s")
        params.append(str(data['title']).strip())
    if 'category_id' in data:
        sets.append("category_id = %s")
        params.append(int(data['category_id']) if data.get('category_id') else None)
    if 'min_level' in data:
        ml = _parse_min_level(data.get('min_level'))
        sets.append("min_level = %s")
        params.append(ml)

    if not sets:
        return jsonify({'code': 400, 'message': '没有可更新的字段'}), 400

    params.append(doc_id)
    execute_update(f"UPDATE tb_document SET {', '.join(sets)} WHERE id = %s", tuple(params))
    return jsonify({'code': 200, 'message': '更新成功'})


def format_file_size(size):
    """
    格式化文件大小为可读字符串

    Args:
        size: 文件大小(字节)

    Returns:
        str: 格式化后的大小字符串
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"