#!/usr/bin/env python3
"""
云服务器测试自动化部署执行脚本

功能：
1. SSH 连接到目标服务器
2. 上传 TB 安装包和配置文件
3. 自动修改配置参数
4. 解压安装并执行测试
5. 监控测试进度

用法：
    python deploy_and_run.py --config machines.json
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# 厂商配置映射
VENDOR_MAP = {
    "腾讯云": "qcloud",
    "火山云": "volcengine",
    "百度云": "bdcloud",
    "金山云": "jscloud",
    "阿里云": "aliyun",
    "华为云": "huaweiyun",
    "微软云": "azure",
    "亚马逊云": "aws",
    "谷歌云": "gcp"
}

# 地域代码映射
AREA_MAP = {
    "广州": "gz",
    "上海": "sh",
    "北京": "bj",
    "南京": "nj",
    "成都": "cd",
    "香港": "hk",
    "新加坡": "sg",
    "硅谷": "usw"
}

# 系统类型映射
OS_CASE_MAP = {
    "centos": "benchmark.compet_single_centos",
    "ubuntu": "benchmark.compet_single"
}


def get_skill_base_dir():
    """获取 skill 基础目录"""
    return Path(__file__).parent.parent


def get_assets_dir():
    """获取 assets 目录路径"""
    return get_skill_base_dir() / "assets"


def validate_machine_config(machine):
    """验证机器配置是否完整"""
    required_fields = ["id", "vendor", "spec", "ip", "username", "password", "os"]
    missing = [f for f in required_fields if not machine.get(f)]
    if missing:
        return False, f"缺少必填字段: {', '.join(missing)}"
    
    # 验证 vendor
    valid_vendors = list(VENDOR_MAP.values()) + list(VENDOR_MAP.keys())
    if machine["vendor"] not in valid_vendors:
        return False, f"不支持的厂商: {machine['vendor']}"
    
    # 验证 os
    if machine["os"].lower() not in ["centos", "ubuntu"]:
        return False, f"不支持的操作系统: {machine['os']}"
    
    return True, "配置有效"


def normalize_vendor(vendor):
    """标准化厂商名称"""
    vendor = vendor.lower()
    if vendor in VENDOR_MAP.values():
        return vendor
    for cn, en in VENDOR_MAP.items():
        if cn in vendor:
            return en
    return vendor


def get_remote_path(os_type):
    """根据系统类型获取远程路径"""
    os_type = os_type.lower()
    if os_type == "centos":
        return "/root"
    elif os_type == "ubuntu":
        return "/home/ubuntu"
    return "/tmp"


def get_tb_package_name():
    """获取 TB 安装包文件名"""
    assets_dir = get_assets_dir()
    tb_files = list(assets_dir.glob("TencentBench-*.tar.gz"))
    if tb_files:
        return tb_files[0].name
    return "TencentBench-2.2.1a24.tar.gz"


def generate_ssh_commands(machine):
    """生成 SSH 操作命令序列"""
    vendor = normalize_vendor(machine["vendor"])
    spec = machine["spec"]
    area = machine.get("area", "gz")
    
    # 转换地域为代码
    if area in AREA_MAP:
        area = AREA_MAP[area]
    
    remote_path = get_remote_path(machine["os"])
    tb_package = get_tb_package_name()
    
    commands = {
        "upload_files": f"""
# 上传文件到服务器
scp {get_assets_dir()}/{tb_package} {machine['username']}@{machine['ip']}:{remote_path}/
scp {get_assets_dir()}/default.cfg {machine['username']}@{machine['ip']}:{remote_path}/
""",
        
        "modify_config": f"""
# 修改配置文件
# 注意：default.cfg 结构：[product] 下有 sold_type=, vendor=, username=, password=, port=；[role] 下有 area=
ssh {machine['username']}@{machine['ip']} "cd {remote_path} && sed -i 's/^sold_type = .*/sold_type = \"{spec}\"/' default.cfg"
ssh {machine['username']}@{machine['ip']} "cd {remote_path} && sed -i 's/^vendor = .*/vendor = \"{vendor}\"/' default.cfg"
ssh {machine['username']}@{machine['ip']} "cd {remote_path} && sed -i 's/^area = .*/area = \"{area}\"/' default.cfg"
ssh {machine['username']}@{machine['ip']} "cd {remote_path} && sed -i 's/^username = .*/username = \"{machine['username']}\"/' default.cfg"
""",
        
        "install_tb": f"""
# 解压并安装 TB
ssh {machine['username']}@{machine['ip']} "cd {remote_path} && tar -xzvf {tb_package}"
ssh {machine['username']}@{machine['ip']} "cd {remote_path}/{tb_package.replace('.tar.gz', '')} && sudo ./install.sh"
""",
        
        "run_test": f"""
# 执行测试
ssh {machine['username']}@{machine['ip']} "cd {remote_path} && setsid tb-runner --cfg {remote_path}/default.cfg --no-color --run {OS_CASE_MAP[machine['os'].lower()]} > runtb.log 2>&1 &"
""",
        
        "monitor": f"""
# 监控测试进度
ssh {machine['username']}@{machine['ip']} "sudo tail -f {remote_path}/runtb.log"
""",
        
        "check_result": f"""
# 检查结果
ssh {machine['username']}@{machine['ip']} "ls -la /tmp/TENCENTBENCH/"
"""
    }
    
    return commands


def print_deployment_plan(machines):
    """打印部署计划"""
    print("=" * 60)
    print("云服务器测试部署计划")
    print("=" * 60)
    
    for i, machine in enumerate(machines, 1):
        print(f"\n【机器 {i}】")
        print(f"  ID: {machine['id']}")
        print(f"  厂商: {machine['vendor']}")
        print(f"  规格: {machine['spec']}")
        print(f"  IP: {machine['ip']}")
        print(f"  系统: {machine['os']}")
        print(f"  地域: {machine.get('area', 'gz')}")
    
    print("\n" + "=" * 60)


def print_execution_guide(machine):
    """打印单个机器的执行指南"""
    print(f"\n{'='*60}")
    print(f"执行指南 - {machine['id']} ({machine['spec']})")
    print(f"{'='*60}")
    
    commands = generate_ssh_commands(machine)
    
    print("\n【步骤 1: 上传文件】")
    print(commands["upload_files"])
    
    print("\n【步骤 2: 修改配置】")
    print(commands["modify_config"])
    
    print("\n【步骤 3: 安装 TB】")
    print(commands["install_tb"])
    
    print("\n【步骤 4: 执行测试】")
    print(commands["run_test"])
    
    print("\n【步骤 5: 监控进度】")
    print(commands["monitor"])
    
    print("\n【步骤 6: 收集结果】")
    print(commands["check_result"])


def main():
    parser = argparse.ArgumentParser(description='云服务器测试自动化部署')
    parser.add_argument('--config', '-c', required=True, help='机器配置文件(JSON格式)')
    parser.add_argument('--dry-run', '-d', action='store_true', help='仅打印执行计划，不实际执行')
    args = parser.parse_args()
    
    # 读取配置
    try:
        with open(args.config, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"错误: 无法读取配置文件 - {e}")
        sys.exit(1)
    
    machines = config.get('machines', [])
    if not machines:
        print("错误: 配置文件中未找到 machines 列表")
        sys.exit(1)
    
    # 验证配置
    print("\n正在验证机器配置...")
    for i, machine in enumerate(machines):
        valid, msg = validate_machine_config(machine)
        if not valid:
            print(f"错误 [机器 {i+1}]: {msg}")
            sys.exit(1)
        print(f"✓ 机器 {i+1} ({machine['id']}) 配置有效")
    
    # 打印部署计划
    print_deployment_plan(machines)
    
    if args.dry_run:
        print("\n【干运行模式 - 仅显示执行指南】")
        for machine in machines:
            print_execution_guide(machine)
    else:
        print("\n请根据以下指南手动执行各步骤：")
        for machine in machines:
            print_execution_guide(machine)
    
    print("\n" + "=" * 60)
    print("提示：")
    print("1. 确保本地已安装 scp 和 ssh 命令")
    print("2. 测试执行后使用 'tail -f runtb.log' 监控进度")
    print("3. 测试结果保存在 /tmp/TENCENTBENCH/ 目录")
    print("=" * 60)


if __name__ == "__main__":
    main()
