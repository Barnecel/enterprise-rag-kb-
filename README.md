# 企业RAG知识库问答Agent系统

基于LangChain的RAG（检索增强生成）企业内部知识库问答系统，使用Flask + Vue3开发。

## 项目结构

```
server/                 # Python Flask后端
├── app/
│   ├── routes/        # API路由
│   ├── services/      # 业务逻辑服务
│   └── utils/         # 工具函数
├── config/            # 配置文件
├── scripts/           # 脚本文件
│   ├── init_database.sql  # 数据库建表SQL
│   └── test_data.sql      # 测试数据
├── uploads/           # 上传文件目录
├── chroma_data/      # Chroma向量数据库存储
└── requirements.txt   # Python依赖

client/                # Vue3前端
├── src/
│   ├── api/          # API调用封装
│   ├── router/       # 路由配置
│   ├── views/        # 页面组件
│   └── assets/       # 静态资源
└── .env              # 环境变量配置
```

## 技术栈

### 后端
- **Web框架**: Flask 2.3
- **数据库**: MySQL 8.0 (db_enterprise_9a, 端口3308)
- **向量数据库**: Chroma
- **LLM模型**: oMLX Qwen3.5-9B-MLX-4bit
- **嵌入模型**: Qllama Qwen3-Embedding-8B-4bit-DWQ
- **认证**: JWT + MD5密码

### 前端
- **框架**: Vue 3
- **UI库**: Element Plus
- **图表**: ECharts
- **构建**: Vite

## 功能特性

1. **用户管理**: 登录/注册/个人中心，支持管理员和普通用户角色
2. **知识库管理**: 文档上传/下载/删除，支持分类管理
3. **智能问答**: 基于RAG技术的智能问答，支持文档检索
4. **管理员后台**: 数据统计图表、用户管理、文档管理、登录日志

## 快速开始

### 1. 初始化数据库

```bash
# 登录MySQL并执行建表SQL
mysql -h localhost -P 3308 -u root -p123456 < server/scripts/init_database.sql
mysql -h localhost -P 3308 -u root -p123456 < server/scripts/test_data.sql
```

### 2. 安装后端依赖

```bash
cd server
pip install -r requirements.txt
```

### 3. 安装前端依赖

```bash
cd client
npm install
```

### 4. 启动服务

```bash
# 启动后端 (端口5000)
cd server
python app.py

# 启动前端 (端口3000)
cd client
npm run dev
```

## 默认账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | 123456 | 管理员 |
| user01 | 123456 | 普通用户 |

## API接口

### 认证相关
- `POST /api/auth/login` - 用户登录
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/logout` - 用户登出
- `GET /api/auth/verify` - 验证Token
- `POST /api/auth/change_password` - 修改密码

### 用户相关
- `GET /api/user/profile` - 获取用户信息
- `PUT /api/user/profile` - 更新用户信息
- `GET /api/user/list` - 获取用户列表(管理员)

### 文档相关
- `POST /api/document/upload` - 上传文档
- `GET /api/document/list` - 获取文档列表
- `GET /api/document/:id` - 获取文档详情
- `DELETE /api/document/:id` - 删除文档

### 问答相关
- `POST /api/qa/ask` - 提问
- `GET /api/qa/history` - 获取问答历史

### 管理后台
- `GET /api/admin/dashboard` - 仪表盘统计
- `GET /api/admin/statistics/daily` - 每日统计
- `GET /api/admin/login_logs` - 登录日志

## 数据库表结构

- `tb_user` - 用户表
- `tb_category` - 知识库分类表
- `tb_document` - 文档表
- `tb_qa_history` - 问答历史记录表
- `tb_config` - 系统配置表
- `tb_login_log` - 登录日志表

## 开发说明

1. 代码包含完整中文注释
2. 密码使用MD5加密存储
3. 使用JWT进行身份认证
4. 支持CORS跨域请求