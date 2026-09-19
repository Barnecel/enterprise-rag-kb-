# -*- coding: utf-8 -*-
"""
结构化日志处理器模块
支持 JSON 格式输出，便于在生产环境中通过 ELK/EFK 进行检索和分析
同时兼容传统文本格式，确保向后兼容
"""

import logging
import os
import sys
import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Union
from pathlib import Path

# 日志保存根目录
LOG_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(LOG_ROOT, exist_ok=True)

# 全局上下文存储（线程安全）
import threading
_context_storage = threading.local()

# 默认结构化日志格式
STRUCTURED_FORMAT = '%(message)s'  # 消息部分由 JSON 填充

# 传统文本格式（向后兼容）
DEFAULT_LOG_FORMAT = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)


class InterceptHandler(logging.Handler):
    """拦截标准库日志并转发到结构化格式"""
    
    def emit(self, record: logging.LogRecord) -> None:
        # 获取或生成上下文 ID
        request_id = getattr(_context_storage, 'request_id', None)
        user_id = getattr(_context_storage, 'user_id', None)
        
        # 构建结构化日志数据
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "module": os.path.basename(record.filename),
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        
        # 添加上下文字段
        if request_id:
            log_entry["request_id"] = request_id
        if user_id is not None:
            log_entry["user_id"] = user_id
        
        # 兼容性：同时输出 JSON 到 stderr（便于 Docker/Kubernetes 收集）
        # 也支持传统文本格式
        message = json.dumps(log_entry, ensure_ascii=False)
        sys.stderr.write(message + "\n")
        
        # 同时也记录到传统格式的文件Handler
        # 这里简化处理，实际项目中可通过过滤器控制输出目标


def set_context(request_id: str = None, user_id: int = None) -> None:
    """设置当前请求上下文（在中间件中调用）
    
    Args:
        request_id: 唯一请求ID（UUID格式）
        user_id: 当前登录用户ID
    """
    _context_storage.request_id = request_id
    _context_storage.user_id = user_id


def clear_context() -> None:
    """清除当前上下境"""
    _context_storage.request_id = None
    _context_storage.user_id = None


def get_logger(
    name: str = "rag_system",
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    log_file: str = None,
    use_structured: bool = True
) -> logging.Logger:
    """
    获取日志器（支持结构化日志）
    
    Args:
        name: 日志器名称
        console_level: 控制台日志级别
        file_level: 文件日志级别
        log_file: 日志文件路径（不指定则按日期生成）
        use_structured: 是否使用结构化 JSON 输出到控制台
    
    Returns:
        logging.Logger: 配置好的日志器
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 避免重复添加Handler
    if logger.handlers:
        return logger

    # 控制台Handler - 支持结构化输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    
    # 对于控制台，我们使用拦截器方法，文件使用传统格式
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(console_handler)

    # 文件Handler - 始终使用传统格式便于人工阅读
    if not log_file:
        log_file = os.path.join(LOG_ROOT, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(file_level)
    file_handler.setFormatter(DEFAULT_LOG_FORMAT)
    logger.addHandler(file_handler)

    return logger


# 上下文管理器，便易在 with语句中使用
class LogContext:
    """日志上下文管理器
    
    用法:
        with LogContext(request_id="xxx", user_id=123):
            logger.info("处理用户请求")
    """
    def __init__(self, request_id: str = None, user_id: int = None):
        self.old_request_id = None
        self.old_user_id = None
        self.request_id = request_id
        self.user_id = user_id
    
    def __enter__(self):
        # 保存旧值并设置新值
        old = getattr(_context_storage, 'request_id', None)
        _context_storage.request_id = self.request_id
        _context_storage.user_id = self.user_id
        self.old_request_id = old
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # 恢复旧值
        _context_storage.request_id = self.old_request_id
        _context_storage.user_id = self.old_user_id


# 全局日志器实例（传统模式，便于直接导入使用）
logger = get_logger("rag_system", use_structured=False)


def info(msg: str, **kwargs: Any) -> None:
    """带关键词参数的 info 日志 - 自动合并上下文"""
    extra = kwargs
    # 合并全局上下文
    request_id = getattr(_context_storage, 'request_id', None)
    user_id = getattr(_context_storage, 'user_id', None)
    if request_id:
        extra['request_id'] = request_id
    if user_id is not None:
        extra['user_id'] = user_id
    logger.info(msg, extra=extra)


def warning(msg: str, **kwargs: Any) -> None:
    """带关键词参数的 warning 日志"""
    extra = kwargs
    request_id = getattr(_context_storage, 'request_id', None)
    user_id = getattr(_context_storage, 'user_id', None)
    if request_id:
        extra['request_id'] = request_id
    if user_id is not None:
        extra['user_id'] = user_id
    logger.warning(msg, extra=extra)


def error(msg: str, **kwargs: Any) -> None:
    """带关键词参数的 error 日志"""
    extra = kwargs
    request_id = getattr(_context_storage, 'request_id', None)
    user_id = getattr(_context_storage, 'user_id', None)
    if request_id:
        extra['request_id'] = request_id
    if user_id is not None:
        extra['user_id'] = user_id
    logger.error(msg, extra=extra)


def debug(msg: str, **kwargs: Any) -> None:
    """带关键词参数的 debug 日志"""
    extra = kwargs
    request_id = getattr(_context_storage, 'request_id', None)
    user_id = getattr(_context_storage, 'user_id', None)
    if request_id:
        extra['request_id'] = request_id
    if user_id is not None:
        extra['user_id'] = user_id
    logger.debug(msg, extra=extra)


def exception(msg: str, **kwargs: Any) -> None:
    """记录异常信息（含堆栈跟踪）"""
    extra = kwargs
    request_id = getattr(_context_storage, 'request_id', None)
    user_id = getattr(_context_storage, 'user_id', None)
    if request_id:
        extra['request_id'] = request_id
    if user_id is not None:
        extra['user_id'] = user_id
    logger.exception(msg, extra=extra)
