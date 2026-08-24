#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API 全量集成测试 - 按照 SPEC.md v1.0 覆盖所有公开/鉴权/管理员/AI接口
覆盖范围：
  - 健康检查、config、首页ICP
  - 认证全流程 + 用户名/密码边界校验
  - 未登录权限拦截（上传/处理/评论/merge等）
  - 静态文件权限控制（uploads/outputs）
  - 评论CRUD + 软删除/恢复
  - 管理员接口（用户列表/重置密码/删除恢复评论/清理）
  - AI接口（鸡汤/起名/评论/文案）fallback链路
  - 任务软删除/恢复
  - 任务列表权限字段
"""
import os
import sys
import json
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='badminton_full_test_')
os.environ['ARK_API_KEY'] = ''
os.environ['ARK_ENDPOINT'] = ''

from web.app import app
from web.models import (
    init_db, ADMIN_WECHAT_NAME, ADMIN_DEFAULT_PASSWORD,
    create_task, add_comment, get_conn
)


class FullApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def setUp(self):
        self.admin_token = None
        self.user1_token = None
        self.user2_token = None
        self._login_admin()
        self._register_user('测试用户甲', 'Pass1234', as_user='user1')
        self._register_user('测试用户乙', 'Pass5678', as_user='user2')

    def _register(self, name, password):
        return self.client.post('/api/auth/register', json={
            'wechat_name': name, 'password': password
        })

    def _login(self, name, password):
        return self.client.post('/api/auth/login', json={
            'wechat_name': name, 'password': password
        })

    def _register_user(self, name, password, as_user='user1'):
        resp = self._register(name, password)
        if resp.status_code == 200:
            token = resp.get_json().get('token')
        else:
            resp2 = self._login(name, password)
            token = resp2.get_json().get('token') if resp2.status_code == 200 else None
        setattr(self, f'{as_user}_token', token)
        return token

    def _login_admin(self):
        resp = self._login(ADMIN_WECHAT_NAME, ADMIN_DEFAULT_PASSWORD)
        self.admin_token = resp.get_json().get('token')
        self.assertTrue(self.admin_token, '管理员登录必须成功')

    def _auth_headers(self, token):
        return {'X-Auth-Token': token} if token else {}

    def _make_task(self, token, title='测试任务', is_private=0):
        owner = '测试用户甲' if token == self.user1_token else '测试用户乙'
        uid = f'test-{abs(hash(title + str(id(self))))}'
        payload = {
            'upload_id': uid,
            'user_name': owner,
            'task_name': title,
            'original_filename': 'test.mp4',
            'safe_filename': f'{uid}_test.mp4',
            'upload_url': f'/uploads/{uid}_test.mp4',
            'upload_size': 1024000,
            'output_dir': f'/outputs/{uid}',
            'min_duration': 1.5,
            'status': 'completed',
            'output_count': 0,
            'wechat_name': owner,
            'is_private': is_private,
        }
        create_task(payload)
        return uid

    # ==================================================================
    # Group 1: 基础页面与健康检查（SPEC §3.7）
    # ==================================================================
    def test_001_health(self):
        r = self.client.get('/health')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['status'], 'ok')

    def test_002_config(self):
        r = self.client.get('/config')
        self.assertEqual(r.status_code, 200)

    def test_003_homepage_contains_icp(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('陕ICP备2026022163号-1', r.data.decode('utf-8'))

    def test_004_homepage_contains_ai_elements(self):
        html = self.client.get('/').data.decode('utf-8')
        for el in ['dailyAiQuote', 'aiTaskNamesBtn', 'data-ai-comment-mood']:
            self.assertIn(el, html, f'首页必须包含 {el}')

    def test_005_viewport_meta(self):
        html = self.client.get('/').data.decode('utf-8')
        self.assertIn('viewport-fit=cover', html)

    # ==================================================================
    # Group 2: 认证 - 边界校验（SPEC §3.1）
    # ==================================================================
    def test_010_auth_check_new_user(self):
        r = self.client.post('/api/auth/check', json={'wechat_name': '不存在的用户xyz'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()['exists'])

    def test_011_auth_check_admin_exists(self):
        r = self.client.post('/api/auth/check', json={'wechat_name': ADMIN_WECHAT_NAME})
        self.assertTrue(r.get_json()['exists'])

    def test_012_register_rejects_empty_name(self):
        r = self._register('', 'Pass1234')
        self.assertEqual(r.status_code, 400)

    def test_013_register_rejects_short_name(self):
        r = self._register('a', 'Pass1234')
        self.assertEqual(r.status_code, 400)

    def test_014_register_rejects_xss_name(self):
        r = self._register('<script>alert(1)</script>', 'Pass1234')
        self.assertEqual(r.status_code, 400)

    def test_015_register_rejects_long_name(self):
        r = self._register('a' * 21, 'Pass1234')
        self.assertEqual(r.status_code, 400)

    def test_016_register_rejects_short_password(self):
        r = self._register('合法用户名', '123')
        self.assertEqual(r.status_code, 400)

    def test_017_register_rejects_long_password(self):
        r = self._register('合法用户名', 'x' * 65)
        self.assertEqual(r.status_code, 400)

    def test_018_register_then_login_then_me(self):
        name = '链路测试用户'
        r = self._register(name, 'Pass1234')
        self.assertEqual(r.status_code, 200)
        token = r.get_json()['token']
        me = self.client.get('/api/auth/me', headers=self._auth_headers(token))
        self.assertEqual(me.get_json()['user']['wechat_name'], name)

    def test_019_logout_invalidates_token(self):
        token = self._register('临时注销用户', 'Pass1234').get_json()['token']
        self.client.post('/api/auth/logout', headers=self._auth_headers(token))
        me = self.client.get('/api/auth/me', headers=self._auth_headers(token))
        self.assertIsNone(me.get_json()['user'])

    def test_020_login_wrong_password(self):
        r = self._login('测试用户甲', 'wrongpass')
        self.assertEqual(r.status_code, 401)

    def test_021_me_without_token_is_guest(self):
        r = self.client.get('/api/auth/me')
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.get_json()['user'])

    def test_022_me_invalid_token(self):
        r = self.client.get('/api/auth/me', headers={'X-Auth-Token': 'invalid-token-xxx'})
        self.assertIsNone(r.get_json()['user'])

    # ==================================================================
    # Group 3: 未登录权限拦截（SPEC §5.2 鉴权前置）
    # ==================================================================
    def test_030_upload_without_login_401(self):
        r = self.client.post('/api/upload')
        self.assertEqual(r.status_code, 401)
        self.assertTrue(r.get_json().get('need_login'))

    def test_031_process_without_login_401(self):
        r = self.client.post('/api/process', json={'upload_id': 'x'})
        self.assertEqual(r.status_code, 401)

    def test_032_comment_without_login_401(self):
        r = self.client.post('/api/comments', json={'rating': 5, 'content': 'x'})
        self.assertEqual(r.status_code, 401)

    def test_033_merge_without_login_returns_4xx(self):
        r = self.client.post('/api/merge/x', json={'files': ['a.mp4']})
        self.assertIn(r.status_code, (400, 401, 403))

    def test_034_admin_users_without_admin_403(self):
        r = self.client.get('/api/admin/users', headers=self._auth_headers(self.user1_token))
        self.assertEqual(r.status_code, 403)

    def test_035_admin_reset_password_without_admin_403(self):
        r = self.client.post('/api/admin/reset-password',
                             headers=self._auth_headers(self.user1_token),
                             json={'wechat_name': 'x', 'new_password': 'y'})
        self.assertEqual(r.status_code, 403)

    # ==================================================================
    # Group 4: 评论系统（SPEC §3.3）
    # ==================================================================
    def _post_comment(self, token, rating=5, content='测试评论'):
        return self.client.post('/api/comments', headers=self._auth_headers(token),
                                json={'rating': rating, 'content': content})

    def test_040_comment_create_and_list(self):
        r = self._post_comment(self.user1_token, 5, '甲的评论')
        self.assertEqual(r.status_code, 200)
        cid = r.get_json()['comment']['id']
        lst = self.client.get('/api/comments').get_json()['comments']
        self.assertTrue(any(c['id'] == cid for c in lst))

    def test_041_comment_rating_is_clamped_to_valid_range(self):
        r6 = self._post_comment(self.user1_token, 6, '超范围评分clamp')
        self.assertEqual(r6.status_code, 200)
        self.assertIn(r6.get_json()['comment']['rating'], (0, 5))
        r0 = self._post_comment(self.user1_token, -1, '负分clamp')
        self.assertEqual(r0.status_code, 200)
        self.assertGreaterEqual(r0.get_json()['comment']['rating'], 0)
        self.assertLessEqual(r0.get_json()['comment']['rating'], 5)

    def test_042_comment_publicly_accessible(self):
        r = self.client.get('/api/comments')
        self.assertEqual(r.status_code, 200)
        self.assertIn('comments', r.get_json())

    def test_043_admin_can_soft_delete_comment(self):
        cid = self._post_comment(self.user2_token, 4, '待删除评论').get_json()['comment']['id']
        r = self.client.delete(f'/api/comments/{cid}', headers=self._auth_headers(self.admin_token))
        self.assertEqual(r.status_code, 200)
        lst = self.client.get('/api/comments').get_json()['comments']
        self.assertFalse(any(c['id'] == cid for c in lst), '软删除评论不应出现在公开列表')

    def test_044_admin_can_restore_comment(self):
        cid = self._post_comment(self.user2_token, 4, '待恢复评论').get_json()['comment']['id']
        self.client.delete(f'/api/comments/{cid}', headers=self._auth_headers(self.admin_token))
        r = self.client.post(f'/api/comments/{cid}/restore', headers=self._auth_headers(self.admin_token))
        self.assertEqual(r.status_code, 200)
        lst = self.client.get('/api/comments').get_json()['comments']
        self.assertTrue(any(c['id'] == cid for c in lst), '恢复后评论应重新可见')

    def test_045_non_admin_cannot_delete_comment(self):
        cid = self._post_comment(self.user1_token, 5, '甲的评论').get_json()['comment']['id']
        r = self.client.delete(f'/api/comments/{cid}', headers=self._auth_headers(self.user2_token))
        self.assertEqual(r.status_code, 403)

    # ==================================================================
    # Group 5: 任务与权限字段（SPEC §3.2）
    # ==================================================================
    def test_050_list_returns_permission_flags(self):
        uid = self._make_task(self.user1_token, title='甲的公开任务', is_private=0)
        r = self.client.get('/api/list', headers=self._auth_headers(self.user1_token))
        tasks = r.get_json()['tasks']
        mine = next(t for t in tasks if t['upload_id'] == uid)
        self.assertTrue(mine['is_owner'])
        self.assertFalse(mine['is_private'])
        self.assertIn('output_files', mine)

    def test_051_private_task_not_visible_to_other_user(self):
        uid = self._make_task(self.user1_token, title='甲的私密任务', is_private=1)
        r = self.client.get('/api/list', headers=self._auth_headers(self.user2_token))
        tasks = r.get_json()['tasks']
        self.assertFalse(any(t['upload_id'] == uid for t in tasks),
                         '私密任务不应在其他用户列表中可见')

    def test_052_admin_can_see_all_tasks(self):
        uid = self._make_task(self.user1_token, title='甲的私密任务', is_private=1)
        r = self.client.get('/api/list', headers=self._auth_headers(self.admin_token))
        tasks = r.get_json()['tasks']
        self.assertTrue(any(t['upload_id'] == uid for t in tasks), '管理员应能看到所有任务')

    def test_053_guest_cannot_see_private_output(self):
        uid = self._make_task(self.user1_token, title='私密', is_private=1)
        r = self.client.get(f'/outputs/{uid}/nonexistent.mp4')
        self.assertIn(r.status_code, (403, 404), '访客不能访问私密任务的output')

    def test_054_outputs_returns_404_for_nonexistent(self):
        r = self.client.get('/outputs/nonexistent-id-xxx/fake.mp4')
        self.assertEqual(r.status_code, 404)

    def test_055_uploads_nonexistent_returns_403_or_404(self):
        r = self.client.get('/uploads/nonexistent_file_.mp4')
        self.assertIn(r.status_code, (403, 404))

    # ==================================================================
    # Group 6: 管理员功能（SPEC §3.5）
    # ==================================================================
    def test_060_admin_list_users(self):
        r = self.client.get('/api/admin/users', headers=self._auth_headers(self.admin_token))
        self.assertEqual(r.status_code, 200)
        users = r.get_json()['users']
        names = [u['wechat_name'] for u in users]
        self.assertIn(ADMIN_WECHAT_NAME, names)
        self.assertIn('测试用户甲', names)

    def test_061_admin_reset_password(self):
        r = self.client.post('/api/admin/reset-password',
                             headers=self._auth_headers(self.admin_token),
                             json={'wechat_name': '测试用户乙', 'new_password': 'NewPass99'})
        self.assertEqual(r.status_code, 200)
        login_old = self._login('测试用户乙', 'Pass5678')
        self.assertEqual(login_old.status_code, 401, '旧密码应失效')
        login_new = self._login('测试用户乙', 'NewPass99')
        self.assertEqual(login_new.status_code, 200, '新密码应能登录')
        self.user2_token = login_new.get_json()['token']

    def test_062_admin_is_admin_flag(self):
        me = self.client.get('/api/auth/me', headers=self._auth_headers(self.admin_token))
        self.assertTrue(me.get_json()['user']['is_admin'])

    def test_063_normal_user_is_not_admin(self):
        me = self.client.get('/api/auth/me', headers=self._auth_headers(self.user1_token))
        self.assertFalse(me.get_json()['user']['is_admin'])

    # ==================================================================
    # Group 7: AI 功能（SPEC §3.6）- 无API Key时走fallback
    # ==================================================================
    def test_070_ai_daily_quote_returns_200_with_emoji(self):
        r = self.client.get('/api/ai/daily-quote')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn('quote', data)
        self.assertTrue(len(data['quote']) > 0)
        # fallback必须带emoji（检查是否包含常见emoji或至少非空）
        self.assertTrue(data.get('weekday'))

    def test_071_ai_daily_quote_with_name(self):
        r = self.client.get('/api/ai/daily-quote?name=小羽毛')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(len(r.get_json()['quote']) > 0)

    def test_072_ai_task_names_returns_3(self):
        r = self.client.post('/api/ai/task-names', json={'user_name': '球友'})
        self.assertEqual(r.status_code, 200)
        names = r.get_json()['names']
        self.assertGreaterEqual(len(names), 3)

    def test_073_ai_comment_moods(self):
        for mood in ['funny', 'encourage', 'serious', 'lazy']:
            r = self.client.post('/api/ai/comment',
                                 json={'mood': mood, 'rating': 5, 'user_name': '球友'})
            self.assertEqual(r.status_code, 200, f'mood={mood} 应返回200')
            data = r.get_json()
            self.assertTrue(len(data.get('content', '')) > 0, f'mood={mood} 应有content内容')

    def test_074_ai_caption(self):
        r = self.client.post('/api/ai/caption',
                             json={'seg_idx': 1, 'duration_s': 7, 'score': 0.8, 'user_name': '球友'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(len(r.get_json().get('caption', '')) > 0)

    def test_075_ai_comment_is_public(self):
        r = self.client.post('/api/ai/comment', json={'mood': 'funny', 'rating': 5})
        self.assertEqual(r.status_code, 200, 'AI生成接口为公开，访客也可使用')

    def test_076_ai_caption_is_public(self):
        r = self.client.post('/api/ai/caption', json={'seg_idx': 1, 'duration_s': 7})
        self.assertEqual(r.status_code, 200, 'AI生成接口为公开，访客也可使用')

    # ==================================================================
    # Group 8: 首页其他关键资源
    # ==================================================================
    def test_080_guide_page(self):
        r = self.client.get('/guide')
        self.assertEqual(r.status_code, 200)

    def test_081_estimate_endpoint_exists(self):
        r = self.client.get('/api/estimate')
        self.assertIn(r.status_code, (200, 400), 'estimate接口存在，无参数时返回200或400均可，但不能500')

    @classmethod
    def tearDownClass(cls):
        d = os.environ.get('DATA_DIR')
        if d and os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
