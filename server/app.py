# -*- coding: utf-8 -*-
"""
Flask应用入口文件
企业RAG知识库问答Agent系统主应用
"""

from flask import Flask
from flask_cors import CORS
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import FLASK_CONFIG

def create_app():
    """
    创建并配置Flask应用实例

    Returns:
        Flask: 配置好的Flask应用实例
    """
    app = Flask(__name__)

    # 配置加载
    app.config['SECRET_KEY'] = FLASK_CONFIG['SECRET_KEY']
    app.config['DEBUG'] = FLASK_CONFIG['DEBUG']
    app.config['JSON_AS_ASCII'] = FLASK_CONFIG['JSON_AS_ASCII']

    # 启用CORS跨域支持
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # 注册蓝图路由
    from application.routes.auth import auth_bp
    from application.routes.user import user_bp
    from application.routes.document import document_bp
    from application.routes.category import category_bp
    from application.routes.qa import qa_bp
    from application.routes.admin import admin_bp
    from application.routes.model import model_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(user_bp, url_prefix='/api/user')
    app.register_blueprint(document_bp, url_prefix='/api/document')
    app.register_blueprint(category_bp, url_prefix='/api/category')
    app.register_blueprint(qa_bp, url_prefix='/api/qa')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(model_bp, url_prefix='/api/model')

    # 创建上传目录
    upload_folder = os.path.join(os.path.dirname(__file__), 'uploads')
    os.makedirs(upload_folder, exist_ok=True)

    # 健康检查端点
    @app.route('/api/health')
    def health_check():
        """健康检查端点"""
        return {'status': 'ok', 'message': '服务运行正常'}

    return app


# 应用入口
if __name__ == '__main__':
    app = create_app()
    app.run(
        host=os.environ.get('FLASK_HOST', '0.0.0.0'),
        port=int(os.environ.get('FLASK_PORT', 5003)),
        debug=app.config['DEBUG']
    )