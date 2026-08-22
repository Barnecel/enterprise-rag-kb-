# -*- coding: utf-8 -*-
"""
数据库连接工具模块
提供MySQL数据库连接和基础操作封装
"""

import pymysql
from pymysql.cursors import DictCursor
from contextlib import contextmanager
from config.settings import DB_CONFIG

def get_db_connection():
    """
    获取数据库连接对象

    Returns:
        Connection: MySQL数据库连接对象
    """
    connection = pymysql.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        database=DB_CONFIG['database'],
        charset=DB_CONFIG['charset'],
        cursorclass=DictCursor
    )
    return connection


@contextmanager
def get_db_session():
    """
    数据库会话上下文管理器
    自动处理连接的开启和关闭

    Yields:
        Connection: 数据库连接对象
    """
    connection = get_db_connection()
    try:
        yield connection
        connection.commit()
    except Exception as e:
        connection.rollback()
        raise e
    finally:
        connection.close()


def execute_query(sql, params=None):
    """
    执行查询SQL语句

    Args:
        sql: SQL查询语句
        params: 查询参数元组

    Returns:
        List[Dict]: 查询结果列表
    """
    with get_db_session() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()


def execute_update(sql, params=None):
    """
    执行更新SQL语句(INSERT/UPDATE/DELETE)

    Args:
        sql: SQL语句
        params: 参数元组

    Returns:
        int: 受影响的行数
    """
    with get_db_session() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.rowcount


def execute_insert(sql, params=None):
    """
    执行插入SQL并返回自增ID

    Args:
        sql: INSERT语句
        params: 参数元组

    Returns:
        int: 新插入记录的自增ID
    """
    with get_db_session() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.lastrowid