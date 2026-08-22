# -*- coding: utf-8 -*-
"""
配置文件 - 统一配置出口
唯一数据源为 config/*.yml（支持 ${ENV_VAR:default} 环境变量插值与 server/.env）。
本模块仅做结构适配与类型转换，供 db_utils / 路由层等使用；
RAG服务直接读取 utils.config_handler.config 的对应段落。
"""

import os

from utils.config_handler import config

# 基础路径配置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bool(value, default=False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return default


# 数据库配置
_DB = config.get_section('database')
DB_CONFIG = {
    'host': _DB.get('host', 'localhost'),
    'port': int(_DB.get('port', 3308)),
    'user': _DB.get('user', 'root'),
    'password': _DB.get('password', ''),
    'database': _DB.get('database', 'db_enterprise_9a'),
    'charset': _DB.get('charset', 'utf8mb4')
}

# Chroma向量数据库配置
_CHROMA = config.get_section('chroma')
_chroma_dir = _CHROMA.get('persist_directory', 'chroma_data')
if not os.path.isabs(_chroma_dir):
    _chroma_dir = os.path.join(BASE_DIR, _chroma_dir)
CHROMA_CONFIG = {
    'persist_directory': _chroma_dir,
    'collection_name': _CHROMA.get('collection_name', 'enterprise_knowledge')
}

# 密级定义（1公开/2内部/3机密/4绝密）：用户 clearance_level 与文档 min_level 共用
CLEARANCE_LEVELS = {1: '公开', 2: '内部', 3: '机密', 4: '绝密'}

# 文档处理配置
_DOCUMENT = config.get_section('document')
_upload_folder = _DOCUMENT.get('upload_folder', 'uploads')
if not os.path.isabs(_upload_folder):
    _upload_folder = os.path.join(BASE_DIR, _upload_folder)
DOCUMENT_CONFIG = {
    'chunk_size': int(_DOCUMENT.get('chunk_size', 500)),
    'chunk_overlap': int(_DOCUMENT.get('chunk_overlap', 50)),
    'upload_folder': _upload_folder,
    'allowed_extensions': set(_DOCUMENT.get('allowed_extensions') or {
        'txt', 'pdf', 'doc', 'docx', 'ppt', 'pptx', 'wps', 'rtf', 'md'})
}

# Flask配置
_FLASK = config.get_section('flask')
FLASK_CONFIG = {
    'SECRET_KEY': _FLASK.get('secret_key', ''),
    'DEBUG': _bool(_FLASK.get('debug'), False),
    'JSON_AS_ASCII': _bool(_FLASK.get('json_as_ascii'), False)
}

# JWT配置
JWT_CONFIG = {
    'secret_key': _FLASK.get('jwt_secret_key', ''),
    'expire_hours': int(_FLASK.get('jwt_expire_hours', 24))
}
