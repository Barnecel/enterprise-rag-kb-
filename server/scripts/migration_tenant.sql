-- =============================================
-- 部门级租户隔离 增量迁移脚本
-- 用于已有数据库升级（新增 tb_tenant 表 + tenant_id 列）
-- 目标库: db_enterprise_9a
-- =============================================

USE db_enterprise_9a;

-- 1. 部门租户表
CREATE TABLE IF NOT EXISTS tb_tenant (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '部门租户ID',
    name VARCHAR(100) NOT NULL UNIQUE COMMENT '部门名称',
    description VARCHAR(500) COMMENT '部门描述',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='部门租户表';

-- 2. 给用户和文档表增加 tenant_id 列（MySQL 不支持 IF NOT EXISTS，用存储过程判断）
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

CALL add_column_if_missing('tb_user', 'tenant_id', 'tenant_id INT DEFAULT 1 COMMENT ''所属部门租户ID'' AFTER role');
CALL add_column_if_missing('tb_document', 'tenant_id', 'tenant_id INT DEFAULT 1 COMMENT ''所属部门租户ID'' AFTER category_id');
DROP PROCEDURE IF EXISTS add_column_if_missing;

-- 3. 种子数据：5个演示部门
INSERT INTO tb_tenant (id, name, description) VALUES
    (1, '默认租户', '默认部门'),
    (2, '技术部', '技术研发'),
    (3, '市场部', '市场营销'),
    (4, '财务部', '财务管理'),
    (5, '人力资源部', '人力行政')
ON DUPLICATE KEY UPDATE name = VALUES(name), description = VALUES(description);

-- 4. 历史数据归入默认租户
UPDATE tb_user SET tenant_id = 1 WHERE tenant_id IS NULL OR tenant_id = 0;
UPDATE tb_document SET tenant_id = 1 WHERE tenant_id IS NULL OR tenant_id = 0;

-- 5. 索引
CREATE INDEX idx_user_tenant ON tb_user (tenant_id);
CREATE INDEX idx_doc_tenant ON tb_document (tenant_id);
