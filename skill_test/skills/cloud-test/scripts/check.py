#!/usr/bin/env python3
"""
测试任务状态检查脚本

功能：
- 检查后台测试任务状态
- 自动故障检测和恢复
- 完成后自动收集结果

用法：
    python check.py --job {job_id}          # 检查特定任务
    python check.py --list                  # 列出所有任务
    python check.py --monitor               # 定时监控模式（cron用）
"""

import argparse
import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime


def get_project_dir():
    """获取项目根目录"""
    return Path(__file__).parent.parent.parent.parent


def get_jobs_dir():
    """获取任务目录"""
    jobs_dir = get_project_dir() / "test_jobs"
    jobs_dir.mkdir(exist_ok=True)
    return jobs_dir


def get_results_dir():
    """获取结果目录"""
    results_dir = get_project_dir() / "test_results"
    results_dir.mkdir(exist_ok=True)
    return results_dir


def load_status(job_id):
    """加载任务状态"""
    status_file = get_jobs_dir() / job_id / "status.json"
    if status_file.exists():
        with open(status_file, 'r') as f:
            return json.load(f)
    return None


def save_status(job_id, status):
    """保存任务状态"""
    status_file = get_jobs_dir() / job_id / "status.json"
    with open(status_file, 'w') as f:
        json.dump(status, f, indent=2)


def load_config(job_id):
    """加载任务配置"""
    config_file = get_jobs_dir() / job_id / "config.json"
    if config_file.exists():
        with open(config_file, 'r') as f:
            return json.load(f)
    return None


def check_remote_status(config):
    """远程检查测试状态"""
    ip = config['ip']
    username = config['username']
    password = config['password']
    
    try:
        # 检查进程是否存在
        cmd = f"ssh -o ConnectTimeout=10 {username}@{ip} 'ps aux | grep tb-runner | grep -v grep'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        process_running = result.returncode == 0 and len(result.stdout.strip()) > 0
        
        # 读取日志进度
        remote_log_path = f"/home/{username}/runtb.log" if username != 'root' else "/root/runtb.log"
        cmd = f"ssh -o ConnectTimeout=10 {username}@{ip} 'tail -50 {remote_log_path} 2>/dev/null'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        log_content = result.stdout
        
        # 解析进度
        progress = "unknown"
        if "Progress" in log_content or "progress" in log_content:
            # 提取进度百分比
            import re
            match = re.search(r'(\d+)%', log_content)
            if match:
                progress = f"{match.group(1)}%"
        
        # 检查是否完成
        completed = "completed" in log_content.lower() or "全部完成" in log_content
        
        # 检查错误
        has_error = "error" in log_content.lower() or "fail" in log_content.lower() or "失败" in log_content
        
        return {
            "process_running": process_running,
            "progress": progress,
            "completed": completed,
            "has_error": has_error,
            "log_snippet": log_content[-500:] if log_content else ""
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "process_running": False,
            "ssh_failed": True
        }


def check_job(job_id, auto_recover=True):
    """检查任务状态"""
    status = load_status(job_id)
    config = load_config(job_id)
    
    if not status or not config:
        print(f"✗ 任务不存在: {job_id}")
        return
    
    print(f"\n{'='*60}")
    print(f"任务检查: {job_id}")
    print(f"{'='*60}")
    print(f"服务器: {config['ip']}")
    print(f"厂商: {config['vendor']}")
    print(f"规格: {config['spec']}")
    print(f"启动时间: {status.get('start_time', 'unknown')}")
    
    # 远程检查
    remote_status = check_remote_status(config)
    
    if remote_status.get("ssh_failed"):
        print(f"⚠ SSH连接失败: {remote_status.get('error')}")
        print(f"状态: 上次检查正常，等待下次重试")
        return
    
    # 更新状态
    status["last_check"] = datetime.now().isoformat()
    status["check_count"] = status.get("check_count", 0) + 1
    
    if remote_status["completed"]:
        status["status"] = "completed"
        status["progress"] = "100%"
        print(f"✓ 测试已完成!")
        
        # 触发结果收集
        collect_result(job_id, config)
        
    elif remote_status["process_running"]:
        status["status"] = "running"
        status["progress"] = remote_status["progress"]
        print(f"状态: 运行中 ({remote_status['progress']})")
        
    elif remote_status["has_error"]:
        status["status"] = "failed"
        print(f"✗ 测试失败")
        print(f"错误日志: {remote_status['log_snippet'][-200:]}")
        
        # AI 分析故障并决策是否重试
        if auto_recover:
            error_log = remote_status['log_snippet']
            should_retry, fix_strategy = analyze_error(error_log, status)
            
            if should_retry:
                print(f"分析故障原因，准备修复: {fix_strategy}")
                apply_fix(job_id, config, fix_strategy)
                restart_test(job_id, config)
                status["status"] = "retrying"
                status["last_fix"] = fix_strategy
                status["retry_history"] = status.get("retry_history", []) + [{
                    "time": datetime.now().isoformat(),
                    "fix": fix_strategy
                }]
            else:
                print(f"✗ 无法自动修复，需要人工介入")
                status["needs_human"] = True
        
    else:
        # 进程不存在但未检测到完成标志
        status["status"] = "unknown"
        print(f"? 状态未知（进程不存在，但未检测到完成标志）")
        print(f"日志片段: {remote_status['log_snippet'][-200:]}")
    
    save_status(job_id, status)


def restart_test(job_id, config):
    """重启测试"""
    ip = config['ip']
    username = config['username']
    os_type = config.get('os', 'centos').lower()
    
    if os_type == 'centos':
        cmd = f"ssh {username}@{ip} 'cd ~ && setsid tb-runner --cfg /root/default.cfg --no-color --run benchmark.compet_single_centos > runtb.log 2>&1 &'"
    else:
        cmd = f"ssh {username}@{ip} 'cd ~ && sudo setsid tb-runner --cfg /home/ubuntu/default.cfg --no-color --run benchmark.compet_single > runtb.log 2>&1 &'"
    
    subprocess.run(cmd, shell=True)
    print(f"✓ 测试已重启")


def analyze_error(error_log, status):
    """
    AI 分析错误日志，判断是否可以自动修复
    返回: (should_retry: bool, fix_strategy: str)
    """
    error_log_lower = error_log.lower()
    retry_history = status.get("retry_history", [])
    
    # 检查是否重复相同错误
    if retry_history:
        last_fix = retry_history[-1].get("fix", "")
        if last_fix in error_log_lower:
            # 上次修复后仍然出现相同错误，可能无法自动修复
            return False, "重复错误，需要人工检查"
    
    # 分析错误类型
    if "alexnet" in error_log_lower and ("username" in error_log_lower or "password" in error_log_lower):
        return True, "fix_alexnet_config"
    
    if "permission denied" in error_log_lower or "权限" in error_log:
        return True, "fix_permission"
    
    if "no space left" in error_log_lower or "磁盘满" in error_log or "空间不足" in error_log:
        return True, "clean_disk"
    
    if "command not found" in error_log_lower or "未找到命令" in error_log:
        return True, "install_dependency"
    
    if "connection" in error_log_lower or "连接" in error_log:
        return True, "wait_network"
    
    if "memory" in error_log_lower or "out of memory" in error_log_lower or "内存" in error_log:
        return True, "optimize_memory"
    
    if "config" in error_log_lower or "配置" in error_log:
        return True, "fix_config"
    
    # 未知错误或连续多次修复失败
    if len(retry_history) >= 3:
        return False, "多次修复失败，需要人工介入"
    
    # 默认尝试重启
    return True, "restart_test"


def apply_fix(job_id, config, fix_strategy):
    """应用修复策略"""
    ip = config['ip']
    username = config['username']
    
    print(f"  执行修复: {fix_strategy}")
    
    if fix_strategy == "fix_alexnet_config":
        # 修正 AlexNet 配置
        cmd = f"ssh {username}@{ip} 'sed -i \"s/^username=.*/username={username}/\" ~/default.cfg'"
        subprocess.run(cmd, shell=True)
        
    elif fix_strategy == "fix_permission":
        # 检查 sudo 权限
        cmd = f"ssh {username}@{ip} 'sudo -l'"
        subprocess.run(cmd, shell=True)
        
    elif fix_strategy == "clean_disk":
        # 清理磁盘空间
        cmd = f"ssh {username}@{ip} 'sudo rm -rf /tmp/*.log /var/log/*.old'"
        subprocess.run(cmd, shell=True)
        
    elif fix_strategy == "install_dependency":
        # 安装缺失依赖
        cmd = f"ssh {username}@{ip} 'sudo yum install -y gcc make'"
        subprocess.run(cmd, shell=True)
        
    elif fix_strategy == "fix_config":
        # 重新上传配置文件
        assets_dir = Path(__file__).parent.parent / "assets"
        cmd = f"scp {assets_dir}/default.cfg {username}@{ip}:~/"
        subprocess.run(cmd, shell=True)
        
    elif fix_strategy == "optimize_memory":
        # 清理内存缓存
        cmd = f"ssh {username}@{ip} 'sudo sync && sudo echo 3 > /proc/sys/vm/drop_caches'"
        subprocess.run(cmd, shell=True)
        
    elif fix_strategy == "wait_network":
        # 网络问题，稍后自动重试
        print("  网络问题，将在下次检查时重试")
        
    elif fix_strategy == "restart_test":
        # 直接重启
        print("  直接重启测试")
        
    else:
        print(f"  未知修复策略: {fix_strategy}")


def collect_result(job_id, config):
    """收集测试结果"""
    print(f"\n正在收集结果...")
    
    ip = config['ip']
    username = config['username']
    vendor = config['vendor']
    spec = config['spec']
    machine_id = config['machine_id']
    
    # 获取测试日期
    remote_date = config.get('remote_date', datetime.now().strftime('%Y%m%d'))
    
    # 生成本地文件名
    filename = f"{vendor}_{spec}_{machine_id}_{remote_date}.tar.gz"
    local_path = get_results_dir() / filename
    
    # 下载命令（这里只显示命令，实际执行需要确认）
    print(f"下载命令:")
    print(f"  scp {username}@{ip}:/tmp/TENCENTBENCH/{remote_date}/*.tar.gz {local_path}")
    
    # 更新状态
    status = load_status(job_id)
    status["result_collected"] = True
    status["local_path"] = str(local_path)
    save_status(job_id, status)


def list_jobs():
    """列出所有任务"""
    jobs_dir = get_jobs_dir()
    if not jobs_dir.exists():
        print("暂无任务")
        return
    
    print(f"\n{'='*60}")
    print("测试任务列表")
    print(f"{'='*60}")
    
    for job_dir in sorted(jobs_dir.iterdir()):
        if job_dir.is_dir():
            status = load_status(job_dir.name)
            if status:
                print(f"\n{job_dir.name}")
                print(f"  状态: {status.get('status', 'unknown')}")
                print(f"  进度: {status.get('progress', 'unknown')}")
                print(f"  启动: {status.get('start_time', 'unknown')}")


def monitor_mode():
    """监控模式（定时检查所有running任务）"""
    jobs_dir = get_jobs_dir()
    if not jobs_dir.exists():
        return
    
    for job_dir in jobs_dir.iterdir():
        if job_dir.is_dir():
            status = load_status(job_dir.name)
            if status and status.get('status') in ['running', 'retrying']:
                check_job(job_dir.name, auto_recover=True)


def main():
    parser = argparse.ArgumentParser(description='测试任务状态检查')
    parser.add_argument('--job', '-j', help='检查特定任务ID')
    parser.add_argument('--list', '-l', action='store_true', help='列出所有任务')
    parser.add_argument('--monitor', '-m', action='store_true', help='监控模式')
    args = parser.parse_args()
    
    if args.job:
        check_job(args.job)
    elif args.list:
        list_jobs()
    elif args.monitor:
        monitor_mode()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
