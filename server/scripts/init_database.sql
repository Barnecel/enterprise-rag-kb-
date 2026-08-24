-- =============================================
-- 企业内部知识库问答Agent系统数据库建表SQL
-- 数据库名: db_enterprise_9a
-- 端口: 3308
-- =============================================

-- 创建数据库
CREATE DATABASE IF NOT EXISTS db_enterprise_9a DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE db_enterprise_9a;

-- =============================================
-- 部门租户表 (tb_tenant)
-- =============================================
DROP TABLE IF EXISTS tb_tenant;
CREATE TABLE tb_tenant (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '部门租户ID',
    name VARCHAR(100) NOT NULL UNIQUE COMMENT '部门名称',
    description VARCHAR(500) COMMENT '部门描述',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='部门租户表';

-- 种子部门数据
INSERT INTO tb_tenant (id, name, description) VALUES
(1, '默认租户', '默认部门'),
(2, '技术部', '技术研发'),
(3, '市场部', '市场营销'),
(4, '财务部', '财务管理'),
(5, '人力资源部', '人力行政');

-- =============================================
-- 用户表 (tb_user)
-- =============================================
DROP TABLE IF EXISTS tb_user;
CREATE TABLE tb_user (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '用户ID',
    username VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
    password VARCHAR(32) NOT NULL COMMENT '密码(MD5加密)',
    real_name VARCHAR(50) COMMENT '真实姓名',
    email VARCHAR(100) COMMENT '邮箱',
    phone VARCHAR(20) COMMENT '手机号',
    role ENUM('admin', 'user') NOT NULL DEFAULT 'user' COMMENT '角色: admin=管理员, user=普通用户',
    clearance_level INT NOT NULL DEFAULT 1 COMMENT '用户密级:1公开/2内部/3机密/4绝密',
    tenant_id INT DEFAULT 1 COMMENT '所属部门租户ID',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 0=禁用, 1=正常',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_user_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- =============================================
-- 知识库分类表 (tb_category)
-- =============================================
DROP TABLE IF EXISTS tb_category;
CREATE TABLE tb_category (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '分类ID',
    name VARCHAR(100) NOT NULL COMMENT '分类名称',
    description VARCHAR(500) COMMENT '分类描述',
    parent_id INT DEFAULT 0 COMMENT '父分类ID,0表示顶级分类',
    sort_order INT DEFAULT 0 COMMENT '排序序号',
    created_by INT COMMENT '创建人ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库分类表';

-- =============================================
-- 文档表 (tb_document)
-- =============================================
DROP TABLE IF EXISTS tb_document;
CREATE TABLE tb_document (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '文档ID',
    title VARCHAR(200) NOT NULL COMMENT '文档标题',
    content MEDIUMTEXT COMMENT '文档内容摘要',
    file_path VARCHAR(500) COMMENT '文件存储路径',
    file_name VARCHAR(200) COMMENT '原始文件名',
    file_size BIGINT COMMENT '文件大小(字节)',
    file_hash VARCHAR(64) COMMENT '文件SHA256哈希(用于去重)',
    file_type VARCHAR(50) COMMENT '文件类型',
    category_id INT COMMENT '所属分类ID',
    tenant_id INT DEFAULT 1 COMMENT '所属部门租户ID',
    vector_id VARCHAR(100) COMMENT '向量库ID(Chroma)',
    status ENUM('pending', 'processing', 'completed', 'failed') DEFAULT 'pending' COMMENT '处理状态',
    upload_by INT COMMENT '上传用户ID',
    doc_level ENUM('public', 'private') DEFAULT 'public' COMMENT '文档级别: public=公开, private=私密',
    min_level INT NOT NULL DEFAULT 1 COMMENT '文档最低密级:1公开/2内部/3机密/4绝密',
    view_count INT DEFAULT 0 COMMENT '浏览次数',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '上传时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_doc_tenant (tenant_id),
    INDEX idx_doc_tenant_level (tenant_id, doc_level, min_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档表';

-- =============================================
-- 文档ACL授权表 (tb_document_acl)
-- 逐用户显式授权，覆盖部门与密级（跨部门例外）
-- =============================================
DROP TABLE IF EXISTS tb_document_acl;
CREATE TABLE tb_document_acl (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'ACL记录ID',
    document_id INT NOT NULL COMMENT '文档ID',
    user_id INT NOT NULL COMMENT '被授权用户ID',
    granted_by INT COMMENT '授权人ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '授权时间',
    UNIQUE KEY uk_doc_user (document_id, user_id),
    KEY idx_acl_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档ACL授权表';

-- =============================================
-- 问答记录表 (tb_qa_history)
-- =============================================
DROP TABLE IF EXISTS tb_qa_history;
CREATE TABLE tb_qa_history (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '记录ID',
    user_id INT NOT NULL COMMENT '用户ID',
    conversation_id INT NULL COMMENT '所属会话ID',
    question TEXT NOT NULL COMMENT '用户问题',
    answer TEXT COMMENT '系统回答',
    documents TEXT COMMENT '参考的文档ID列表(JSON格式)',
    model_used VARCHAR(50) COMMENT '使用的模型',
    token_count INT COMMENT '消耗的token数',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '提问时间',
    INDEX idx_qa_conv (user_id, conversation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='问答历史记录表';

-- =============================================
-- 问答会话表 (tb_qa_conversation)
-- =============================================
DROP TABLE IF EXISTS tb_qa_conversation;
CREATE TABLE tb_qa_conversation (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '会话ID',
    user_id INT NOT NULL COMMENT '用户ID',
    title VARCHAR(100) NOT NULL DEFAULT '新对话' COMMENT '会话标题',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_conv_user (user_id),
    INDEX idx_conv_user_updated (user_id, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='问答会话表';

-- =============================================
-- 系统配置表 (tb_config)
-- =============================================
DROP TABLE IF EXISTS tb_config;
CREATE TABLE tb_config (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '配置ID',
    config_key VARCHAR(100) NOT NULL UNIQUE COMMENT '配置键',
    config_value TEXT COMMENT '配置值',
    description VARCHAR(200) COMMENT '配置说明',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统配置表';

-- =============================================
-- 登录日志表 (tb_login_log)
-- =============================================
DROP TABLE IF EXISTS tb_login_log;
CREATE TABLE tb_login_log (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '日志ID',
    user_id INT COMMENT '用户ID',
    username VARCHAR(50) COMMENT '用户名',
    ip_address VARCHAR(50) COMMENT 'IP地址',
    login_status TINYINT COMMENT '登录状态: 1=成功, 0=失败',
    login_message VARCHAR(200) COMMENT '登录消息',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '登录时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='登录日志表';

-- =============================================
-- 问答反馈表 (tb_qa_feedback)
-- 用户对回答点赞/点踩，用于收集badcase驱动检索与生成质量迭代
-- =============================================
DROP TABLE IF EXISTS tb_qa_feedback;
CREATE TABLE tb_qa_feedback (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '反馈ID',
    history_id INT NOT NULL COMMENT '关联的问答记录ID(tb_qa_history.id)',
    user_id INT NOT NULL COMMENT '反馈用户ID',
    rating TINYINT NOT NULL COMMENT '评价: 1=赞, -1=踩',
    reason VARCHAR(255) DEFAULT NULL COMMENT '点踩原因(可选)',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_history_user (history_id, user_id),
    INDEX idx_rating (rating),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='问答反馈表';-- 模型API接入配置表（局域网/互联网 OpenAI兼容端点）
CREATE TABLE IF NOT EXISTS tb_model_config (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '配置ID',
    name VARCHAR(100) NOT NULL COMMENT '显示名称',
    model_type ENUM('llm','embedding') NOT NULL COMMENT '模型角色',
    provider VARCHAR(50) NOT NULL DEFAULT 'openai_compatible' COMMENT '协议族',
    api_base VARCHAR(255) NOT NULL COMMENT '端点地址(含/v1)',
    api_key VARCHAR(512) DEFAULT '' COMMENT '密钥',
    model_name VARCHAR(100) NOT NULL COMMENT '模型名',
    is_active TINYINT NOT NULL DEFAULT 0 COMMENT '是否启用:每类型仅一个',
    pending_rebuild TINYINT NOT NULL DEFAULT 0 COMMENT '嵌入切换后待重建向量库',
    remark VARCHAR(255) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_type_active (model_type, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模型API接入配置';
