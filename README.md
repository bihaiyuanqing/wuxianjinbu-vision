# 🏸 无限进步 - 羽毛球视频智能剪辑服务

个人非经营性羽毛球视频记录与智能分段剪辑平台，基于计算机视觉技术自动识别并提取羽毛球比赛中的精彩回合。

## ✨ 功能特性

- 🎯 **智能分段**：自动识别羽毛球比赛中的击球回合，剔除无效片段
- 🚀 **异步处理**：基于线程池的异步任务队列 + SSE 实时进度推送
- 📱 **响应式 UI**：移动端友好的 Web 界面
- 💬 **留言墙**：用户反馈收集功能
- 🗑️ **软删除**：任务历史管理，支持管理员恢复
- ⏰ **自动清理**：每日 03:00 自动清理 7 天前的历史数据
- 🔒 **HTTPS**：自动 SSL 证书，强制 HTTPS 跳转

## 🛠️ 技术栈

| 层级 | 技术选型 |
|------|----------|
| 后端 | Python 3 / Flask / Gunicorn |
| 数据库 | SQLite |
| CV 算法 | OpenCV / MediaPipe / PyTorch / TrackNetV3 |
| 视频处理 | FFmpeg |
| 前端 | 原生 HTML/CSS/JavaScript |
| 部署 | Nginx / systemd / Certbot |

## 📋 视频限制

- **文件大小**：最大 600MB
- **视频时长**：上限 30 分钟（建议 10 分钟以内）
- **支持格式**：mp4, mov, qt, m4v, 3gp, avi, mkv, flv, wmv, webm, mts, m2ts

## 🚀 快速开始

### 环境要求

- Python 3.8+
- FFmpeg
- （可选）CUDA 支持的 GPU（用于 TrackNetV3 加速）

### 本地开发

```bash
# 1. 克隆项目
git clone <repository-url>
cd wuxianjinbu-vision

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动 Web 服务
cd web
python app.py
```

服务默认在 `http://localhost:5000` 启动。

### 命令行使用

项目也提供命令行工具进行视频分析和剪辑：

```bash
# 查看视频信息
python main.py info -i /path/to/video.mp4

# 分析视频并生成分段 JSON
python main.py analyze -i /path/to/video.mp4 -o ./output --tracknet

# 根据分段 JSON 剪辑视频
python main.py cut -i /path/to/video.mp4 -s segments.json -o ./output

# 一键自动处理（分析+剪辑）
python main.py auto -i /path/to/video.mp4 -o ./output --tracknet
```

## 🚢 部署

### 三级发布流程

```
本地开发验证 → 测试环境 (101.126.10.54) → 线上环境 (wuxianjinbu.fun)
```

### 部署脚本

使用 [deploy.sh](file:///Users/xuedongfeng/Downloads/ProjectsTrea/record_flow/deploy/deploy.sh) 进行自动化部署：

```bash
# 部署到测试环境
./deploy/deploy.sh test

# 部署到线上环境
./deploy/deploy.sh prod
```

部署脚本会自动完成：
- 代码打包与上传
- 清理缓存文件
- 重启服务
- 健康检查
- 外部可访问性验证

### 环境信息

| 环境 | 地址 | 备注 |
|------|------|------|
| 线上 | https://wuxianjinbu.fun | 公网访问，HTTPS |
| 测试 | http://101.126.10.54 | 内网访问 |

## 📁 项目结构

```
wuxianjinbu-vision/
├── src/                     # 核心算法模块
│   ├── segmenter.py         # 视频分段主逻辑
│   ├── video_cutter.py      # FFmpeg 视频剪辑
│   ├── court_detector.py    # 球场检测
│   ├── player_pose.py       # 球员姿态估计
│   ├── shuttlecock_tracker.py # 羽毛球追踪
│   └── tracknetv3_integrator.py # TrackNetV3 集成
├── web/                     # Web 服务
│   ├── app.py               # Flask 应用入口
│   ├── models.py            # 数据库模型
│   ├── templates/           # HTML 模板
│   ├── uploads/             # 上传文件目录
│   └── outputs/             # 处理结果目录
├── models/                  # ML 模型权重（TrackNetV3）
├── deploy/                  # 部署配置与脚本
│   ├── deploy.sh            # 主部署脚本
│   ├── gunicorn.conf.py     # Gunicorn 配置
│   ├── nginx.conf.template  # Nginx 配置模板
│   └── cleanup_old_videos.py # 自动清理脚本
├── config.yaml              # 算法参数配置
├── main.py                  # CLI 命令行入口
└── requirements.txt         # Python 依赖
```

## ⚙️ 配置说明

主要配置在 [config.yaml](file:///Users/xuedongfeng/Downloads/ProjectsTrea/record_flow/config.yaml) 中：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| video.min_segment_duration | 3.0s | 最小分段时长 |
| video.max_segment_duration | 60.0s | 最大分段时长 |
| video.padding_before | 0.5s | 分段前向补长 |
| video.padding_after | 0.5s | 分段后向补长 |
| shuttlecock.confidence_threshold | 0.5 | 羽毛球检测置信度阈值 |

## 🔧 管理员功能

系统管理员通过微信号「行遇书」识别，拥有以下权限：
- 查看所有用户的任务（含已删除）
- 恢复已软删除的任务

## 🧹 数据清理

系统每日 03:00 自动执行清理任务，删除 7 天前的上传视频和处理结果，以节省服务器存储空间。

## 📝 分支管理

- `master`：维护最新的发布版本（生产环境）
- `xuedongfeng_YYYYMMDD`：日常开发分支，合并到 master 后发布

## 📄 备案说明

本网站为个人非经营性视频记录网站，ICP 备案号：待更新。

## 📞 反馈

欢迎通过网站内的留言墙提出建议和反馈！🏸
