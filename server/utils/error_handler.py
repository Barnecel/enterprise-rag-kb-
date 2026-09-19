# -*- coding: utf-8 -*-
"""
错误处理中间件
统一捕获异常，转换为标准JSON格式的API响应
支持结构化日志记录和上下文信息注入
"""
import sys
import logging
import traceback
from typing import Optional, Dict, Any

from flask import Flask, request, jsonify
from utils.exceptions import RAGException
from utils.logger_handler import set_context, clear_context, logger, info

# 默认错误映射：异常类 -> (HTTP状态码, 错误码)
ERROR_MAP = {
    # RAGException 子类的自动映射（通过 __init__ 中的 code 字段）
}

# 记录错误的辅助函数
def _log_error(error: Exception, context: Dict[str, Any] = None) -> None:
    """记录错误到结构化日志"""
    log_entry = {
        "level": "ERROR",
        "exception_type": type(error).__name__,
        "exception_message": str(error),
    }
    
    # 添加上下文信息
    request_id = getattr(__import__('utils.logger_handler', fromlist=['set_context']), 'set_context', lambda: None)()
    # 简化处理：直接从全局上下文获取
    import threading
    ctx = threading.current_thread()
    
    # 收集traceback信息
    log_entry["traceback"] = traceback.format_exception(
        type(error), error, error.__traceback__
    )
    
    # 记录到结构化日志
    logger.error(
        "未处理的异常",
        extra={
            "exception": log_entry,
            "path": request.path if hasattr(request, 'path') else "unknown",
            "method": request.method if hasattr(request, 'method') else "unknown",
        }
    )


# 错误处理装饰器
def handle_errors(f):
    """装饰器：统一捕获函数内的异常"""
    from functools import wraps
    
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except RAGException as e:
            # 已知的自定义异常，直接转换为JSON响应
            return jsonify(e.to_dict()), e.code
        except Exception as e:
            # 未知异常，记录日志后返回500
            _log_error(e)
            # 在开发环境返回更详细的信息
            import os
            env = os.environ.get('FLASK_ENV', 'production')
            error_dict = {
                "code": 500,
                "message": "内部服务器错误",
                "error": -1
            }
            if env == 'development':
                error_dict["details"] = str(e)
                error_dict["traceback"] = traceback.format_exc()
            return jsonify(error_dict), 500
    return wrapper


# Flask错误处理器注册函数
def register_error_handlers(app: Flask) -> None:
    """注册Flask错误处理器
    
    Args:
        app: Flask应用实例
    """
    
    @app.errorhandler(RAGException)
    def handle_rag_exception(error: RAGException):
        """处理自定义RAG异常"""
        return jsonify(error.to_dict()), error.code
    
    @app.errorhandler(404)
    def not_found(error):
        """处理404未找到"""
        return jsonify({
            "code": 404,
            "message": "接口不存在",
            "error": 4004
        }), 404
    
    @app.errorhandler(405)
    def method_not_allowed(error):
        """处理405方法不被允许"""
        return jsonify({
            "code": 405,
            "message": "请求方法不被允许",
            "error": 4005
        }), 405
    
    @app.errorhandler(400)
    def bad_request(error):
        """处理400错误"""
        return jsonify({
            "code": 400,
            "message": "bad request",
            "error": 4000
        }), 400
    
    @app.errorhandler(401)
    def unauthorized(error):
        """处理401未授权"""
        return jsonify({
            "code": 401,
            "message": "unauthorized",
            "error": 4001
        }), 401
    
    @app.errorhandler(403)
    def forbidden(error):
        """处理403禁止访问"""
        return jsonify({
            "code": 403,
            "message": "forbidden",
            "error": 4003
        }), 403
    
    @app.errorhandler(500)
    def internal_error(error):
        """处理500内部错误"""
        return jsonify({
            "code": 500,
            "message": "internal server error",
            "error": 5000
        }), 500
