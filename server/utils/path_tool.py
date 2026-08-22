# -*- coding: utf-8 -*-
"""
路径工具模块
提供项目路径相关的工具函数
"""

import os
from pathlib import Path


def get_project_root() -> str:
    """获取项目根目录"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_abs_path(relative_path: str) -> str:
    """
    将相对路径转换为绝对路径

    Args:
        relative_path: 相对于项目根目录的路径

    Returns:
        str: 绝对路径
    """
    project_root = get_project_root()
    return os.path.join(project_root, relative_path)


def ensure_dir(dir_path: str) -> None:
    """
    确保目录存在，不存在则创建

    Args:
        dir_path: 目录路径
    """
    os.makedirs(dir_path, exist_ok=True)