#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
权限系统本地单元测试 - 使用Flask test_client
覆盖2026-08-21迭代功能:
  1. 密码登录认证系统
  2. 任务私有可见权限
  3. 管理员权限控制
"""
import os
import sys
import json
import tempfile
import shutil
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 使用临时数据库
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='badminton_test_')

from web.app import app
from web.models import init_db, ADMIN_WECHAT_NAME, ADMIN_DEFAULT_PASSWORD


class AuthSystemTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def setUp(self):
        self.admin_token = None
        self.user1_token = None
        self.user2_token = None

    def _register(self, name, password):
        return self.client.post('/api/auth/register', json={
            'wechat_name': name, 'password': password
        })

    def _login(self, name, password):
        return self.client.post('/api/auth/login', json={
            'wechat_name': name, 'password': password
        })

    def _me(self, token=None):
        headers = {}
        if token:
            headers['X-Auth-Token'] = token
        return self.client.get('/api/auth/me', headers=headers)

    def _logout(self, token):
        return self.client.post('/api/auth/logout', headers={'X-Auth-Token': token})

    def _list(self, token=None):
        headers = {}
        if token:
            headers['X-Auth-Token'] = token
        return self.client.get('/api/list', headers=headers)

    def _comments_post(self, token, rating, content):
        return self.client.post('/api/comments', headers={'X-Auth-Token': token}, json={
            'rating': rating, 'content': content
        })

    # ==================================================================
    # Test Group 1: 健康检查
    # ==================================================================
    def test_01_health_endpoint(self):
        resp = self.client.get('/health')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'ok')

    # ==================================================================
    # Test Group 2: 用户检查接口
    # ==================================================================
    def test_02_auth_check_new_user(self):
        resp = self.client.post('/api/auth/check', json={'wechat_name': 'newbie'})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.get_json()['exists'])

    def test_03_auth_check_admin_exists(self):
        resp = self.client.post('/api/auth/check', json={'wechat_name': ADMIN_WECHAT_NAME})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['exists'])

    def test_04_auth_check_empty_name(self):
        resp = self.client.post('/api/auth/check', json={'wechat_name': ''})
        self.assertEqual(resp.status_code, 400)

    # ==================================================================
    # Test Group 3: 注册流程
    # ==================================================================
    def test_05_register_password_too_short(self):
        resp = self._register('shortpwd', '123')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('密码', resp.get_json()['error'])

    def test_06_register_success(self):
        resp = self._register('user1', 'pass1234')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('token', data)
        self.assertFalse(data['user']['is_admin'])
        self.user1_token = data['token']

    def test_07_register_duplicate(self):
        self._register('dup_user', 'pass1234')
        resp = self._register('dup_user', 'pass5678')
        self.assertEqual(resp.status_code, 400)

    def test_08_register_empty_name(self):
        resp = self._register('', 'pass1234')
        self.assertEqual(resp.status_code, 400)

    # ==================================================================
    # Test Group 4: 登录流程
    # ==================================================================
    def test_09_login_wrong_password(self):
        self._register('logintest', 'correctpass')
        resp = self._login('logintest', 'wrongpass')
        self.assertEqual(resp.status_code, 401)

    def test_10_login_success(self):
        self._register('logintest2', 'mypassword')
        resp = self._login('logintest2', 'mypassword')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('token', data)
        self.user2_token = data['token']

    def test_11_admin_login(self):
        resp = self._login(ADMIN_WECHAT_NAME, ADMIN_DEFAULT_PASSWORD)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['user']['is_admin'])
        self.admin_token = data['token']

    def test_12_login_nonexistent_user(self):
        resp = self._login('nonexistent_xyz', 'anypass')
        self.assertEqual(resp.status_code, 401)

    # ==================================================================
    # Test Group 5: /api/auth/me 接口
    # ==================================================================
    def test_13_me_without_token(self):
        resp = self._me()
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.get_json()['user'])

    def test_14_me_with_valid_token(self):
        r = self._register('me_test', 'pass1234')
        token = r.get_json()['token']
        resp = self._me(token)
        self.assertEqual(resp.status_code, 200)
        user = resp.get_json()['user']
        self.assertEqual(user['wechat_name'], 'me_test')
        self.assertFalse(user['is_admin'])

    def test_15_me_invalid_token(self):
        resp = self._me('invalid_token_xxx')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.get_json()['user'])

    def test_16_me_admin_token(self):
        r = self._login(ADMIN_WECHAT_NAME, ADMIN_DEFAULT_PASSWORD)
        token = r.get_json()['token']
        resp = self._me(token)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['user']['is_admin'])

    # ==================================================================
    # Test Group 6: 退出登录
    # ==================================================================
    def test_17_logout_then_token_invalid(self):
        r = self._register('logout_test', 'pass1234')
        token = r.get_json()['token']
        logout_resp = self._logout(token)
        self.assertEqual(logout_resp.status_code, 200)
        me_resp = self._me(token)
        self.assertIsNone(me_resp.get_json()['user'])

    # ==================================================================
    # Test Group 7: 未登录访问写接口返回401
    # ==================================================================
    def test_18_comment_without_login_returns_401(self):
        resp = self.client.post('/api/comments', json={'rating': 5, 'content': 'test'})
        self.assertEqual(resp.status_code, 401)
        self.assertTrue(resp.get_json().get('need_login'))

    def test_19_list_without_login_ok(self):
        resp = self._list()
        self.assertEqual(resp.status_code, 200)
        self.assertIn('tasks', resp.get_json())

    # ==================================================================
    # Test Group 8: 登录后功能可用
    # ==================================================================
    def test_20_comment_after_login_success(self):
        r = self._register('commenter', 'pass1234')
        token = r.get_json()['token']
        resp = self._comments_post(token, 5, '测试评论内容')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('comment', resp.get_json())

    def test_21_comment_rating_validation(self):
        r = self._register('rater', 'pass1234')
        token = r.get_json()['token']
        resp = self._comments_post(token, 999, 'rating should be clamped')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['comment']['rating'], 5)

    # ==================================================================
    # Test Group 9: 列表权限结构
    # ==================================================================
    def test_22_list_returns_correct_structure(self):
        r = self._register('lister', 'pass1234')
        token = r.get_json()['token']
        resp = self._list(token)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('tasks', data)
        self.assertIn('task_names', data)
        self.assertIn('is_admin', data)
        self.assertIn('current_user', data)
        self.assertFalse(data['is_admin'])
        self.assertEqual(data['current_user']['wechat_name'], 'lister')

    def test_23_list_admin_sees_all_flag(self):
        r = self._login(ADMIN_WECHAT_NAME, ADMIN_DEFAULT_PASSWORD)
        token = r.get_json()['token']
        resp = self._list(token)
        data = resp.get_json()
        self.assertTrue(data['is_admin'])
        self.assertTrue(data['current_user']['is_admin'])
        self.assertEqual(data['current_user']['wechat_name'], ADMIN_WECHAT_NAME)

    def test_24_task_fields_contain_permission_flags(self):
        r = self._register('field_check', 'pass1234')
        token = r.get_json()['token']
        resp = self._list(token)
        data = resp.get_json()
        for task in data['tasks']:
            self.assertIn('is_private', task)
            self.assertIn('is_owner', task)
            self.assertIn('is_admin', task)

    # ==================================================================
    # Test Group 10: 评论列表公开可见
    # ==================================================================
    def test_25_comments_publicly_accessible(self):
        resp = self.client.get('/api/comments')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('comments', resp.get_json())
        self.assertIn('stats', resp.get_json())


if __name__ == '__main__':
    print("=" * 60)
    print("🏸 无限进步球场 - 权限系统本地单元测试")
    print(f"⏰ 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.TestLoader().loadTestsFromTestCase(AuthSystemTestCase)
    result = runner.run(suite)

    print()
    print("=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    print(f"  运行用例: {result.testsRun}")
    print(f"  ✅ 成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  ❌ 失败: {len(result.failures)}")
    print(f"  ⚠️  错误: {len(result.errors)}")

    if result.wasSuccessful():
        print()
        print("🎉 所有测试用例通过！")
        sys.exit(0)
    else:
        print()
        if result.failures:
            print("失败详情:")
            for test, trace in result.failures:
                print(f"  - {test}: {trace.split(chr(10))[-2]}")
        if result.errors:
            print("错误详情:")
            for test, trace in result.errors:
                print(f"  - {test}: {trace.split(chr(10))[-2]}")
        sys.exit(1)
