-- 模型API接入配置表（局域网/互联网 OpenAI兼容端点）
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
