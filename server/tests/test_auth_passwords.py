# -*- coding: utf-8 -*-
"""密码双算法迁移单元测试——bcrypt渐进迁移(缺陷③修复)的核心逻辑"""
import bcrypt
import pytest
from application.routes.auth import hash_password, verify_password, md5_encrypt


def test_bcrypt哈希格式与验证():
    h = hash_password('secret123')
    assert h.startswith('$2b$') and len(h) == 60
    assert verify_password('secret123', h) == (True, False)


def test_bcrypt错误密码拒绝():
    h = hash_password('secret123')
    assert verify_password('wrong', h) == (False, False)


def test_旧MD5哈希回退校验并标记升级():
    legacy = md5_encrypt('legacy123')
    assert verify_password('legacy123', legacy) == (True, True), '旧哈希匹配且需升级'


def test_旧MD5错误密码():
    legacy = md5_encrypt('legacy123')
    assert verify_password('nope', legacy) == (False, True)


def test_空存储拒绝():
    assert verify_password('x', '') == (False, False)
    assert verify_password('x', None) == (False, False)


def test_每次bcrypt盐不同():
    assert hash_password('same') != hash_password('same')


def test_真实迁移场景_MD5登录后升级为bcrypt():
    """模拟login路由的透明升级：旧哈希校验通过 → 重写为bcrypt → 新哈希校验通过"""
    stored = md5_encrypt('admin123')
    ok, need_upgrade = verify_password('admin123', stored)
    assert ok and need_upgrade
    stored = hash_password('admin123')          # 路由执行的升级
    ok, need_upgrade = verify_password('admin123', stored)
    assert ok and not need_upgrade
