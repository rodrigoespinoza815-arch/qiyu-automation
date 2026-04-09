#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易七鱼开放平台 API 调用脚本
获取客服数据报表

文档：https://qiyukf.com/openapi
"""

import hashlib
import hmac
import time
import requests
import json
from datetime import datetime, timedelta

# ==================== 配置区 ====================
# ⚠️ 填入你的七鱼 API 凭证（七鱼后台 → 系统 → 扩展与集成）
QIYU_APP_KEY = "3b9d81fd743a018bb30158d99043adc5"
QIYU_APP_SECRET = "3E27394508A14673894EAB5636D22BFF"

# API 基础 URL
BASE_URL = "https://qiyukf.com/openapi"

# ==================== 鉴权模块 ====================
def md5_hex(text):
    """计算 MD5（32 位，小写）"""
    return hashlib.md5(text.encode('utf-8')).hexdigest().lower()

def sha1_hex(text):
    """计算 SHA1（小写）"""
    return hashlib.sha1(text.encode('utf-8')).hexdigest().lower()

def generate_checksum(app_secret, content_md5, timestamp):
    """
    生成 checksum
    公式：SHA1(appSecret + md5 + time)
    time 是秒级时间戳
    """
    content = f"{app_secret}{content_md5}{timestamp}"
    return sha1_hex(content)

def build_signed_url(endpoint, content=''):
    """
    构建带签名的完整 URL
    
    Args:
        endpoint: API 端点路径（如 /data/overview/session）
        content: POST 请求体（JSON 字符串）
    """
    timestamp = str(int(time.time()))  # 秒级时间戳
    # 空 dict 也要序列化成 '{}' 来计算 MD5
    if not content:
        content = '{}'
    content_md5 = md5_hex(content)
    checksum = generate_checksum(QIYU_APP_SECRET, content_md5, timestamp)
    
    url = f"{BASE_URL}{endpoint}"
    url += f"?appKey={QIYU_APP_KEY}"
    url += f"&time={timestamp}"
    url += f"&checksum={checksum}"
    
    return url

# ==================== API 调用封装 ====================
def _fix_malformed_json(text):
    """
    修复七鱼返回的畸形 JSON
    七鱼的 follower 字段会返回 {123456:"name", ...} 这种 key 不带引号的非法 JSON
    """
    import re
    # 修复 { 数字:  模式 -> { "数字": 
    text = re.sub(r'\{(\d+):', r'{"\1":', text)
    text = re.sub(r',(\d+):', r',"\1":', text)
    return text

def api_request(endpoint, data=None):
    """
    通用 API 调用方法
    
    Args:
        endpoint: API 端点路径
        data: POST 数据（dict）
    
    Returns:
        dict: 解析后的响应，包含 code 和 message/data
    """
    # 空 dict 也要序列化成 '{}'
    content = json.dumps(data if data else {}, ensure_ascii=False)
    url = build_signed_url(endpoint, content)
    
    headers = {
        'Content-Type': 'application/json;charset=utf-8'
    }
    
    response = requests.post(url, data=content, headers=headers, timeout=10)
    try:
        result = response.json()
    except json.JSONDecodeError:
        # 尝试修复畸形 JSON 后重新解析
        fixed = _fix_malformed_json(response.text)
        result = json.loads(fixed)
    return result

def parse_result(result):
    """
    解析返回结果
    七鱼返回格式：{"code": 200, "message": "{...}"} 或 {"code": 200, "data": {...}}
    """
    if result.get('code') != 200:
        return {'success': False, 'error': result.get('message', 'Unknown error')}
    
    # message 字段可能是字符串化的 JSON，需要二次解析
    message = result.get('message')
    if message and isinstance(message, str):
        try:
            data = json.loads(message)
            return {'success': True, 'data': data}
        except:
            return {'success': True, 'data': message}
    elif result.get('data'):
        return {'success': True, 'data': result['data']}
    else:
        return {'success': True, 'data': {}}

# ==================== 实时数据报表 ====================
def get_realtime_overview(to_group=None, to_staff=None, assign_staff=None, staff_group=None):
    """
    实时数据报表 - 获取当前客服数据概览
    
    Args:
        to_group: 分流客服组 ID 列表
        to_staff: 分流客服 ID 列表
        assign_staff: 客服 ID 列表
        staff_group: 客服组 ID 列表
    
    返回字段：
    - kefuCount: 当前在线客服人数
    - sessionCount: 当前咨询人数
    - queueCount: 当前排队人数
    - sessionInCount: 已接入会话量
    - leaveSessionCount: 未接入会话量
    - averageServiceTime: 平均会话时长（毫秒）
    - averageWaitingTime: 平均排队时长（毫秒）
    - satisfaction: 相对满意度
    - 等等...
    """
    data = {}
    if to_group: data['toGroup'] = to_group
    if to_staff: data['toStaff'] = to_staff
    if assign_staff: data['assignStaff'] = assign_staff
    if staff_group: data['staffGroup'] = staff_group
    
    result = api_request('/data/overview/session', data)
    return parse_result(result)

# ==================== 客服质量报表 ====================
def get_staff_quality(start_time=None, end_time=None, model=1, staff_group_list=None, staff_id_list=None, page=1, page_size=100):
    """
    客服质量报表 - 客服工作质量数据
    
    Args:
        start_time: 开始时间（毫秒时间戳），不传默认近一个月
        end_time: 结束时间（毫秒时间戳）
        model: 查询模式 1=全部 2=客服组 3=客服
        staff_group_list: 客服组 ID 列表
        staff_id_list: 客服 ID 列表
        page: 页码
        page_size: 每页数量（1-1000）
    
    返回字段：
    - avgFirstRespTime: 平均首响
    - avgRespTime: 平均响应时长
    - avgRgTime: 平均人工接待时长
    - satisfactionRatio: 满意度
    - replyRatio: 应答率
    - oneOffRatio: 一次性解决率
    - 等等...
    """
    data = {
        'page': page,
        'pageSize': min(page_size, 1000)
    }
    if start_time: data['startTime'] = start_time
    if end_time: data['endTime'] = end_time
    if model: data['model'] = model
    if staff_group_list: data['staffGroupList'] = staff_group_list
    if staff_id_list: data['staffIdList'] = staff_id_list
    
    result = api_request('/statistic/staffquality', data)
    return parse_result(result)

# ==================== 客服考勤报表 ====================
def get_staff_attendance(start_time=None, end_time=None, model=1, staff_group_list=None, staff_id_list=None, page=1, page_size=100):
    """
    客服考勤报表 - 客服上下线考勤数据
    
    Args:
        start_time: 开始时间（毫秒时间戳）
        end_time: 结束时间（毫秒时间戳）
        model: 查询模式 1=全部 2=客服组 3=客服
        staff_group_list: 客服组 ID 列表
        staff_id_list: 客服 ID 列表
        page: 页码
        page_size: 每页数量（1-1000）
    
    返回字段：
    - loginDuration: 值班总时长
    - onlineDuration: 在线时长
    - restDuration: 小休时长
    - hangDuration: 挂起时长
    - firstLoginTs/firstOnlineTs/lastLogoutTs: 登录/上线/登出时间
    - 等等...
    """
    data = {
        'page': page,
        'pageSize': min(page_size, 1000)
    }
    if start_time: data['startTime'] = start_time
    if end_time: data['endTime'] = end_time
    if model: data['model'] = model
    if staff_group_list: data['staffGroupList'] = staff_group_list
    if staff_id_list: data['staffIdList'] = staff_id_list
    
    result = api_request('/statistic/staffAttendance', data)
    return parse_result(result)

# ==================== 客服考勤明细 ====================
def get_attendance_detail(staff_id, start_time=None):
    """
    客服考勤明细 - 单个客服一天的详细考勤记录
    
    Args:
        staff_id: 客服 ID（必填）
        start_time: 开始时间（毫秒时间戳），不传默认当天
    
    返回字段：
    - loginRecords: 登录详情列表
      - login: 登录时间
      - logout: 登出时间
      - middle: 中间事件列表
    """
    data = {'staffId': staff_id}
    if start_time: data['startTime'] = start_time
    
    result = api_request('/statistic/salaryDetail', data)
    return parse_result(result)

# ==================== 历史数据总览 ====================
def get_history_overview(start_time=None, end_time=None, staff_ids=None, session_origin=None, distribute_ids=None, distribute_staff_ids=None):
    """
    历史数据总览 - 查询指定时间段的数据汇总
    
    Args:
        start_time: 开始时间（毫秒时间戳）
        end_time: 结束时间（毫秒时间戳），查询 T 日数据需传 T 日最后一毫秒
        staff_ids: 客服 ID 列表
        session_origin: 会话发起方 0=所有 1=来访 2=主动
        distribute_ids: 分流客服组 ID 列表
        distribute_staff_ids: 分流客服 ID 列表
    
    ⚠️ 注意：当天数据不支持查询，频率限制 1 分钟 1 次
    
    返回字段：
    - sessions: 总会话数
    - effectSessions: 有效会话数
    - assignedRatio: 接入率
    - satisfactionRatio: 相对满意度
    - avgFirstRespTime: 平均首次响应时长
    - avgRespTime: 平均响应时长
    - oneOffRatio: 一次解决率
    - visit: 总来访量
    - 等等...
    """
    data = {}
    if start_time: data['startTime'] = start_time
    if end_time: data['endTime'] = end_time
    if staff_ids: data['staffIds'] = staff_ids
    if session_origin is not None: data['sessionOrigin'] = session_origin
    if distribute_ids: data['distributeIds'] = distribute_ids
    if distribute_staff_ids: data['distributeStaffIds'] = distribute_staff_ids
    
    result = api_request('/statistic/overview', data)
    return parse_result(result)

# ==================== 客服工作量报表 ====================
def get_staff_workload(start_time=None, end_time=None, model=1, staff_group_list=None, staff_id_list=None):
    """
    客服工作量报表
    
    Args:
        start_time: 开始时间（毫秒时间戳）
        end_time: 结束时间（毫秒时间戳）
        model: 查询模式 1=全部 2=客服组 3=客服
        staff_group_list: 客服组 ID 列表
        staff_id_list: 客服 ID 列表
    
    返回字段：
    - totalSessionCount: 会话总量
    - sessionsCount: 接入会话量
    - validSessionCount: 有效会话量
    - noReplySessionsCount: 未回复会话量
    - messageDealCount: 留言处理量
    - 等等...
    """
    data = {}
    if start_time: data['startTime'] = start_time
    if end_time: data['endTime'] = end_time
    if model: data['model'] = model
    if staff_group_list: data['staffGroupList'] = staff_group_list
    if staff_id_list: data['staffIdList'] = staff_id_list
    
    result = api_request('/statistic/staffworklod', data)
    return parse_result(result)

# ==================== 客服满意度报表 ====================
def get_satisfaction_report(start_time=None, end_time=None, model=1, staff_group_list=None, staff_id_list=None):
    """
    客服满意度报表 - 客服维度满意度数据
    
    Args:
        start_time: 开始时间（毫秒时间戳）
        end_time: 结束时间（毫秒时间戳）
        model: 查询模式 1=全部 2=客服组 3=客服
        staff_group_list: 客服组 ID 列表
        staff_id_list: 客服 ID 列表
    
    返回字段：
    - verySatisfiedCount: 非常满意会话数
    - satisfiedCount: 满意会话数
    - normalSatisfiedCount: 一般会话数
    - notSatisfiedCount: 不满意会话数
    - veryNotSatisfiedCount: 非常不满意会话数
    - satisfactionRatio: 相对满意度
    - 等等...
    """
    data = {}
    if start_time: data['startTime'] = start_time
    if end_time: data['endTime'] = end_time
    if model: data['model'] = model
    if staff_group_list: data['staffGroupList'] = staff_group_list
    if staff_id_list: data['staffIdList'] = staff_id_list
    
    result = api_request('/statistic/satisfaction/report', data)
    return parse_result(result)

# ==================== 短信任务 ====================
def send_sms_task(template_id, mobile_list, params=None):
    """
    创建短信发送任务
    
    Args:
        template_id: 短信模板 ID（必传）
        mobile_list: 手机号列表（必传，最多 20 个）
        params: 模板参数列表（非必传，每个参数最大 30 字符）
    
    Returns:
        dict: {'success': True, 'task_id': 123} 或 {'success': False, 'error': 'xxx', 'code': xxx}
    
    错误码：
    - 67407: 企业短信服务未开通
    - 67406: 模板 ID 或手机号参数不正确
    - 67408: 手机号个数不正确（超过 20 个）
    - 67501: 手机号格式不正确
    - 67502: 模板参数长度不正确
    """
    data = {
        'templateId': template_id,
        'mobileList': mobile_list
    }
    if params:
        data['params'] = params
    
    result = api_request('/smstask/create', data)
    
    if result.get('code') == 200:
        return {'success': True, 'task_id': result.get('message')}
    else:
        return {'success': False, 'error': result.get('message', 'Unknown error'), 'code': result.get('code')}

def get_sms_task_status(task_id_list):
    """
    获取短信任务状态
    
    Args:
        task_id_list: 短信任务 ID 列表（必传，最多 100 个）
    
    Returns:
        dict: 任务状态列表
    
    状态说明：
    - status > 0 && status < 100: 发送中
    - 150: 发送成功
    - -91 ~ -100: 各种失败原因（余额不足、模板审核未通过、手机号格式错误等）
    """
    data = {'taskIdList': task_id_list}
    result = api_request('/smstask/status', data)
    
    if result.get('code') == 200:
        return {'success': True, 'data': result.get('message', [])}
    else:
        return {'success': False, 'error': result.get('message', 'Unknown error'), 'code': result.get('code')}

def format_sms_status(status):
    """
    格式化短信状态码为可读文本
    """
    status_map = {
        150: "发送成功",
        -100: "任务发送失败",
        -99: "模板或签名审核未通过",
        -98: "发送失败",
        -97: "发送失败",
        -96: "最大条数限制",
        -95: "发送失败",
        -94: "手机号格式错误",
        -93: "余额不足",
        -92: "模板或签名类型不匹配",
        -91: "发送失败",
    }
    
    if status > 0 and status < 100:
        return f"发送中 ({status}%)"
    return status_map.get(status, f"未知状态 ({status})")

# ==================== 会话导出 API ====================
def get_session_detail(session_id):
    """
    获取单条会话详情（含消息列表）
    
    Args:
        session_id: 会话 ID
    
    Returns:
        dict: 会话详情
    
    ⚠️ 频率限制：每秒不能超过 5 次
    """
    data = {'sessionId': session_id}
    result = api_request('/export/session/one', data)
    return parse_result(result)

def get_session_messages(session_id, m_types=None):
    """
    获取会话的所有消息
    
    Args:
        session_id: 会话 ID
        m_types: 消息类型筛选，逗号分隔（如 "1,110"）
    
    Returns:
        dict: 消息列表
    
    ⚠️ 频率限制：每秒不能超过 5 次
    """
    data = {'sessionId': session_id}
    if m_types:
        data['mTypes'] = m_types
    
    result = api_request('/export/session/one/message', data)
    return parse_result(result)

# ==================== 用户信息 API ====================
def get_session_user_profile(session_id):
    """
    获取会话关联的用户信息
    
    Args:
        session_id: 会话 ID
    
    Returns:
        dict: 用户信息
        - id: 用户 ID
        - name: 名字
        - phone: 电话
        - foreign_id: 外部 ID
        - address: 地址
        - vipLevel: VIP 等级
        - remarks: 备注
        - customField: 自定义属性
    """
    data = {'sessionId': session_id}
    result = api_request('/session/user/profile', data)
    return parse_result(result)

# ==================== 咨询分类 API ====================
def get_session_categories(session_type=1):
    """
    获取咨询分类（五级树状结构）
    
    Args:
        session_type: 1=在线会话分类
    
    Returns:
        dict: 分类树
    """
    data = {'type': session_type}
    result = api_request('/online/session/category/list', data)
    return parse_result(result)

# ==================== 服务小记 API ====================
def get_session_customfield(session_id):
    """
    获取会话的服务小记模板和已填写记录
    
    Args:
        session_id: 会话 ID
    
    Returns:
        dict: 
        - templates: 服务小记模板列表
        - selectedTemplateId: 已选择的模板 ID
        - historyFieldValues: 已填写的字段值
        - sessionInfo: 会话信息
    """
    data = {'sessionId': session_id}
    result = api_request('/online/session/customfield/template', data)
    return parse_result(result)

def update_session_customfield(session_id, template_id, custom_fields, status=None, category=None, description=None):
    """
    更新会话服务小记
    
    Args:
        session_id: 会话 ID
        template_id: 模板 ID
        custom_fields: 自定义字段列表 [{"id": 123, "value": "xxx"}]
        status: 问题解决状态 (0:未解决，1:已解决，2:解决中)
        category: 咨询分类 ID
        description: 会话备注（最多 500 字符）
    
    Returns:
        dict: 更新结果
    """
    data = {
        'sessionId': session_id,
        'templateId': template_id,
        'customfield': json.dumps(custom_fields) if isinstance(custom_fields, list) else custom_fields
    }
    if status is not None:
        data['status'] = status
    if category is not None:
        data['category'] = category
    if description is not None:
        data['description'] = description
    
    result = api_request('/online/session/customfield/update', data)
    return parse_result(result)

# ==================== 会话摘要 API ====================
def create_session_summary(session_id):
    """
    提交会话摘要总结任务（AI 生成）
    
    Args:
        session_id: 会话 ID
    
    Returns:
        dict: {'success': True, 'message': 'success'} 或错误信息
    
    ⚠️ 频率限制：每分钟 120 次
    ⚠️ 需要开通会话摘要权限
    """
    data = {'sessionId': session_id}
    result = api_request('/session/summary', data)
    
    if result.get('code') == 200:
        return {'success': True, 'message': result.get('message')}
    else:
        return {'success': False, 'error': result.get('message'), 'code': result.get('code')}

def get_session_summary_result(session_id):
    """
    获取会话摘要生成结果
    
    Args:
        session_id: 会话 ID
    
    Returns:
        dict:
        - status: 0 无摘要，1 生成中，2 有敏感内容，3 完成，4 被拒绝，5 完成
        - context: 摘要内容（AI 生成）
    
    ⚠️ 频率限制：每分钟 120 次
    """
    data = {'sessionId': session_id}
    result = api_request('/session/summary/getResult', data)
    
    if result.get('code') == 200:
        return {'success': True, 'data': result.get('data', {}), 'message': result.get('message')}
    else:
        return {'success': False, 'error': result.get('message'), 'code': result.get('code')}

# ==================== 坐席状态 API ====================
def get_staff_status(model=1, staff_group_list=None, staff_id_list=None, page=1, page_size=50):
    """
    获取坐席实时状态
    
    Args:
        model: 1=全部，2=客服组列表，3=客服列表
        staff_group_list: 客服组 ID 列表（model=2 时有效，最多 100 个）
        staff_id_list: 客服 ID 列表（model=3 时有效，最多 1000 个）
        page: 页码
        page_size: 每页数量（1-50）
    
    Returns:
        dict: 坐席状态列表
        - id: 坐席 ID
        - state: 0 离线，1 在线，2 挂起，3 小休，9 管理端在线
        - ext: 扩展状态
        - startTime: 状态开始时间
    
    ⚠️ 频率限制：每分钟 60 次
    """
    data = {
        'model': model,
        'page': page,
        'pageSize': min(page_size, 50)
    }
    if staff_group_list:
        data['staffGroupList'] = staff_group_list
    if staff_id_list:
        data['staffIdList'] = staff_id_list
    
    result = api_request('/chat/seatStatus', data)
    
    if result.get('code') == 200:
        # data 字段可能是字符串化的 JSON
        data_str = result.get('data', '[]')
        if isinstance(data_str, str):
            try:
                data_list = json.loads(data_str)
            except:
                data_list = []
        else:
            data_list = data_str
        return {'success': True, 'data': data_list}
    else:
        return {'success': False, 'error': result.get('message'), 'code': result.get('code')}

def get_staff_ext_status():
    """
    获取客服自定义状态（小休细分状态）
    
    Returns:
        dict: 自定义状态列表
        - eventId: 2=挂起，5=小休
        - eventList: [{eventIdExt, orderNo, name}]
    """
    result = api_request('/chat/event/ext/', {})
    
    if result.get('code') == 200:
        data_str = result.get('data', '[]')
        if isinstance(data_str, str):
            try:
                data_list = json.loads(data_str)
            except:
                data_list = []
        else:
            data_list = data_str
        return {'success': True, 'data': data_list}
    else:
        return {'success': False, 'error': result.get('message'), 'code': result.get('code')}

# ==================== 服务时间 API ====================
def get_service_time_templates():
    """
    获取服务时间模板
    
    Returns:
        dict: 模板列表
        - id: 模板 ID
        - name: 模板名称
        - normalServiceTime: 常规工作时间
        - specialServiceTime: 非常规工作时间
        - type: 1=时间段，2=全天不服务
    """
    result = api_request('/chat/service/time/template/', {})
    
    if result.get('code') == 200:
        data_str = result.get('data', '[]')
        if isinstance(data_str, str):
            try:
                data_list = json.loads(data_str)
            except:
                data_list = []
        else:
            data_list = data_str
        return {'success': True, 'data': data_list}
    else:
        return {'success': False, 'error': result.get('message'), 'code': result.get('code')}

def get_service_time_configs():
    """
    获取服务时间配置（客服组/渠道/机器人）
    
    Returns:
        dict: 配置列表
        - enable: 是否开启
        - serviceTimeInfoList: 配置详情
    """
    result = api_request('/chat/service/time/config/', {})
    
    if result.get('code') == 200:
        data_str = result.get('data', '[]')
        if isinstance(data_str, str):
            try:
                data_list = json.loads(data_str)
            except:
                data_list = []
        else:
            data_list = data_str
        return {'success': True, 'data': data_list}
    else:
        return {'success': False, 'error': result.get('message'), 'code': result.get('code')}

# ==================== 微信模板消息 ====================
def set_wx_template(app_id, logistic_config):
    """
    设置微信模板消息（物流类）
    
    Args:
        app_id: 公众号 appId
        logistic_config: 物流模板配置
        {
            "template_id": "xxx",
            "top": "first",
            "bottom": "remark",
            "id": "keyword1",
            "name": "keyword2",
            ...
        }
    
    Returns:
        dict: 设置结果
    """
    data = {
        'appId': app_id,
        'logistic': logistic_config
    }
    result = api_request('/settings/wxTemplates', data)
    
    if result.get('code') == 200:
        return {'success': True, 'message': result.get('message')}
    else:
        return {'success': False, 'error': result.get('message'), 'code': result.get('code')}

# ==================== 工单 API ====================
# 工单状态: 1=已提交, 5=待申领, 10=处理中, 20=已完结, 25=已驳回, 50=挂起
# 优先级: 2=低, 5=一般, 8=紧急, 10=非常紧急

def search_tickets(ticket_id=None, mobile=None, limit=50, offset=0,
                   sort_by='ct', order='desc', start=None, end=None,
                   op_start=None, op_end=None, with_custom_field=False,
                   uid=None, with_mail_reply_list=False):
    """
    搜索工单（核心查询接口）
    
    Args:
        ticket_id: 工单ID（与 mobile 二选一）
        mobile: 用户手机号（与 ticket_id 二选一）
        limit: 一次请求获取的工单数上限，最大 500，最小 1
        offset: 偏移量，从 0 开始
        sort_by: 排序方式，默认 'ct' 创建时间
            'ct': 创建时间, 'pr': 优先级, 'ut': 上一次操作时间,
            'reminderCount': 催单次数, 'staffReminderCount': 坐席催单次数,
            'foreignReminderCount': 访客催单次数, 'sheet_id': 工单id,
            'firstDispatchTime': 首次分配时间, 'reopenNum': 重开次数, 'status': 工单状态
        order: 升降序，默认 'desc' 降序，可选 'asc' 正序
        start: 起始毫秒时间戳（不传默认支持30天跨度）
        end: 截止毫秒时间戳
        op_start: 操作时间起始毫秒时间戳
        op_end: 操作时间截止毫秒时间戳（不超过90天）
        with_custom_field: 是否包含自定义字段信息，默认 False
        uid: 访客的 foreignid
        with_mail_reply_list: 是否返回工单的邮件列表，默认 False
    
    Returns:
        dict: 搜索结果
        - total: 工单总数
        - tickets: 工单列表 [{id, staffId, templateId, userName, userEmail, userMobile,
          typeId, priority, groupId, title, content, status, properties, createTime,
          custom, connectionType, connectionId, pluginUrl, mailReplyList}]
    
    ⚠️ ticketId 和 mobile 二选一
    ⚠️ 时间跨度不得超过 90 天
    ⚠️ 频率限制：每分钟 60 次
    """
    data = {
        'limit': min(limit, 500),
        'offset': offset,
        'sortBy': sort_by,
        'order': order
    }
    if ticket_id is not None:
        data['ticketId'] = ticket_id
    if mobile is not None:
        data['mobile'] = mobile
    if start:
        data['start'] = start
    if end:
        data['end'] = end
    if op_start:
        data['opStart'] = op_start
    if op_end:
        data['opEnd'] = op_end
    if with_custom_field:
        data['withCustomField'] = True
    if uid is not None:
        data['uid'] = uid
    if with_mail_reply_list:
        data['withMailReplyList'] = True
    
    result = api_request('/v2/ticket/search', data)
    return parse_result(result)


def get_ticket_detail(ticket_id):
    """
    获取工单详情
    
    Args:
        ticket_id: 工单ID
    
    Returns:
        dict: 工单详情
        - id: 工单id
        - title: 工单标题
        - content: 工单内容
        - status: 工单状态
        - priority: 优先级 (2=低, 5=一般, 8=紧急, 10=非常紧急)
        - templateName: 模板名称
        - targetGroup: 受理组名称
        - groupId: 客服组id
        - staffId: 创建工单的客服id
        - holderId: 当前客服ID
        - userMobile: 用户手机
        - userEmail: 用户邮箱
        - userName: 用户姓名
        - createTime: 工单创建时间
        - lastFinishTime: 最近一次完结时间
        - fromType: 来源渠道
        - questionType: 工单分类 {id, name, parent, path}
        - custom: 自定义字段
        - attachments: 附件 [{name, size, type, url}]
        - follower: 工单关注人
    
    ⚠️ 频率限制：每分钟 60 次
    """
    data = {'ticketId': ticket_id}
    result = api_request('/v2/ticket/new/detail', data)
    return parse_result(result)


def get_ticket_logs(ticket_id):
    """
    获取工单日志列表
    
    Args:
        ticket_id: 工单ID
    
    Returns:
        dict: 工单日志列表
        - id: 日志id
        - action: 操作名称
        - actionType: 操作类型
        - operator: 操作人
        - operatorId: 操作客服ID
        - time: 操作时间
        - info: 变更详情 [{title, content}]
        - attachments: 附件
    
    ⚠️ 频率限制：每分钟 60 次
    """
    data = {'ticketId': ticket_id}
    result = api_request('/v2/ticket/log', data)
    return parse_result(result)

# ==================== 辅助函数 ====================
def ms_timestamp(dt=None):
    """获取毫秒时间戳"""
    if dt is None:
        return int(time.time() * 1000)
    return int(dt.timestamp() * 1000)

def days_ago(days):
    """获取 N 天前的毫秒时间戳"""
    dt = datetime.now() - timedelta(days=days)
    return int(dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)

def today_end():
    """获取今天最后一毫秒"""
    now = datetime.now()
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    return int(today_end.timestamp() * 1000)

# ==================== 主程序 ====================
def format_realtime(data):
    """格式化实时数据输出"""
    if not data:
        return "无数据"
    
    lines = [
        f"👥 在线客服：{data.get('kefuCount', 0)} 人",
        f"📞 当前咨询：{data.get('sessionCount', 0)} 人",
        f"⏳ 当前排队：{data.get('queueCount', 0)} 人",
        f"✅ 已接入会话：{data.get('sessionInCount', 0)}",
        f"❌ 未接入会话：{data.get('leaveSessionCount', 0)}",
        f"📊 今日总会话：{data.get('totalSessionCount', 0)}",
        f"⏱️ 平均会话时长：{data.get('averageServiceTime', 0) // 1000} 秒",
        f"⏱️ 平均排队时长：{data.get('averageWaitingTime', 0) // 1000} 秒",
        f"⚡ 接入率：{data.get('servicePercent', 0) * 100:.2f}%",
        f"⭐ 满意度：{data.get('relativeSatisfactionPercent', 0) * 100:.2f}%",
        f"📝 参评率：{data.get('evaluatePercent', 0) * 100:.2f}%",
    ]
    return "\n".join(lines)

if __name__ == '__main__':
    print("🗡️ 七鱼客服数据拉取脚本")
    print("=" * 60)
    
    # 检查凭证
    if QIYU_APP_KEY == "你的 appKey" or QIYU_APP_SECRET == "你的 appSecret":
        print("❌ 请先填写 appKey 和 appSecret！")
        print("   位置：七鱼后台 → 系统 → 扩展与集成")
        exit(1)
    
    print("✅ 凭证已配置")
    
    # 获取实时数据 - 整体
    print("\n" + "=" * 60)
    print("📊 实时客服数据 - 整体")
    print("=" * 60)
    result = get_realtime_overview()
    
    if result.get('success'):
        print(format_realtime(result.get('data', {})))
    else:
        print(f"❌ 获取失败：{result.get('error')}")
    
    # 获取实时数据 - 未成年人投诉组
    print("\n" + "=" * 60)
    print("📊 实时客服数据 - 未成年人投诉组 (ID: 484896336)")
    print("=" * 60)
    result_minor = get_realtime_overview(to_group=[484896336])
    
    if result_minor.get('success'):
        print(format_realtime(result_minor.get('data', {})))
    else:
        print(f"❌ 获取失败：{result_minor.get('error')}")
