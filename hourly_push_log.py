#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小时报推送日志记录和自检模块

功能：
1. 记录每次推送的详细信息（时间、群、状态、消息 ID）
2. 推送后自检（检查是否真的发送成功）
3. 连续失败告警
4. 每日推送报告
"""

import os
import json
from datetime import datetime, timedelta

# ==================== 配置 ====================
WORKSPACE = "/Users/oscar/.openclaw/workspace"
PUSH_LOG_FILE = os.path.join(WORKSPACE, ".learnings/hourly_push_log.json")
MAX_LOG_ENTRIES = 500  # 最多保留 500 条记录

# ==================== 日志记录 ====================
def log_push(task_name, group_name, success, message_id=None, error=None, metadata=None):
    """
    记录推送日志
    
    Args:
        task_name: 任务名称（如 "未成年人组小时报"）
        group_name: 推送群名称
        success: 是否成功
        message_id: 飞书消息 ID（成功时有值）
        error: 错误信息（失败时有值）
        metadata: 其他元数据（排队人数、客服数等）
    """
    # 加载现有日志
    logs = load_logs()
    
    # 创建新记录
    entry = {
        'timestamp': datetime.now().isoformat(),
        'task': task_name,
        'group': group_name,
        'success': success,
        'message_id': message_id,
        'error': error,
        'metadata': metadata or {}
    }
    
    # 添加到日志
    logs.append(entry)
    
    # 限制日志大小
    if len(logs) > MAX_LOG_ENTRIES:
        logs = logs[-MAX_LOG_ENTRIES:]
    
    # 保存
    save_logs(logs)
    
    # 打印日志
    status = "✅" if success else "❌"
    print(f"[{entry['timestamp']}] {status} {task_name} → {group_name}")
    if not success:
        print(f"   错误：{error}")
    
    return entry

def load_logs():
    """加载推送日志"""
    if not os.path.exists(PUSH_LOG_FILE):
        return []
    try:
        with open(PUSH_LOG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_logs(logs):
    """保存推送日志"""
    # 确保目录存在
    os.makedirs(os.path.dirname(PUSH_LOG_FILE), exist_ok=True)
    with open(PUSH_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

# ==================== 自检功能 ====================
def check_recent_pushes(hours=2):
    """
    检查最近 N 小时的推送情况
    
    Returns:
        dict: 检查结果
    """
    logs = load_logs()
    now = datetime.now()
    cutoff = now - timedelta(hours=hours)
    
    # 筛选最近的日志
    recent = [
        entry for entry in logs
        if datetime.fromisoformat(entry['timestamp']) > cutoff
    ]
    
    # 按任务分组
    tasks = {}
    for entry in recent:
        task_key = f"{entry['task']}:{entry['group']}"
        if task_key not in tasks:
            tasks[task_key] = {'total': 0, 'success': 0, 'failures': []}
        tasks[task_key]['total'] += 1
        if entry['success']:
            tasks[task_key]['success'] += 1
        else:
            tasks[task_key]['failures'].append(entry)
    
    # 分析问题
    issues = []
    for task_key, stats in tasks.items():
        success_rate = stats['success'] / stats['total'] if stats['total'] > 0 else 0
        if success_rate < 0.8:  # 成功率低于 80%
            issues.append({
                'task': task_key,
                'total': stats['total'],
                'success': stats['success'],
                'rate': success_rate,
                'failures': stats['failures']
            })
    
    return {
        'period_hours': hours,
        'total_pushes': len(recent),
        'tasks': tasks,
        'issues': issues
    }

def get_daily_report(date=None):
    """
    获取指定日期的推送报告
    
    Args:
        date: 日期（datetime 对象，默认为今天）
    
    Returns:
        dict: 推送报告
    """
    if date is None:
        date = datetime.now()
    
    logs = load_logs()
    date_str = date.strftime('%Y-%m-%d')
    
    # 筛选当天的日志
    daily = [
        entry for entry in logs
        if entry['timestamp'].startswith(date_str)
    ]
    
    # 按任务分组统计
    tasks = {}
    for entry in daily:
        task_key = f"{entry['task']}:{entry['group']}"
        if task_key not in tasks:
            tasks[task_key] = {'total': 0, 'success': 0, 'first_push': None, 'last_push': None}
        tasks[task_key]['total'] += 1
        if entry['success']:
            tasks[task_key]['success'] += 1
        ts = entry['timestamp']
        if tasks[task_key]['first_push'] is None or ts < tasks[task_key]['first_push']:
            tasks[task_key]['first_push'] = ts
        if tasks[task_key]['last_push'] is None or ts > tasks[task_key]['last_push']:
            tasks[task_key]['last_push'] = ts
    
    # 计算总体统计
    total_pushes = len(daily)
    total_success = sum(1 for e in daily if e['success'])
    success_rate = total_success / total_pushes if total_pushes > 0 else 0
    
    return {
        'date': date_str,
        'total_pushes': total_pushes,
        'total_success': total_success,
        'total_failures': total_pushes - total_success,
        'success_rate': success_rate,
        'tasks': tasks
    }

def format_daily_report(report):
    """格式化每日报告为可读文本"""
    lines = [
        f"📊 小时报推送日报 ({report['date']})",
        "=" * 50,
        f"总推送次数：{report['total_pushes']}",
        f"成功：{report['total_success']} | 失败：{report['total_failures']}",
        f"成功率：{report['success_rate']*100:.1f}%",
        "",
        "📋 各任务详情:"
    ]
    
    for task_key, stats in report['tasks'].items():
        task_name, group_name = task_key.split(':', 1)
        rate = stats['success'] / stats['total'] * 100 if stats['total'] > 0 else 0
        status = "✅" if rate >= 99 else "⚠️" if rate >= 80 else "❌"
        lines.append(f"  {status} {task_name} → {group_name}")
        lines.append(f"     推送{stats['total']}次 | 成功{stats['success']} | 成功率{rate:.0f}%")
    
    return "\n".join(lines)

# ==================== 测试 ====================
if __name__ == '__main__':
    # 测试日志记录
    print("测试推送日志记录...")
    log_push("测试任务", "测试群", True, message_id="test123", metadata={'queue': 5})
    log_push("测试任务", "测试群", False, error="测试错误", metadata={'queue': 10})
    
    # 测试自检
    print("\n检查最近 2 小时推送...")
    result = check_recent_pushes(2)
    print(f"总推送：{result['total_pushes']}")
    if result['issues']:
        print(f"发现问题：{len(result['issues'])} 个")
        for issue in result['issues']:
            print(f"  - {issue['task']}: 成功率{issue['rate']*100:.0f}%")
    else:
        print("✅ 无异常")
    
    # 测试日报
    print("\n今日推送报告:")
    report = get_daily_report()
    print(format_daily_report(report))
