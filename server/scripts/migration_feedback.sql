-- 用户反馈表升级脚本（用于已有数据库，无需重建）
-- 新增 tb_qa_feedback：用户对回答点赞/点踩，收集badcase驱动迭代

CREATE TABLE IF NOT EXISTS tb_qa_feedback (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='问答反馈表';
