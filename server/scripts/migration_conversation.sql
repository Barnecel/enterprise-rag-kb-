-- =============================================
-- 多会话问答 增量迁移脚本
-- 用于已有数据库升级（新增 tb_qa_conversation 会话表 + tb_qa_history.conversation_id 列）
-- 目标库: db_enterprise_9a
-- =============================================

USE db_enterprise_9a;

-- 1. 会话表
CREATE TABLE IF NOT EXISTS tb_qa_conversation (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '会话ID',
    user_id INT NOT NULL COMMENT '用户ID',
    title VARCHAR(100) NOT NULL DEFAULT '新对话' COMMENT '会话标题',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_conv_user (user_id),
    INDEX idx_conv_user_updated (user_id, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='问答会话表';

-- 2. 历史表加会话ID列（MySQL 不支持 IF NOT EXISTS，用存储过程判断）
DROP PROCEDURE IF EXISTS add_column_if_missing;
DELIMITER $$
CREATE PROCEDURE add_column_if_missing(IN tbl VARCHAR(64), IN col VARCHAR(64), IN ddl VARCHAR(255))
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = tbl AND COLUMN_NAME = col
    ) THEN
        SET @s = CONCAT('ALTER TABLE ', tbl, ' ADD COLUMN ', ddl);
        PREPARE stmt FROM @s;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

CALL add_column_if_missing('tb_qa_history', 'conversation_id', 'conversation_id INT NULL COMMENT ''所属会话ID'' AFTER user_id');
DROP PROCEDURE IF EXISTS add_column_if_missing;

CREATE INDEX idx_qa_conv ON tb_qa_history (user_id, conversation_id);

-- 3. 存量数据迁移：把每个已有历史记录的用户归入一个"历史记录"会话
DROP PROCEDURE IF EXISTS migrate_qa_conversations;
DELIMITER $$
CREATE PROCEDURE migrate_qa_conversations()
BEGIN
    DECLARE done INT DEFAULT 0;
    DECLARE u_id INT;
    DECLARE conv_id INT;
    DECLARE cur CURSOR FOR SELECT DISTINCT user_id FROM tb_qa_history WHERE conversation_id IS NULL;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = 1;

    OPEN cur;
    read_loop: LOOP
        FETCH cur INTO u_id;
        IF done THEN
            LEAVE read_loop;
        END IF;

        -- 为用户创建一个"历史记录"会话
        INSERT INTO tb_qa_conversation (user_id, title) VALUES (u_id, '历史记录');
        SET conv_id = LAST_INSERT_ID();

        -- 该用户所有旧记录归入此会话
        UPDATE tb_qa_history SET conversation_id = conv_id WHERE user_id = u_id AND conversation_id IS NULL;
    END LOOP;
    CLOSE cur;
END$$
DELIMITER ;

CALL migrate_qa_conversations();
DROP PROCEDURE IF EXISTS migrate_qa_conversations;
