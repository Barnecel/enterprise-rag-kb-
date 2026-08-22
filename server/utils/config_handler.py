# -*- coding: utf-8 -*-
"""
配置处理器模块
支持YAML配置文件加载和管理
所有YAML中的字符串值支持 ${ENV_VAR} / ${ENV_VAR:default} 环境变量插值，
敏感信息（数据库密码、API密钥、JWT密钥等）通过环境变量或 server/.env 注入。
"""

import os
import re

import yaml
from typing import Any, Dict

try:
    from dotenv import load_dotenv
    _DOTENV_AVAILABLE = True
except ImportError:
    _DOTENV_AVAILABLE = False


# ${VAR} 或 ${VAR:default}
_ENV_PATTERN = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}')


def _resolve_env(value: Any) -> Any:
    """递归解析值中的环境变量占位符"""
    if isinstance(value, str):
        def repl(m):
            name, default = m.group(1), m.group(2)
            val = os.environ.get(name)
            if val is None:
                val = default if default is not None else ''
            return val
        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


class ConfigHandler:
    """配置管理器"""

    _instance = None
    _config = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """加载所有YAML配置文件"""
        if _DOTENV_AVAILABLE:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            load_dotenv(os.path.join(base_dir, '.env'))

        config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(config_dir, 'config')

        # 加载各个配置文件
        self._config = {
            'database': self._load_yaml(os.path.join(config_path, 'database.yml')),
            'chroma': self._load_yaml(os.path.join(config_path, 'chroma.yml')),
            'llm': self._load_yaml(os.path.join(config_path, 'llm.yml')),
            'embedding': self._load_yaml(os.path.join(config_path, 'embedding.yml')),
            'document': self._load_yaml(os.path.join(config_path, 'document.yml')),
            'rag': self._load_yaml(os.path.join(config_path, 'rag.yml')),
            'flask': self._load_yaml(os.path.join(config_path, 'flask.yml')),
            'cache': self._load_yaml(os.path.join(config_path, 'cache.yml')),
        }

    def _load_yaml(self, file_path: str) -> Dict[str, Any]:
        """加载单个YAML文件并做环境变量插值"""
        if not os.path.exists(file_path):
            return {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            return _resolve_env(data)
        except Exception as e:
            print(f"加载配置文件失败 {file_path}: {e}")
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项
        支持点号分隔的多级访问，如 'database.host'

        Args:
            key: 配置键名
            default: 默认值

        Returns:
            配置值或默认值
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default

        return value

    def get_section(self, section: str) -> Dict[str, Any]:
        """获取整个配置段落"""
        return self._config.get(section, {})


# 全局配置实例
config = ConfigHandler()
