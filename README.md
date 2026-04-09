# 🎯 七鱼客服自动化监控系统

> 网易七鱼客服 API 自动化方案 | 排队监控 | 小时报自动推送 | 工单跟踪 | 飞书/企微推送

**搜索关键词：** 七鱼客服、网易七鱼、客服自动化、排队监控、小时报推送、工单系统、飞书机器人、企业微信机器人、Python 脚本、客服管理、运营工具、游戏运营、OpenClaw

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![GitHub Stars](https://img.shields.io/github/stars/rodrigoespinoza815-arch/qiyu-automation)](https://github.com/rodrigoespinoza815-arch/qiyu-automation/stargazers)

---

## 📋 目录

- [背景](#背景)
- [功能特性](#功能特性)
- [技术架构](#技术架构)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [效果对比](#效果对比)
- [实际案例](#实际案例)
- [技术支持](#技术支持)

---

## 📖 背景

本项目源于真实的游戏私域运营场景。在使用网易七鱼客服系统时，运营团队面临以下痛点：

- 😫 客服排队突然暴增，等发现时已经排了 50+ 人
- 📊 小时报要手动拉数据、做 Excel、发群
- 🎫 工单处理情况全靠人工统计
- 📉 月底算客服绩效，要熬几个通宵

**于是决定——全部自动化。**

---

## ✨ 功能特性

### 1️⃣ 实时排队监控
- 每 30 分钟自动检测排队人数
- 超过 20 人 → 飞书告警
- 超过 50 人 → @负责人

### 2️⃣ 小时报自动推送
- 10:00-19:00 每小时自动推送
- 实时数据：排队人数 / 在线客服 / 接入率 / 平均等待
- TOP5 客服工作量排名

### 3️⃣ 工单处理监控
- 待处理 / 已完结 / 超时工单统计
- 客服处理量排名
- 零处理量提醒

### 4️⃣ 效率分析
- 响应率 / 响应时间 / 满意度综合评分
- 低效客服自动识别
- 培训建议生成

---

## 🏗️ 技术架构

```
┌─────────────────┐
│   七鱼开放平台   │
│   (API 接口)    │
└────────┬────────
         │
         ▼
┌─────────────────┐
│  Python 脚本层   │
│ - minor_queue   │
│ - hourly_report │
│ - ticket_monitor│
└────────────────┘
         │
         ▼
┌─────────────────┐
│   推送渠道       │
│ - 飞书 Webhook  │
│ - 企微机器人    │
└─────────────────┘
```

### 技术栈
- **语言：** Python 3.8+
- **API：** 七鱼开放平台
- **推送：** 飞书 Webhook / 企业微信机器人
- **部署：** OpenClaw（AI 助手自动化框架）
- **定时任务：** Cron + OpenClaw Cron

---

## 🚀 快速开始

### 环境要求
- Python 3.8+
- 七鱼客服系统账号
- 飞书/企微 Webhook 地址

### 安装
```bash
git clone https://github.com/rodrigoespinoza815-arch/qiyu-automation.git
cd qiyu-automation
pip install requests
```

### 配置
1. 编辑 `qiyu_api.py`，填入七鱼 API 凭证：
```python
QIYU_APP_KEY = "your_app_key"
QIYU_APP_SECRET = "your_app_secret"
```

2. 编辑 `feishu_push.py`，填入飞书 Webhook：
```python
FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
```

### 运行
```bash
# 排队监控
python3 minor_queue_alert.py

# 小时报推送
python3 qiuqiu_minor_hourly.py

# 工单监控
python3 ticket_hourly_report.py
```

### 定时任务（Cron）
```bash
# 每 30 分钟检查排队
*/30 10-19 * * * cd /path/to/qiyu-automation && python3 minor_queue_alert.py

# 每小时推送小时报
3 10-19 * * * cd /path/to/qiyu-automation && python3 qiuqiu_minor_hourly.py
```

---

## 📊 效果对比

| 指标 | 自动化前 | 自动化后 | 提升 |
|------|----------|----------|------|
| 排队响应时间 | 15-30 分钟 | <5 分钟 | **300%** |
| 小时报制作时间 | 1 小时/天 | 0 | **∞** |
| 工单超时率 | 15% | 3% | **80%** |
| 客服绩效统计 | 3 天/月 | 实时 | **∞** |

**合计：每月节省约 80-100 小时人工 ≈ 2000-3000 元**

---

## 💡 实际案例

### 案例：未成年人客服组排队暴增

**时间：** 2026 年 4 月 8 日 19:00

**情况：**
- 排队人数从 19 人暴增至 42 人
- 在线客服从 1 人降至 0 人
- 平均等待时间高达 781 秒（~13 分钟）

**系统响应：**
1. 19:00 自动检测到异常，飞书告警已发送
2. 19:30 排队降至 12 人，系统自动恢复

**如果没有自动化：**
- 问题可能持续数小时才被发现
- 大量用户流失
- 客户投诉增加

---

## 🛠️ 目录结构

```
qiyu-automation/
├── minor_queue_alert.py      # 排队监控脚本
├── qiuqiu_minor_hourly.py    # 小时报推送脚本
├── ticket_hourly_report.py   # 工单监控脚本
├── qiyu_api.py               # 七鱼 API 封装
├── feishu_push.py            # 飞书推送封装
├── hourly_push_log.py        # 推送日志记录
├── cleanup_locks.py          # 锁文件清理
├── index.html                # 项目落地页
├── README.md                 # 项目说明
└── .github/
    └── FUNDING.yml           # 赞助支持
```

---

## 💰 商业支持

如果您需要：
- ✅ 完整系统部署
- ✅ 七鱼 API 配置
- ✅ 飞书/企微推送配置
- ✅ 30 天技术支持
- ✅ 1 次免费定制

**专业版：¥19.9/套（含完整部署+技术支持）**

支付宝扫码付款，备注"七鱼自动化"：
- 联系：`oscartsui`
- 24 小时内交付

---

## 📝 许可证

MIT License

---

## 🙏 感谢

- 网易七鱼开放平台
- OpenClaw 自动化框架
- 飞书/企业微信开发者平台

---

**⭐ 如果这个项目对你有帮助，请给个 Star！**

**🐛 如有问题，欢迎提 Issue！**