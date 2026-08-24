# 🏸 无限进步球场 · 功能规格说明书（SPEC）

> 版本：v1.0 | 更新日期：2026-08-24 | 维护人：开发团队
> 规则：**每次功能迭代必须同步更新本文件**，并在更新日志中记录变更。

---

## 1. 产品概述

"无限进步球场"是一个面向羽毛球爱好者的视频自动切片工作站，支持上传比赛/训练录像，自动识别精彩片段并切分输出，让每段快乐都能单独保存。

**核心定位**：主打快乐，顺带进步。
**公网地址**：http://101.96.224.241/
**技术栈**：Flask + SQLite(WAL) + Gunicorn多worker + FFmpeg + ThreadPool异步队列

---

## 2. 用户角色与权限模型

| 角色 | 描述 | 权限 |
|------|------|------|
| **访客（未登录）** | 浏览公开内容 | 查看首页、公开任务列表、公开视频、公开评论；使用AI鸡汤/起名；上传/评论/私密访问被拦截 |
| **登录用户** | 注册并设置密码 | 上传视频、发起处理、查看自己的全部任务（含私有）、发表/删除自己的评论、下载自己和公开的视频、合并导出、使用全部AI功能 |
| **管理员** | 硬编码：微信名「行遇书」 | 所有普通用户权限 + 查看所有用户任务 + 硬删除任务及文件 + 删除/恢复任意评论 + 查看用户列表 + 重置任意用户密码 + 系统清理 |

---

## 3. 功能模块规格

### 3.1 认证系统（Auth）

#### 3.1.1 用户名校验规则
- 长度：2-20个字符
- 允许字符：中文、英文、数字、下划线、短横线、空格（不能以空格开头/结尾）
- 禁止：HTML标签（`<script>`等）、特殊字符（`<>"'&`）防止XSS
- 管理员名「行遇书」为保留字，首次启动时自动创建

#### 3.1.2 密码规则
- 长度：4-64字符
- 存储：使用 `werkzeug.security.generate_password_hash` 哈希存储，禁止明文

#### 3.1.3 Token机制
- 登录/注册成功后返回token
- Token有效期：7天
- 存储：sessions表（支持Gunicorn多worker共享）
- 传递方式：HTTP Header `X-Auth-Token: <token>` 或 Query参数 `?token=<token>`（用于静态文件访问）
- 登出后Token立即失效

#### 3.1.4 认证接口

| 接口 | 方法 | 权限 | 状态码 | 说明 |
|------|------|------|--------|------|
| `/api/auth/check` | POST | 公开 | 200/404 | 检查用户名是否存在（区分新用户/老用户） |
| `/api/auth/register` | POST | 公开 | 200/400 | 新用户注册，返回token |
| `/api/auth/login` | POST | 公开 | 200/401 | 登录，返回token；密码错误401 |
| `/api/auth/logout` | POST | 已登录 | 200 | 注销当前token |
| `/api/auth/me` | GET | 任意 | 200 | 获取当前用户信息，未登录user=null |

---

### 3.2 视频上传与处理

#### 3.2.1 上传规则
- 接口：`POST /api/upload`（**必须登录**，否则401且返回`need_login:true`）
- 支持格式：MP4/MOV/QT/M4V/3GP/AVI/MKV/WEBM
- 大小限制：最大600MB，时长最长30分钟
- 文件名安全处理：UUID重命名，避免路径穿越
- 参考视频：10分钟视频约3分钟出片

#### 3.2.2 任务处理流程
1. 上传完成 → 调用 `POST /api/process` 启动异步处理
2. 任务状态：`queued → processing → completed` 或 `failed`
3. 服务启动时自动重置所有`processing/queued`状态为`failed`（防止重启后进度条卡死）
4. 进度通过 SSE（`/api/task/<id>/events`）实时推送

#### 3.2.3 任务字段
- 必须包含：`upload_id`, `wechat_name`, `title`, `status`, `created_at`, `duration`, `output_files[]`, `is_owner`, `can_view`, `can_delete`
- `output_files[]` 每项包含：`filename`, `url`, `size`, `duration_s`
- 视频元数据（duration/size）在处理完成时持久化，禁止list接口同步调用ffprobe

#### 3.2.4 任务接口

| 接口 | 方法 | 权限 | 状态码 | 说明 |
|------|------|------|--------|------|
| `/api/upload` | POST | 登录 | 200/401/400 | 上传视频文件 |
| `/api/process` | POST | 登录（所有者） | 200/401/403/404 | 启动处理 |
| `/api/task/<id>/status` | GET | can_view | 200/403/404 | 查询任务状态 |
| `/api/task/<id>/events` | GET | can_view | 200(SSE) | SSE实时进度 |
| `/api/list` | GET | 任意 | 200 | 任务列表；管理员看全部，普通用户看公开+自己的 |
| `/api/task/<id>/delete` | POST | 所有者/管理员 | 200/403/404 | 软删除（普通用户）/硬删除（管理员） |
| `/api/task/<id>/restore` | POST | 所有者 | 200/403/404 | 恢复软删除的任务 |
| `/api/delete/<id>` | DELETE | 所有者/管理员 | 200/403/404 | 同delete，兼容旧客户端 |
| `/api/merge/<id>` | POST | 所有者 | 200/400/403/404 | 合并选中片段为集锦，输出merged_*.mp4 |

---

### 3.3 评论系统

#### 3.3.1 评论规则
- 发表评论必须登录（未登录401）
- 评分：1-5星
- 内容：最多500字，支持emoji表情
- 删除采用软删除（`is_deleted=1`），管理员可恢复

#### 3.3.2 评论接口

| 接口 | 方法 | 权限 | 状态码 | 说明 |
|------|------|------|--------|------|
| `/api/comments` | GET | 公开 | 200 | 评论列表（默认不包含已删除，`?include_deleted=true`管理员可看） |
| `/api/comments` | POST | 登录 | 200/401/400 | 发表评论 |
| `/api/comments/<id>` | DELETE | 管理员 | 200/403/404 | 软删除评论 |
| `/api/comments/<id>/restore` | POST | 管理员 | 200/403/404 | 恢复已删除评论 |

---

### 3.4 静态文件权限控制

#### 3.4.1 安全规则
- `/uploads/<filename>` 和 `/outputs/<upload_id>/<filename>` **必须做权限校验**，禁止直接裸访问
- 访问者必须满足以下任一：任务所有者、管理员、任务公开且未删除
- URL必须通过 `withAuthToken()` 函数追加 `?token=<token>` 才能正常加载
- 无权限访问返回403，文件不存在返回404

---

### 3.5 管理员功能

| 接口 | 方法 | 权限 | 状态码 | 说明 |
|------|------|------|--------|------|
| `/api/admin/users` | GET | 管理员 | 200/403 | 用户列表，含id/wechat_name/is_admin/created_at |
| `/api/admin/reset-password` | POST | 管理员 | 200/403/404 | 重置指定用户密码 |
| `/api/admin/cleanup` | POST | 管理员 | 200/403 | 清理过期/失败任务及文件 |

---

### 3.6 AI 趣味功能（2026-08-24新增）

基于豆包（火山方舟Ark）大模型，不引入新依赖（使用urllib.request直连），带本地fallback兜底。

#### 3.6.1 通用设计
- API Key通过环境变量 `ARK_API_KEY` / `ARK_ENDPOINT` 注入，**禁止硬编码**
- systemd EnvironmentFile：`/opt/badminton/env/ai.env`，权限640，属主badminton
- LLM调用超时：默认20秒，失败/超时自动使用本地fallback文案
- 结果带ttl内存缓存（鸡汤5分钟，起名1分钟），减少API消耗
- Fallback文案必须包含emoji

#### 3.6.2 AI接口

| 接口 | 方法 | 权限 | 缓存 | 说明 |
|------|------|------|------|------|
| `/api/ai/daily-quote` | GET | 公开 | 5分钟 | 每日鸡汤；支持`?name=xxx`返回个性化欢迎语 |
| `/api/ai/task-names` | POST | 公开 | 1分钟 | 给视频起名，返回3个名字chips；Body:`{user_name, date_hint, style}` |
| `/api/ai/comment` | POST | 公开 | 2分钟 | 生成评论文案（纯文本生成，不提交评论），Body:`{mood, rating, user_name}`，返回`{content, rating}` |
| `/api/ai/caption` | POST | 公开 | 5分钟 | 生成片段解说词（纯文本生成），Body:`{seg_idx, duration_s, score, total_segs, user_name}`，返回`{caption}` |

> 注：AI生成类接口均为公开（纯文本生成+fallback兜底，不消耗服务器资源），真正的"提交评论""上传视频"等写操作仍需登录。

---

### 3.7 其他接口

| 接口 | 方法 | 权限 | 说明 |
|------|------|------|------|
| `/health` | GET | 公开 | 健康检查，返回`{status:"ok"}` |
| `/config` | GET | 公开 | 前端配置（最大文件大小、支持格式等） |
| `/` | GET | 公开 | 主页SPA |
| `/guide` | GET | 公开 | 使用指南页 |
| `/api/estimate` | GET/POST | 公开 | 预估处理时长 |

---

## 4. UI/UX 规范

### 4.1 视觉设计
- 品牌色：紫色渐变主背景 `#5b4bd6 → #7a6cf4`
- 按钮主色：紫色渐变 `.btn-primary`；次要按钮：灰色 `.btn-secondary`
- 每日鸡汤：**白色胶囊**（rgba(255,255,255,0.95)背景 + 深紫色字#4a36b0 + 圆角999px + 阴影），必须带emoji
- 底部：显示slogan"主打快乐，顺带进步" + logo + ICP备案号

### 4.2 交互规范
- 所有危险操作/重要操作使用自定义 `showConfirm()`，**按钮顺序：取消在左，确定在右**
- 所有异步操作必须提供loading反馈（按钮置灰+文案"处理中…"）
- 登录/操作成功显示Toast反馈（带emoji，3秒自动消失）
- 未登录点击需要登录的功能，弹出登录Modal或Toast提示

### 4.3 移动端适配（≤480px断点）
- viewport meta必须包含 `viewport-fit=cover` 和 `user-scalable=no`
- 主断点 `@media (max-width:480px)` 覆盖：Header/card/upload/progress/result/output/history-filter/dy-comment/emoji/comment/modal/preview/confirm/toast/footer
- 小屏断点 `@media (max-width:360px)`：h1缩至19px、emoji改为5列
- AI评论按钮手机端2×2网格布局（flex:1 1 calc(50% - 4px)），标签独占一行
- 表格长文本字段省略显示+hover完整内容

### 4.4 文案本地化
- 禁止在UI上展示英文技术字段名（如直接显示`is_private`/`upload_id`）
- 使用本地化术语："往届名场面"（历史列表）、"球馆登记"（登录注册）、"主裁判吹哨开切"（开始处理）、"留言墙"（评论区）

---

## 5. 非功能需求

### 5.1 时区处理
- 所有时间戳存储为UTC ISO8601格式（带Z后缀）
- 前端渲染统一转换为 Asia/Shanghai（UTC+8）
- 后端DB写入和查询必须双重校验时区偏移

### 5.2 安全
- SQL注入：使用参数化查询（models.py已统一）
- XSS：用户名过滤 + Jinja2模板自动转义
- 路径穿越：上传文件名UUID重命名，send_from_directory限定目录
- API Key：环境变量注入，文件权限640，禁止提交到代码仓库
- 鉴权前置：`/api/upload`、`/api/process`等接口必须将登录检查置于逻辑最前端，未授权请求优先返回401

### 5.3 合规
- 页面底部必须展示 ICP 备案号 **陕ICP备2026022163号-1**
- 不收集手机号/身份证等敏感个人信息
- 视频文件仅限用户本人/管理员/公开可见三种访问级别

### 5.4 性能
- 禁止在`/api/list`批量接口中同步调用ffprobe
- SQLite启用WAL模式 + busy_timeout=10s + synchronous=NORMAL + foreign_keys=ON
- AI结果缓存，避免重复调用LLM
- Gunicorn多worker部署（systemd管理）

### 5.5 可靠性
- 服务启动时重置`processing/queued`任务为`failed`
- LLM调用失败自动fallback到本地文案池
- 部署脚本具备SSH超时重试机制

---

## 6. 测试覆盖矩阵

| 模块 | 单元测试 | API集成测试 | E2E浏览器测试 |
|------|---------|------------|--------------|
| 健康检查 | ✅ test_auth_unit | ✅ test_api_full (TC001) | ✅ |
| 认证(注册/登录/登出/me) | ✅ test_auth_unit (8个) | ✅ test_api_full (TC010-022) | ✅ |
| 用户名校验/XSS/密码强度 | ✅ test_auth_unit (4个) | ✅ test_api_full (TC012-017) | ✅ |
| Token失效/权限拦截 | ✅ test_auth_unit (3个) | ✅ test_api_full (TC030-035) | ✅ |
| 评论CRUD+软删除+恢复 | ✅ test_auth_unit (4个) | ✅ test_api_full (TC040-045) | ✅ |
| 任务列表+权限字段 | ✅ test_auth_unit (3个) | ✅ test_api_full (TC050-052) | ✅ |
| 时区转换 | ✅ test_timezone (10个) | - | - |
| 静态文件权限 | - | ✅ test_api_full (TC053-055) | ✅ |
| 管理员接口 | - | ✅ test_api_full (TC060-063) | ✅ |
| AI鸡汤/起名/评论/文案 | - | ✅ test_api_full (TC070-076) | ✅ |
| 合并导出 | - | ✅ test_api_full (TC033,无文件4xx) | - |
| 首页/ICP/viewport/AI DOM | - | ✅ test_api_full (TC003-005) | ✅ |
| config/guide/estimate | - | ✅ test_api_full (TC002,080,081) | - |
| 视频切片(CV算法) | - | - | ⚠️ test_tracknet（需模型权重） |
| PC端UI渲染 | - | - | ✅ Puppeteer |
| 移动端适配(≤480/≤360) | - | - | ✅ Puppeteer 390×844 |
| ICP备案合规 | - | ✅ test_api_full (TC003) | ✅ |

**测试统计**：
- 单元+API集成测试总计 **84个**（test_auth_unit 25 + test_timezone 10 + test_api_full 49），全部自动化通过
- E2E场景 **51个**（tests/test_e2e_scenarios.md），覆盖A-I共9组

---

## 7. 更新日志

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|---------|------|
| 2026-08-24 | v1.0 | 初版SPEC，覆盖认证/上传/评论/管理员/AI/移动端/安全/合规全部模块 | AI辅助生成 |

---

## 8. 后续迭代规范

每次功能迭代必须同步更新本文件：
1. **新增接口** → 更新第3节对应模块的接口表
2. **新增UI功能** → 更新第4节UI规范
3. **规则变更** → 更新对应模块规则描述
4. **新增测试** → 更新第6节测试覆盖矩阵
5. **版本发布** → 在第7节更新日志追加一行
