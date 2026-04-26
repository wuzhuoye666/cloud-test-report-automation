#!/usr/bin/env python3
"""
云端测试结果下载器

功能：从云服务器下载 TB 测试结果，原样保存到本地
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime


def get_base_dir():
    """获取 skill 基础目录"""
    return Path(__file__).parent.parent


def get_download_dir():
    """获取下载目录"""
    download_dir = get_base_dir() / "data" / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


def generate_filename(vendor, spec, machine_id, date):
    """生成标准文件名"""
    return f"{vendor}_{spec}_{machine_id}_{date}.tar.gz"


def generate_download_commands(config):
    """生成下载命令"""
    ip = config["ip"]
    username = config["username"]
    password = config["password"]
    vendor = config["vendor"]
    spec = config["spec"]
    machine_id = config["machine_id"]
    remote_date = config["remote_date"]
    result_dir = config.get("result_dir", "")
    
    # 生成本地文件名
    filename = generate_filename(vendor, spec, machine_id, remote_date)
    local_path = get_download_dir() / filename
    
    commands = {
        "centos": f"""
# CentOS 下载命令
scp {username}@{ip}:/tmp/TENCENTBENCH/{remote_date}/tb_result/{result_dir}.tar.gz "{local_path}"
""",
        "ubuntu": f"""
# Ubuntu 需先远程压缩再下载
ssh {username}@{ip} "cd /tmp/TENCENTBENCH/{remote_date}/tb_result && sudo tar -czvf {result_dir}.tar.gz {result_dir}"
scp {username}@{ip}:/tmp/TENCENTBENCH/{remote_date}/tb_result/{result_dir}.tar.gz "{local_path}"
"""
    }
    
    return commands, str(local_path), filename


def print_usage():
    """打印使用说明"""
    print("""
使用方法:
    python download.py --config config.json

config.json 格式:
{
    "ip": "1.2.3.4",
    "username": "root",
    "password": "your_password",
    "vendor": "qcloud",
    "spec": "SA5",
    "machine_id": "test-001",
    "remote_date": "20260115",
    "result_dir": "result_xxx",
    "os": "centos"
}
    """)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='云端测试结果下载器')
    parser.add_argument('--config', '-c', required=True, help='配置文件路径')
    args = parser.parse_args()
    
    # 读取配置
    try:
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"错误: 无法读取配置文件 - {e}")
        sys.exit(1)
    
    # 验证必要字段
    required = ["ip", "username", "password", "vendor", "spec", "machine_id", "remote_date"]
    missing = [f for f in required if not config.get(f)]
    if missing:
        print(f"错误: 缺少必填字段: {', '.join(missing)}")
        sys.exit(1)
    
    # 生成命令
    commands, local_path, filename = generate_download_commands(config)
    
    os_type = config.get("os", "centos").lower()
    
    print("=" * 60)
    print("云端测试结果下载")
    print("=" * 60)
    print(f"\n服务器: {config['ip']}")
    print(f"厂商: {config['vendor']}")
    print(f"规格: {config['spec']}")
    print(f"日期: {config['remote_date']}")
    print(f"\n本地保存: {local_path}")
    print("\n" + "=" * 60)
    print("执行命令:")
    print("=" * 60)
    
    if os_type == "ubuntu":
        print(commands["ubuntu"])
    else:
        print(commands["centos"])
    
    print("\n提示: 如需自动执行，请确保已配置 SSH 免密登录")


if __name__ == "__main__":
    main()
