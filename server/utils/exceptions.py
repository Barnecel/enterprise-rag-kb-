# -*- coding: utf-8 -*-
"""
自定义异常层级模块
提供统一的错误类型和HTTP状态码映射，用于API响应中的code/message字段
"""
from typing import Optional, Dict, Any


class RAGException(Exception):
    def __init__(self, message="系统错误", code=500, error_code=-1):
        self.message = message
        self.code = code
        self.error_code = error_code
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "error": self.error_code}


class BadRequestError(RAGException):
    def __init__(self, message="请求参数错误"):
        super().__init__(message=message, code=400, error_code=4000)


class UnauthorizedError(RAGException):
    def __init__(self, message="未提供有效令牌"):
        super().__init__(message=message, code=401, error_code=4001)


class ForbiddenError(RAGException):
    def __init__(self, message="权限不足，无法访问资源"):
        super().__init__(message=message, code=403, error_code=4003)


class NotFoundError(RAGException):
    def __init__(self, message="请求的资源不存在"):
        super().__init__(message=message, code=404, error_code=4004)


class MethodNotAllowedError(RAGException):
    def __init__(self, message="请求方法不被允许"):
        super().__init__(message=message, code=405, error_code=4005)


class ConflictError(RAGException):
    def __init__(self, message="请求冲突，资源状态不满足要求"):
        super().__init__(message=message, code=409, error_code=4009)


class ValidationError(RAGException):
    def __init__(self, message="参数验证失败", details=None):
        super().__init__(message=message, code=422, error_code=4222)
        self.details = details


class InternalError(RAGException):
    def __init__(self, message="内部服务器错误，请联系管理员"):
        super().__init__(message=message, code=500, error_code=5000)


class NotImplementedError(RAGException):
    def __init__(self, message="该功能尚未实现"):
        super().__init__(message=message, code=501, error_code=5011)


class ServiceUnavailableError(RAGException):
    def __init__(self, message="服务暂时不可用，请稍后重试"):
        super().__init__(message=message, code=503, error_code=5033)


class DocumentProcessError(RAGException):
    def __init__(self, message="文档处理失败"):
        super().__init__(message=message, code=520, error_code=5201)


class RetrievalError(RAGException):
    def __init__(self, message="文档检索失败"):
        super().__init__(message=message, code=521, error_code=5212)


class ModelSwapError(RAGException):
    def __init__(self, message="模型切换失败"):
        super().__init__(message=message, code=522, error_code=5221)


class PermissionDeniedError(RAGException):
    def __init__(self, message="访问被明确拒绝"):
        super().__init__(message=message, code=403, error_code=4031)


def register_error_handlers(app):
    """
    注册Flask错误处理器
    """
    @app.errorhandler(RAGException)
    def handle_rag_exception(error):
        return jsonify(error.to_dict()), error.code

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            "code": 404,
            "message": "接口不存在",
            "error": 4004
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({
            "code": 405,
            "message": "请求方法不被允许",
            "error": 4005
        }), 405

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            "code": 400,
            "message": "bad request",
            "error": 4000
        }), 400

    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({
            "code": 401,
            "message": "unauthorized",
            "error": 4001
        }), 401

    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({
            "code": 403,
            "message": "forbidden",
            "error": 4003
        }), 403

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            "code": 500,
            "message": "internal server error",
            "error": 5000
        }), 500
