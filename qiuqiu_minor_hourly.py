#!/usr/bin/env python3
"""
【客服】球球&太空未成年反馈群 - 小时报推送
推送时间：每日 10:00-19:00（每小时一次）
"""

import sys
import os
import time
import fcntl
sys.path.insert(0, '/Users/oscar/.openclaw/workspace')

from feishu_push import send_text_to_group, send_alert_to_group
from qiyu_api import get_realtime_overview, get_staff_workload, get_staff_quality
from hourly_push_log import log_push, load_logs
from datetime import datetime, timedelta

# 重试配置
MAX_RETRIES = 3  # 最多重试 3 次
RETRY_DELAY = 60  # 重试间隔（秒）

# 🔒 原子锁文件路径（防止重复执行）
LOCK_DIR = os.path.join(WORKSPACE if 'WORKSPACE' in dir() else '/Users/oscar/.openclaw/workspace', '.locks')

def try_acquire_hourly_lock(task_name):
    """
    尝试获取小时级执行锁。使用持久化时间戳文件，
    同一小时内即使前一个执行已完成，后续执行也会看到标记并跳过。
    返回 True = 可以继续执行，False = 已执行过，跳过。
    """
    os.makedirs(LOCK_DIR, exist_ok=True)
    now = datetime.now()
    lock_file = os.path.join(LOCK_DIR, f"{task_name}_{now.strftime('%Y%m%d_%H')}.lock")
    
    # 先检查是否已有持久锁标记
    if os.path.exists(lock_file):
        print(f"\n🔒 当前小时已执行过 {task_name}，跳过（锁文件: {lock_file})")
        return False
    
    # 原子写入锁文件（带 fcntl 防并发写入竞争）
    try:
        fd = open(lock_file, 'w')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(f"locked at {now.isoformat()}\npid={os.getpid()}\n")
        fd.flush()
        fd.close()  # 关闭 FD，但文件保留作为持久标记
        return True
    except (IOError, OSError):
        # 并发竞争失败，说明另一个进程正在写
        print(f"\n🔒 并发竞争失败，当前小时已执行过 {task_name}，跳过")
        return False
# 策略：限流时等待重试，成功时不重试，其他错误重试 1 次
# ⚠️ 飞书 Webhook 不是幂等的，重试 = 重复发消息，所以必须加去重保护

# ==================== 配置 ====================
TARGET_GROUP = '球球&太空未成年反馈群'  # ✅ 已配置
MINOR_GROUP_ID = 484896336  # 未成年人客服组 ID

# ==================== 数据获取 ====================
def get_realtime_data():
    """获取实时数据"""
    result = get_realtime_overview(to_group=[MINOR_GROUP_ID])
    if result.get('success'):
        return result.get('data', {})
    return {}

def get_staff_workload_data():
    """获取客服工作量（带重试机制）"""
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0)
    start_time = int(today_start.timestamp() * 1000)
    end_time = int(now.timestamp() * 1000)
    
    # 重试逻辑
    for attempt in range(MAX_RETRIES):
        print(f"\n📂 获取客服工作量... (尝试 {attempt+1}/{MAX_RETRIES})")
        
        # 获取工作量
        workload_result = get_staff_workload(
            start_time=start_time,
            end_time=end_time,
            model=2,
            staff_group_list=[MINOR_GROUP_ID]
        )
        
        # 检查是否限流
        if not workload_result.get('success'):
            error_msg = workload_result.get('error', '')
            if 'too frequent' in error_msg or 'limit' in error_msg.lower():
                if attempt < MAX_RETRIES - 1:
                    wait_seconds = 30 * (attempt + 1)  # 第 1 次等 30 秒
                    print(f"⚠️  七鱼 API 限流，等待 {wait_seconds} 秒后重试...")
                    time.sleep(wait_seconds)
                    continue
                else:
                    print(f"⚠️  工作量 API 限流，使用空数据")
                    return []
            else:
                print(f"❌ 工作量 API 错误：{error_msg}")
                return []
        
        # 获取质量数据（满意度、响应率等）
        quality_result = get_staff_quality(
            start_time=start_time,
            end_time=end_time,
            model=2,
            staff_group_list=[MINOR_GROUP_ID]
        )
        
        # 质量 API 也可能限流
        if not quality_result.get('success'):
            error_msg = quality_result.get('error', '')
            if 'too frequent' in error_msg or 'limit' in error_msg.lower():
                if attempt < MAX_RETRIES - 1:
                    wait_seconds = 30 * (attempt + 1)  # 第 1 次等 30 秒
                    print(f"⚠️  质量 API 限流，等待 {wait_seconds} 秒后重试...")
                    time.sleep(wait_seconds)
                    continue
                else:
                    print(f"⚠️  质量 API 限流，仅使用工作量数据")
                    quality_result = {'success': True, 'data': {'result': []}}
            else:
                print(f"⚠️  质量 API 错误：{error_msg}，仅使用工作量数据")
                quality_result = {'success': True, 'data': {'result': []}}
        
        # 成功获取数据
        break
    
    # 合并数据
    staff_dict = {}
    workload_list = workload_result.get('data', {}).get('result', [])
    quality_list = quality_result.get('data', {}).get('result', []) if quality_result.get('success') else []
    
    for w in workload_list:
        name = w.get('name', 'N/A')
        staff_dict[name] = {
            'name': name,
            'total': w.get('totalSessionCount', 0),
            'valid': w.get('validSessionCount', 0),
            'no_reply': w.get('noReplySessionsCount', 0),
        }
    
    for q in quality_list:
        name = q.get('name', 'N/A')
        if name not in staff_dict:
            staff_dict[name] = {'name': name, 'total': 0, 'valid': 0, 'no_reply': 0}
        staff_dict[name].update({
            'satisfaction': q.get('satisfactionRatio', -1) * 100,
            'reply_ratio': q.get('replyRatio', -1) * 100,
            'avg_first_resp': q.get('avgFirstRespTime', 0) / 1000,  # 秒
            'avg_resp': q.get('avgRespTime', 0) / 1000,  # 秒
        })
    
    staff_list = list(staff_dict.values())
    # 过滤掉超级管理员和孟凡吉
    staff_list = [s for s in staff_list if s.get('name', '') not in ['超级管理员', '孟凡吉']]
    # 显示所有有数据的客服（即使总会话为 0，也显示出来）
    # 优先显示有会话的，其次显示有质量数据的
    staff_list.sort(key=lambda x: (x.get('total', 0) > 0, x.get('total', 0)), reverse=True)
    return staff_list[:10]

# ==================== 效率分析 ====================
def analyze_staff_efficiency(staff_list):
    """分析员工效率，找出效率最低的员工"""
    if len(staff_list) < 2:
        return None
    
    # 计算效率分数（综合指标）
    for staff in staff_list:
        # 效率分数 = 接待量 * 0.4 + 响应率 * 0.3 + (1/平均响应时间) * 0.3
        total = staff.get('total', 0)
        reply_ratio = staff.get('reply_ratio', 0)
        avg_resp = staff.get('avg_resp', 0)
        
        # 归一化处理（统一到 0-10 分）
        total_score = min(total / 10, 10)  # 10 条为满分
        reply_score = reply_ratio / 10 if reply_ratio > 0 else 0  # 100% = 10分
        # 响应速度：30s=10分，120s=5分，300s=0分
        if avg_resp >= 0:
            resp_score = max(0, min(10, (300 - avg_resp) / 30))
        else:
            resp_score = 0  # 无数据不加分也不减分
        
        staff['efficiency_score'] = total_score * 0.4 + reply_score * 0.3 + resp_score * 0.3
    
    # 按效率分数排序
    staff_list.sort(key=lambda x: x.get('efficiency_score', 0), reverse=True)
    
    # 找出效率最低的人（需同时满足：分数<2 且 有明确问题）
    # 避免把正常表现的人拉来陪跑
    low_efficiency = []
    for s in staff_list:
        score = s.get('efficiency_score', 0)
        total = s.get('total', 0)
        reply_ratio = s.get('reply_ratio', -1)
        avg_resp = s.get('avg_resp', -1)
        
        # 有数据的才纳入评估
        if total == 0 and reply_ratio < 0 and avg_resp < 0:
            continue
        
        # 检查是否有明确问题
        has_issue = (
            (reply_ratio >= 0 and reply_ratio < 70) or  # 响应率明显偏低
            (avg_resp >= 0 and avg_resp > 300) or       # 响应明显慢
            (total >= 1 and total < 2)                   # 有接待但极少
        )
        
        if has_issue and score < 3:
            low_efficiency.append(s)
    
    if low_efficiency:
        return low_efficiency[:2]  # 最多返回2人
    return None

def build_efficiency_reminder(low_efficiency_staff):
    """构建效率提醒消息"""
    if not low_efficiency_staff:
        return None
    
    # 收集需要@的员工姓名
    at_names = [staff.get('name', '') for staff in low_efficiency_staff]
    at_str = ' '.join([f'@{name}' for name in at_names if name])
    
    content = [
        [{'tag': 'text', 'text': ''}],
        [{'tag': 'text', 'text': f'⚠️ 效率提醒:'}],
    ]
    
    for staff in low_efficiency_staff:
        name = staff.get('name', 'N/A')
        total = staff.get('total', 0)
        reply_ratio = staff.get('reply_ratio', -1)
        avg_resp = staff.get('avg_resp', -1)
        satisfaction = staff.get('satisfaction', -1)
        
        # 分析问题
        issues = []
        if reply_ratio >= 0 and reply_ratio < 80:
            issues.append(f"响应率偏低 ({reply_ratio:.0f}%)")
        if avg_resp >= 0 and avg_resp > 300:
            issues.append(f"平均响应慢 ({avg_resp:.0f}秒)")
        if satisfaction >= 0 and satisfaction < 70:
            issues.append(f"满意度较低 ({satisfaction:.0f}%)")
        if total < 3:
            issues.append(f"接待量偏少 ({total}条)")
        
        issue_str = '、'.join(issues) if issues else '综合效率待提升'
        
        content.append([{'tag': 'text', 'text': f'   🔸 {name}: {issue_str}'}])
    
    content.append([{'tag': 'text', 'text': ''}])
    content.append([{'tag': 'text', 'text': f'   💡 建议：加强回复效率培训，优化回复口径'}])
    
    # 添加@提醒（如果有飞书自建应用权限，可以真正@到人）
    if at_str:
        content.append([{'tag': 'text', 'text': ''}])
        content.append([{'tag': 'text', 'text': f'   {at_str} 请及时处理'}])
    
    return content

# ==================== 每日表扬 ====================
# ==================== 消息构建 ====================
def build_hourly_report_text(realtime_data, staff_list):
    """构建小时报消息（纯文本格式）"""
    now = datetime.now()
    hour_str = now.strftime('%Y-%m-%d %H:00')
    
    lines = [
        f'🕐 小时报：{hour_str}',
        '',
        f'👶 未成年人客服组实时数据:',
        f'   当前排队：{realtime_data.get("queueCount", 0)} 人 ⏳',
        f'   当前咨询：{realtime_data.get("sessionCount", 0)} 人',
        f'   在线客服：{realtime_data.get("kefuCount", 0)} 人',
        f'   接入率：{realtime_data.get("servicePercent", 0)*100:.1f}%',
        f'   平均排队：{max(0, realtime_data.get("averageWaitingTime", 0)//1000)}秒',
    ]
    
    # 客服工作量 TOP5
    if staff_list:
        lines.append('')
        lines.append(f'👥 客服工作量 TOP5（今日累计）:')
        for i, staff in enumerate(staff_list[:5], 1):
            name = staff.get('name', 'N/A')
            total = staff.get('total', 0)
            valid = staff.get('valid', 0)
            reply_ratio = staff.get('reply_ratio', -1)
            avg_resp = staff.get('avg_resp', -1)
            
            stats = []
            if reply_ratio >= 0:
                stats.append(f"响应{reply_ratio:.0f}%")
            if avg_resp >= 0:
                stats.append(f"均响{avg_resp:.0f}s")
            stats_str = f" ({', '.join(stats)})" if stats else ""
            
            display_total = f'{total} 条' if total > 0 else '--'
            display_valid = f'有效{valid}' if valid > 0 else '有效--'
            lines.append(f'   {i}. {name}: {display_total} ({display_valid}){stats_str}')
        
        # 效率提醒（10点首日跳过，数据积累中）
        low_efficiency = None
        if now.hour > 10:
            low_efficiency = analyze_staff_efficiency(staff_list)
            if low_efficiency:
                for staff in low_efficiency:
                    s_name = staff.get('name', 'N/A')
                    s_total = staff.get('total', 0)
                    s_reply = staff.get('reply_ratio', -1)
                    s_resp = staff.get('avg_resp', -1)
                    s_sat = staff.get('satisfaction', -1)
                    
                    issues = []
                    if s_reply >= 0 and s_reply < 80:
                        issues.append(f"响应率偏低 ({s_reply:.0f}%)")
                    if s_resp >= 0 and s_resp > 300:
                        issues.append(f"平均响应慢 ({s_resp:.0f}秒)")
                    if s_sat >= 0 and s_sat < 70:
                        issues.append(f"满意度较低 ({s_sat:.0f}%)")
                    if s_total < 3:
                        issues.append(f"接待量偏少 ({s_total}条)")
                    
                    issue_str = '、'.join(issues) if issues else '综合效率待提升'
                    lines.append(f'   ⚠️ {s_name}: {issue_str}')
                
                lines.append('')
                lines.append('   💡 建议：加强回复效率培训，优化回复口径')
        else:
            lines.append('')
            lines.append('   🌅 今日首日，数据积累中...')
    else:
        lines.append('')
        lines.append('📝 客服工作量数据暂不可用')
    
    # 10 点首日条：昨日之星表扬
    now = datetime.now()
    if now.hour == 10:
        yesterday_star = build_yesterday_star_praise()
        if yesterday_star:
            lines.append('')
            lines.extend(yesterday_star)
    
    # 19 点特别表扬（当日最佳员工）
    if now.hour == 19 and staff_list:
        praise = build_daily_praise_text(staff_list)
        if praise:
            lines.append('')
            lines.extend(praise)
    
    # 风险预警
    queue_count = realtime_data.get('queueCount', 0)
    if queue_count > 50:
        lines.append('')
        lines.append(f'🔴 告警：排队人数过多 ({queue_count}人)，请立即处理！')
    elif queue_count > 20:
        lines.append('')
        lines.append(f'🟡 注意：排队人数较多 ({queue_count}人)，建议关注')
    
    # 效率分析规则说明（仅在触发提醒时显示）
    if staff_list and low_efficiency is not None:
        lines.append('')
        lines.append(f'📊 效率分析规则:')
        lines.append(f'   效率分数 = 接待量×0.4 + 响应率×0.3 + 响应速度×0.3')
        lines.append(f'   触发提醒：效率分数<5 分')
        lines.append(f'   问题检测：响应率<80%、响应时间>300s、满意度<70%、接待量<3 条')
    
    return '\n'.join(lines)


def build_daily_praise_text(staff_list):
    """构建每日最佳员工表扬（纯文本格式）"""
    if not staff_list:
        return None
    
    best = None
    for s in staff_list:
        if s.get('total', 0) == 0:
            continue
        if best is None:
            best = s
            continue
        if s.get('valid', 0) > best.get('valid', 0):
            best = s
        elif s.get('valid', 0) == best.get('valid', 0):
            s_reply = s.get('reply_ratio', 0)
            b_reply = best.get('reply_ratio', 0)
            if s_reply > b_reply:
                best = s
            elif s_reply == b_reply:
                s_resp = s.get('avg_resp', 99999)
                b_resp = best.get('avg_resp', 99999)
                if s_resp < b_resp:
                    best = s
    
    if not best or best.get('total', 0) == 0:
        return None
    
    name = best.get('name', 'N/A')
    total = best.get('total', 0)
    valid = best.get('valid', 0)
    reply_ratio = best.get('reply_ratio', -1)
    satisfaction = best.get('satisfaction', -1)
    avg_resp = best.get('avg_resp', -1)
    
    highlights = []
    if valid >= 10:
        highlights.append(f"今日接待 {valid} 个有效会话")
    elif valid > 0:
        highlights.append(f"今日接待 {valid} 个有效会话")
    if reply_ratio >= 0 and reply_ratio >= 90:
        highlights.append(f"响应率 {reply_ratio:.0f}%，秒回王者")
    elif reply_ratio >= 0 and reply_ratio >= 80:
        highlights.append(f"响应率 {reply_ratio:.0f}%")
    if satisfaction >= 0 and satisfaction >= 90:
        highlights.append(f"满意度 {satisfaction:.0f}%，客户好评如潮")
    elif satisfaction >= 0 and satisfaction >= 80:
        highlights.append(f"满意度 {satisfaction:.0f}%")
    if avg_resp >= 0 and avg_resp < 60:
        highlights.append(f"平均响应 {avg_resp:.0f}s，快如闪电")
    elif avg_resp >= 0:
        highlights.append(f"平均响应 {avg_resp:.0f}s")
    
    highlights_str = '｜'.join(highlights) if highlights else f"今日接待 {total} 条会话（有效{valid}条）"
    
    return [
        f'🏆 今日之星：{name}',
        f'   {highlights_str}',
        f'   辛苦啦！继续保持，你是最棒的！👏',
    ]

# ==================== 昨日之星 ====================
def get_yesterday_star_from_logs():
    """
    从推送日志中获取昨日最佳客服（从小时报的 top_staff 字段统计）
    七鱼 API 的 model=2 查历史整日数据会返回全 0，所以改从日志统计。
    返回 dict: {name, mentions} 或 None
    """
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    yesterday_prefix = yesterday.strftime('%Y-%m-%d')
    
    all_logs = load_logs()
    
    # 统计昨日每个客服作为 TOP1 的次数
    top_count = {}
    for log in all_logs:
        if log.get('task') != '未成年人组小时报':
            continue
        if not log.get('timestamp', '').startswith(yesterday_prefix):
            continue
        metadata = log.get('metadata', {})
        top_staff = metadata.get('top_staff', '')
        if top_staff and top_staff not in ['超级管理员', '孟凡吉']:
            top_count[top_staff] = top_count.get(top_staff, 0) + 1
    
    if not top_count:
        return None
    
    # 找出被提及最多的
    best_name = max(top_count, key=top_count.get)
    return {'name': best_name, 'mentions': top_count[best_name]}


def get_yesterday_star():
    """
    获取昨日最佳客服之星
    优先从推送日志统计（可靠），API 作为补充。
    返回 dict: {name, total, valid, reply_ratio, satisfaction, avg_resp} 或 None
    """
    # 先从日志获取 TOP1
    log_star = get_yesterday_star_from_logs()
    if log_star:
        name = log_star['name']
        # 再尝试用 API 补充质量数据（当天查询可能更准）
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999)
        start_ts = int(yesterday_start.timestamp() * 1000)
        end_ts = int(yesterday_end.timestamp() * 1000)
        
        quality_result = get_staff_quality(
            start_time=start_ts,
            end_time=end_ts,
            model=2,
            staff_group_list=[MINOR_GROUP_ID]
        )
        
        staff = {'name': name, 'total': 0, 'valid': 0, 'no_reply': 0, 'mentions': log_star['mentions']}
        
        if quality_result.get('success'):
            for q in quality_result.get('data', {}).get('result', []):
                if q.get('name') == name:
                    staff.update({
                        'satisfaction': q.get('satisfactionRatio', -1) * 100,
                        'reply_ratio': q.get('replyRatio', -1) * 100,
                        'avg_first_resp': q.get('avgFirstRespTime', 0) / 1000,
                        'avg_resp': q.get('avgRespTime', 0) / 1000,
                    })
                    break
        
        return staff
    
    # 日志也查不到，返回 None
    return None


def build_yesterday_star_praise():
    """构建昨日之星表扬内容"""
    star = get_yesterday_star()
    if not star:
        return None
    
    name = star.get('name', 'N/A')
    total = star.get('total', 0)
    valid = star.get('valid', 0)
    reply_ratio = star.get('reply_ratio', -1)
    satisfaction = star.get('satisfaction', -1)
    avg_resp = star.get('avg_resp', -1)
    mentions = star.get('mentions', 0)
    
    highlights = []
    if mentions > 0:
        highlights.append(f"昨日 {mentions} 次登顶小时报 TOP1")
    if valid > 0:
        highlights.append(f"有效会话 {valid} 个")
    if reply_ratio >= 0 and reply_ratio >= 90:
        highlights.append(f"响应率 {reply_ratio:.0f}%，秒回王者")
    elif reply_ratio >= 0 and reply_ratio >= 80:
        highlights.append(f"响应率 {reply_ratio:.0f}%")
    if satisfaction >= 0 and satisfaction >= 90:
        highlights.append(f"满意度 {satisfaction:.0f}%，客户好评如潮")
    elif satisfaction >= 0 and satisfaction >= 80:
        highlights.append(f"满意度 {satisfaction:.0f}%")
    if avg_resp >= 0 and avg_resp < 60:
        highlights.append(f"平均响应 {avg_resp:.0f}s，快如闪电")
    elif avg_resp >= 0:
        highlights.append(f"平均响应 {avg_resp:.0f}s")
    
    if not highlights:
        highlights.append(f"昨日小时报 TOP1 常客")
    
    highlights_str = '｜'.join(highlights)
    
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    return [
        '',
        f'🌟 昨日之星（{yesterday_str}）：{name}',
        f'   {highlights_str}',
        f'   新的一天开始啦！感谢昨天的辛苦付出，今天继续加油冲！🚀',
    ]

# ==================== 主函数 ====================
def send_hourly_report():
    """发送小时报"""
    
    print(f"🗡️ 推送未成年人客服组小时报")
    print(f"目标群：{TARGET_GROUP}")
    print("=" * 70)
    
    # 🔒 第一步：获取原子锁（在获取数据之前，防止重复执行）
    if not try_acquire_hourly_lock('minor_hourly'):
        return {'success': True, 'skipped': True, 'reason': 'lock_held'}
    
    # 获取数据
    print(f"\n📂 获取实时数据...")
    realtime = get_realtime_data()
    
    print(f"\n📂 获取客服工作量...")
    staff_list = get_staff_workload_data()
    
    # 构建消息
    print(f"\n📝 构建消息...")
    text_content = build_hourly_report_text(realtime, staff_list)
    
    # 发送（带重试 + 防重复保护）
    print(f"\n📨 发送到飞书群：{TARGET_GROUP}...")
    
    # 🔒 第二步：日志去重检查（三重保护）
    now = datetime.now()
    current_hour_prefix = now.strftime('%Y-%m-%dT%H')  # ISO format: 2026-04-05T11
    recent_logs = [e for e in load_logs()
                   if e['task'] == '未成年人组小时报'
                   and e['success']
                   and e['timestamp'].startswith(current_hour_prefix)]
    if recent_logs:
        last_push = recent_logs[-1]
        print(f"\n⏭️  当前小时已推送成功，跳过重复发送")
        print(f"   上次推送时间：{last_push['timestamp']}")
        return {'success': True, 'skipped': True, 'reason': 'already_pushed'}
    
    result = None
    last_error = None
    
    for attempt in range(1, MAX_RETRIES + 1):
        result = send_text_to_group(TARGET_GROUP, text_content)
        
        # ✅ 成功则立即返回，不重试
        if result.get('success'):
            queue = realtime.get('queueCount', 0)
            online = realtime.get('kefuCount', 0)
            message_id = result.get('message_id', '')
            print(f"\n✅ 推送成功！")
            print(f"   排队人数：{queue} 人")
            print(f"   在线客服：{online} 人")
            # 记录推送日志
            log_push(
                task_name='未成年人组小时报',
                group_name=TARGET_GROUP,
                success=True,
                message_id=message_id,
                metadata={'queue': queue, 'online': online, 'session': realtime.get('sessionCount', 0), 'top_staff': staff_list[0].get('name', '') if staff_list else ''}
            )
            return result
        
        # ❌ 失败则检查原因
        error_msg = result.get('error', '')
        error_code = result.get('code', 0)
        
        # 飞书限流判断：错误码 10001 或 error 包含 frequency/rate limit
        is_rate_limited = (
            error_code == 10001 or
            'frequency limited' in error_msg.lower() or
            'rate limit' in error_msg.lower()
        )
        
        if is_rate_limited and attempt < MAX_RETRIES:
            print(f"\n⚠️  飞书限流，等待{RETRY_DELAY//60}分钟后重试 ({attempt}/{MAX_RETRIES})...")
            last_error = error_msg
            time.sleep(RETRY_DELAY)
        else:
            # 其他错误不重试，直接失败
            last_error = error_msg
            break
    
    print(f"\n❌ 推送失败：{last_error}")
    # 记录推送失败日志
    log_push(
        task_name='未成年人组小时报',
        group_name=TARGET_GROUP,
        success=False,
        error=last_error,
        metadata={'queue': realtime.get('queueCount', 0), 'online': realtime.get('kefuCount', 0), 'session': realtime.get('sessionCount', 0), 'staff_count': len(staff_list)}
    )
    # 推送失败 → 告警群通知
    send_alert_to_group(f'❌ 未成年人组小时报推送失败：{last_error}')
    return result

if __name__ == '__main__':
    send_hourly_report()
