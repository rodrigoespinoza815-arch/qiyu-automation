#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书 Webhook 推送工具
支持发送富文本、文本、卡片消息到飞书群
"""

import json
import time
import hmac
import hashlib
import base64
import requests
from datetime import datetime

# ==================== 配置 ====================
FEISHU_WEBHOOKS = {
    '球球&太空未成年反馈群': 'https://open.feishu.cn/open-apis/bot/v2/hook/e0fdbded-de53-4009-9777-f472d86599bb',
    '征途赛道客服组': 'https://open.feishu.cn/open-apis/bot/v2/hook/0d11e48f-5fad-4e17-8e62-174897d4b26f',
}

# ⚠️⚠️⚠️ 所有自检异常/推送失败告警统一推送到这个群（鼎爷指定）
ALERT_GROUP_NAME = '告警通知群'
ALERT_GROUP_CHAT_ID = 'oc_7a8097ba8b6b79104ee85b6da7c4b62a'
ALERT_GROUP_WEBHOOK = 'https://open.feishu.cn/open-apis/bot/v2/hook/ba08f7b5-dcc5-421d-a576-9306b9cdf783'

def send_alert_to_group(alert_text):
    """
    发送自检异常告警到告警群（鼎爷指定）
    通过 webhook 发送到 oc_7a8097ba8b6b79104ee85b6da7c4b62a
    """
    return send_feishu_webhook(ALERT_GROUP_WEBHOOK, alert_text, msg_type='text')

# ==================== 核心发送函数 ====================
def send_feishu_webhook(webhook_url, content, msg_type='text', secret=None):
    """
    通过 Webhook 发送消息到飞书群
    
    Args:
        webhook_url: 飞书 Webhook URL
        content: 消息内容（dict）
        msg_type: 消息类型（text/post/card）
        secret: Webhook 签名密钥（可选）
    
    Returns:
        dict: 发送结果
    """
    headers = {'Content-Type': 'application/json; charset=utf-8'}
    
    payload = {'msg_type': msg_type}
    
    if msg_type == 'text':
        payload['content'] = {'text': content} if isinstance(content, str) else content
    else:
        # post / card 消息需要嵌套在 content 字段下
        payload['content'] = content
    
    # 签名
    if secret:
        timestamp = str(int(time.time()))
        string_to_sign = '{}\n{}'.format(timestamp, secret)
        hmac_code = hmac.new(
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        sign = base64.b64encode(hmac_code).decode('utf-8')
        payload['timestamp'] = timestamp
        payload['sign'] = sign
    
    try:
        response = requests.post(webhook_url, headers=headers, json=payload, timeout=10)
        result = response.json()
        
        if result.get('code') == 0:
            return {'success': True, 'message_id': result.get('data', {}).get('message_id', '')}
        else:
            return {
                'success': False,
                'code': result.get('code'),
                'error': result.get('msg', 'Unknown error')
            }
    except requests.exceptions.Timeout:
        return {'success': False, 'error': '请求超时', 'code': -1}
    except requests.exceptions.ConnectionError:
        return {'success': False, 'error': '连接失败', 'code': -2}
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f'请求异常: {str(e)}', 'code': -3}
    except Exception as e:
        return {'success': False, 'error': str(e), 'code': -99}

# ==================== 富文本消息 ====================
def send_post_to_group(group_name, title, content_items):
    """
    发送富文本消息到飞书群
    
    Args:
        group_name: 群名称
        title: 消息标题
        content_items: 内容列表 [[{'tag': 'text', 'text': 'xxx'}], ...]
    
    Returns:
        dict: 发送结果
    """
    webhook = FEISHU_WEBHOOKS.get(group_name)
    if not webhook:
        return {'success': False, 'error': f'未找到群：{group_name}'}
    
    content = {
        'post': {
            'zh_cn': {
                'title': title,
                'content': content_items
            }
        }
    }
    
    return send_feishu_webhook(webhook, content, msg_type='post')

# ==================== 文本消息 ====================
def send_text_to_group(group_name, text, at_users=None):
    """
    发送纯文本消息到飞书群
    
    Args:
        group_name: 群名称
        text: 消息文本
        at_users: 要@的用户 open_id 列表
    
    Returns:
        dict: 发送结果
    """
    webhook = FEISHU_WEBHOOKS.get(group_name)
    if not webhook:
        return {'success': False, 'error': f'未找到群：{group_name}'}
    
    # 飞书 Webhook 文本消息长度限制：4096 字符
    if len(text) > 4000:
        text = text[:3990] + '...（内容过长已截断）'
    
    if at_users:
        for user_id in at_users:
            text += f' <at user_id="{user_id}">'
    
    return send_feishu_webhook(webhook, text, msg_type='text')

# ==================== 卡片消息 ====================
def send_card_to_group(group_name, card_config):
    """
    发送卡片消息到飞书群
    
    Args:
        group_name: 群名称
        card_config: 卡片配置（参考飞书卡片设计器）
    
    Returns:
        dict: 发送结果
    """
    webhook = FEISHU_WEBHOOKS.get(group_name)
    if not webhook:
        return {'success': False, 'error': f'未找到群：{group_name}'}
    
    return send_feishu_webhook(webhook, card_config, msg_type='card')

# ==================== 模板消息 ====================
def send_queue_alert(group_name, queue_data):
    """
    发送排队告警消息
    
    Args:
        group_name: 群名称
        queue_data: 排队数据 dict
    
    Returns:
        dict: 发送结果
    """
    title = '⚠️ 排队告警'
    queue_count = queue_data.get('queue_count', 0)
    
    content = [
        [{'tag': 'text', 'text': f'🔴 排队告警'}],
        [{'tag': 'text', 'text': f'当前排队：{queue_count} 人'}],
    ]
    
    if queue_count > 50:
        content.append([{'tag': 'text', 'text': '请立即处理！'}])
    
    return send_post_to_group(group_name, title, content)

def send_refund_report(group_name, refund_data):
    """
    发送退款报告
    
    Args:
        group_name: 群名称
        refund_data: 退款数据
    
    Returns:
        dict: 发送结果
    """
    title = '📊 退款报告'
    content = [
        [{'tag': 'text', 'text': f'📊 退款报告'}],
        [{'tag': 'text', 'text': f'总退款数：{refund_data.get("total", 0)}'}],
        [{'tag': 'text', 'text': f'退款金额：{refund_data.get("amount", 0)}'}],
    ]
    
    return send_post_to_group(group_name, title, content)

def send_daily_report(group_name, report_data):
    """
    发送日报
    
    Args:
        group_name: 群名称
        report_data: 日报数据
    
    Returns:
        dict: 发送结果
    """
    title = f'📊 日报 - {datetime.now().strftime("%Y-%m-%d")}'
    content = [
        [{'tag': 'text', 'text': title}],
        [{'tag': 'text', 'text': f'总会话数：{report_data.get("total_sessions", 0)}'}],
        [{'tag': 'text', 'text': f'有效会话：{report_data.get("valid_sessions", 0)}'}],
        [{'tag': 'text', 'text': f'满意度：{report_data.get("satisfaction", "N/A")}'}],
    ]
    
    return send_post_to_group(group_name, title, content)


if __name__ == '__main__':
    # 测试发送
    from feishu_push import send_post_to_group
    result = send_post_to_group('运营通知群', '标题', [
        [{'tag': 'text', 'text': '这是一条测试消息'}]
    ])
    print(json.dumps(result, ensure_ascii=False, indent=2))
