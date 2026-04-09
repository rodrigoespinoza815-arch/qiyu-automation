#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
未成年人客服组排队警告推送
- 每半小时执行一次（10:00-19:00）
- 检查七鱼排队情况
- 排队 > 20 人 → 飞书告警
- 排队 > 50 人 → 飞书@负责人
"""

import sys
sys.path.insert(0, '/Users/oscar/.openclaw/workspace')

from qiyu_api import get_realtime_overview
from feishu_push import send_text_to_group, send_alert_to_group
from datetime import datetime

# ============ 配置 ============
MINOR_GROUP_ID = 484896336  # 未成年人客服组 ID
FEISHU_GROUP = '球球&太空未成年反馈群'

# ============ 告警阈值 ============
WARNING_THRESHOLD = 20    # 警告阈值
CRITICAL_THRESHOLD = 50   # 紧急阈值

# ============ 重试 + 去重 ============
ALERT_RETRY = 3           # 飞书发送失败重试次数
ALERT_RETRY_DELAY = 30    # 重试间隔（秒）
ALERT_DEDUP_SECONDS = 300 # 同级别告警去重窗口（5分钟）
ALERT_STATE_FILE = '/Users/oscar/.openclaw/workspace/.learnings/alert_state.json'

# ============ 持续高位告警 ============
SUSTAINED_THRESHOLD = 3   # 连续 N 次超阈值触发升级告警

import json
import os

def load_alert_state():
    """加载上次告警状态"""
    if not os.path.exists(ALERT_STATE_FILE):
        return {}
    try:
        with open(ALERT_STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def should_send_alert(alert_level):
    """检查是否应该发送告警（去重）"""
    state = load_alert_state()
    last_time = state.get(alert_level, 0)
    import time
    now = time.time()
    # 防御：如果时间戳在未来（损坏），自动清除
    if last_time > now + 60:
        print(f"   ⚠️  告警状态文件时间戳异常（{last_time} > {now}），自动清除")
        state.pop(alert_level, None)
        os.makedirs(os.path.dirname(ALERT_STATE_FILE), exist_ok=True)
        with open(ALERT_STATE_FILE, 'w') as f:
            json.dump(state, f)
        return True
    if now - last_time < ALERT_DEDUP_SECONDS:
        return False
    return True

def save_alert_state(alert_level):
    """保存告警时间戳"""
    import time
    state = load_alert_state()
    state[alert_level] = time.time()
    os.makedirs(os.path.dirname(ALERT_STATE_FILE), exist_ok=True)
    with open(ALERT_STATE_FILE, 'w') as f:
        json.dump(state, f)

def track_sustained_alert(queue_count, threshold):
    """
    跟踪持续高位排队次数。
    返回当前连续超过阈值的次数。
    """
    state = load_alert_state()
    now_key = 'sustained_over_' + str(threshold)
    import time
    now = time.time()
    last_check = state.get('last_check_time', 0)
    
    # 30 分钟 cron 间隔，如果超过 40 分钟没检查，重置计数
    if now - last_check > 2400:
        state[now_key] = 0
    
    if queue_count > threshold:
        state[now_key] = state.get(now_key, 0) + 1
    else:
        state[now_key] = 0
    
    state['last_check_time'] = now
    os.makedirs(os.path.dirname(ALERT_STATE_FILE), exist_ok=True)
    with open(ALERT_STATE_FILE, 'w') as f:
        json.dump(state, f)
    
    return state.get(now_key, 0)

def send_with_retry(group_name, text, max_retries=ALERT_RETRY):
    """带重试的飞书消息发送"""
    from feishu_push import send_text_to_group
    for attempt in range(1, max_retries + 1):
        result = send_text_to_group(group_name, text)
        if result.get('success'):
            return result
        error = result.get('error', '')
        # 限频时等待重试
        if 'frequency limited' in error.lower() and attempt < max_retries:
            print(f"   ⚠️  飞书限频，等待 {ALERT_RETRY_DELAY}s 后重试 ({attempt}/{max_retries})...")
            import time
            time.sleep(ALERT_RETRY_DELAY)
        else:
            return result
    return {'success': False, 'error': f'重试 {max_retries} 次后仍失败'}

def send_queue_alert(queue_count, online_count, wait_time=0, is_critical=False):
    """发送排队告警到飞书"""
    
    if is_critical:
        # 紧急告警
        text = (f'🚨 紧急告警：排队人数过多！\n'
                f'当前排队：{queue_count} 人\n'
                f'在线客服：{online_count} 人\n'
                f'平均排队：{wait_time // 1000} 秒\n'
                f'请立即安排更多客服上线！')
    else:
        # 普通告警
        text = (f'⚠️ 排队警告提醒\n'
                f'当前排队：{queue_count} 人\n'
                f'在线客服：{online_count} 人\n'
                f'平均排队：{wait_time // 1000} 秒\n'
                f'请客服组注意及时接入！')
    
    result = send_text_to_group(
        group_name=FEISHU_GROUP,
        text=text
    )
    
    return result

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始检查未成年人组排队状态...")
    
    # 获取实时数据
    result = get_realtime_overview(to_group=[MINOR_GROUP_ID])
    
    if not result.get('success'):
        print(f"❌ 获取数据失败：{result.get('error', '未知错误')}")
        return
    
    data = result.get('data', {})
    
    # 提取关键指标
    queue_count = data.get('queueCount', 0)
    online_count = data.get('kefuCount', 0)
    wait_time = data.get('averageWaitingTime', 0)  # 毫秒
    session_count = data.get('sessionCount', 0)
    
    print(f"📊 当前排队：{queue_count} 人 | 在线客服：{online_count} 人 | 平均等待：{wait_time // 1000} 秒")
    
    # 跟踪持续高位次数
    sustained_count = track_sustained_alert(queue_count, WARNING_THRESHOLD)
    
    # 判断告警级别
    if queue_count > CRITICAL_THRESHOLD:
        print(f"🚨 紧急告警：排队 {queue_count} 人 > {CRITICAL_THRESHOLD} 人")
        # 去重检查
        if not should_send_alert('critical'):
            print(f"⏭️  5分钟内已发送过紧急告警，跳过")
            return
        alert_result = send_with_retry(FEISHU_GROUP, 
            f'🚨 紧急告警：排队人数过多！\n'
            f'当前排队：{queue_count} 人\n'
            f'在线客服：{online_count} 人\n'
            f'平均排队：{wait_time // 1000} 秒\n'
            f'请立即安排更多客服上线！')
        if alert_result.get('success'):
            save_alert_state('critical')
    elif queue_count > WARNING_THRESHOLD:
        print(f"⚠️ 警告：排队 {queue_count} 人 > {WARNING_THRESHOLD} 人")
        alert_result = {'success': True, 'message': '5分钟内已发送过，跳过'}
        # 去重检查
        if not should_send_alert('warning'):
            print(f"⏭️  5分钟内已发送过警告，跳过")
        else:
            alert_result = send_with_retry(FEISHU_GROUP,
                f'⚠️ 排队警告提醒\n'
                f'当前排队：{queue_count} 人\n'
                f'在线客服：{online_count} 人\n'
                f'平均排队：{wait_time // 1000} 秒\n'
                f'请客服组注意及时接入！')
            if alert_result.get('success'):
                save_alert_state('warning')
        
        # 持续高位升级告警
        if sustained_count >= SUSTAINED_THRESHOLD:
            sustained_text = (
                f'🔴 持续高位告警：排队已持续 {sustained_count} 次超过 {WARNING_THRESHOLD} 人\n'
                f'当前排队：{queue_count} 人\n'
                f'平均排队：{wait_time // 1000} 秒\n'
                f'请主管关注排班和人员调配！'
            )
            # 持续告警用不同的 key 去重
            if should_send_alert('sustained_warning'):
                send_with_retry(FEISHU_GROUP, sustained_text)
                save_alert_state('sustained_warning')
    else:
        print(f"✅ 正常：排队 {queue_count} 人 ≤ {WARNING_THRESHOLD} 人")
        # 排队恢复正常，清除持续计数
        track_sustained_alert(queue_count, WARNING_THRESHOLD)
        alert_result = {'success': True, 'message': '无需告警'}
    
    if alert_result.get('success'):
        print(f"✅ 告警处理完成：{alert_result.get('message', '已发送')}")
    else:
        print(f"❌ 发送告警失败：{alert_result.get('error', '未知错误')}")
        # 推送失败 → 告警群通知
        send_alert_to_group(f'❌ 未成年人组排队告警推送失败：{alert_result.get("error", "未知错误")}')

if __name__ == "__main__":
    main()
