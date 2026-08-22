# -*- coding: utf-8 -*-
"""
日志处理器模块
统一的日志管理，支持控制台和文件输出
"""

import logging
import os
from datetime import datetime
from pathlib import Path

# 日志保存根目录
LOG_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(LOG_ROOT, exist_ok=True)

# 日志格式
DEFAULT_LOG_FORMAT = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)


def get_logger(
    name: str = "rag_system",
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    log_file: str = None
) -> logging.Logger:
    """
    获取日志器

    Args:
        name: 日志器名称
        console_level: 控制台日志级别
        file_level: 文件日志级别
        log_file: 日志文件路径（不指定则按日期生成）

    Returns:
        logging.Logger: 配置好的日志器
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 避免重复添加Handler
    if logger.handlers:
        return logger

    # 控制台Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(DEFAULT_LOG_FORMAT)
    logger.addHandler(console_handler)

    # 文件Handler
    if not log_file:
        log_file = os.path.join(LOG_ROOT, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(file_level)
    file_handler.setFormatter(DEFAULT_LOG_FORMAT)
    logger.addHandler(file_handler)

    return logger


# 全局日志器实例
logger = get_logger()