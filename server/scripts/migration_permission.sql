-- =============================================
-- 部门 + 密级 + ACL 三层权限 增量迁移脚本
-- 用于已有数据库升级（新增 clearance_level / min_level / tb_document_acl）
-- 目标库: db_enterprise_9a
-- 执行: mysql -h127.0.0.1 -P3308 -uroot -p123456 db_enterprise_9a < migration_permission.sql
-- =============================================

USE db_enterprise_9a;

-- 1. 用户密级列（复用 add_column_if_missing 存储过程判断）
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

-- 用户密级：1公开/2内部/3机密/4绝密
CALL add_column_if_missing('tb_user', 'clearance_level',
    'clearance_level INT NOT NULL DEFAULT 1 COMMENT ''用户密级:1公开/2内部/3机密/4绝密'' AFTER role');
-- 文档最低密级：1公开/2内部/3机密/4绝密
CALL add_column_if_missing('tb_document', 'min_level',
    'min_level INT NOT NULL DEFAULT 1 COMMENT ''文档最低密级:1公开/2内部/3机密/4绝密'' AFTER doc_level');
DROP PROCEDURE IF EXISTS add_column_if_missing;

-- 2. 文档ACL授权表（逐用户显式授权，覆盖部门与密级）
CREATE TABLE IF NOT EXISTS tb_document_acl (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'ACL记录ID',
    document_id INT NOT NULL COMMENT '文档ID',
    user_id INT NOT NULL COMMENT '被授权用户ID',
    granted_by INT COMMENT '授权人ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '授权时间',
    UNIQUE KEY uk_doc_user (document_id, user_id),
    KEY idx_acl_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档ACL授权表';

-- 3. 文档权限查询索引
CREATE INDEX idx_doc_tenant_level ON tb_document (tenant_id, doc_level, min_level);
