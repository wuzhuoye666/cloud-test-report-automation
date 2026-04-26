#!/usr/bin/env python3
"""
云服务器连接测试 & TB 部署脚本（支持所有厂商）

功能：
1. 验证 SSH 连接是否可达
2. 检查服务器基本信息（OS、磁盘、内存）
3. 自动处理部署过程中的各种兼容性问题
4. 一键执行完整测试流程

已处理的坑：
- Ubuntu 24.04 PEP668 限制 pip install（自动加 --break-system-packages）
- install.sh 失败后回退手动安装（pip3 install + 软链接）
- Ubuntu 系统无 ubuntu 用户导致 tb-runner 报错（自动创建）
- TOML 配置中密码含特殊字符(#等)需用双引号包裹
- root 用户在 Ubuntu 上的 home 目录是 /root 不是 /home/ubuntu
- paramiko 后台命令超时（使用 nohup + 短超时）
- tb-runner 未加入 PATH（自动创建 /usr/local/bin 软链接）

用法：
    # 命令行直接传入机器信息
    python test_connect.py --ip 120.48.51.127 --user root --password "Wzy666##" --vendor bdcloud --spec bcc.e1.c2m2 --check
    python test_connect.py --ip 120.48.51.127 --user root --password "Wzy666##" --vendor bdcloud --spec bcc.e1.c2m2 --deploy
    python test_connect.py --ip 120.48.51.127 --user root --password "Wzy666##" --vendor bdcloud --spec bcc.e1.c2m2 --full

    # 使用配置文件
    python test_connect.py --config test_baidu_ksyun.json --check
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import paramiko


# ============== 常量 ==============

VENDOR_INFO = {
    "qcloud":     {"cn": "腾讯云", "default_area": "gz", "default_spec": "SA5"},
    "volcengine": {"cn": "火山云", "default_area": "bj", "default_spec": "ecs.g3i.xlarge"},
    "bdcloud":    {"cn": "百度云", "default_area": "bj", "default_spec": "bcc.e1.c2m2"},
    "jscloud":    {"cn": "金山云", "default_area": "bj", "default_spec": "km.gn6i.xlarge"},
    "aliyun":     {"cn": "阿里云", "default_area": "hz", "default_spec": "ecs.g8a.8xlarge"},
    "huaweiyun":  {"cn": "华为云", "default_area": "bj", "default_spec": "c7.xlarge.2"},
    "azure":      {"cn": "微软云", "default_area": "sh", "default_spec": "Standard_D4s_v5"},
    "aws":        {"cn": "亚马逊云", "default_area": "usw", "default_spec": "m6i.xlarge"},
    "gcp":        {"cn": "谷歌云", "default_area": "usw", "default_spec": "n2-standard-4"},
}


def get_skill_base_dir():
    return Path(__file__).parent.parent


def get_assets_dir():
    return get_skill_base_dir() / "assets"


# ============== SSH/SFTP 工具函数 ==============

def create_ssh_client(ip, username, password, port=22, timeout=10):
    """创建 SSH 连接"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(ip, port=port, username=username, password=password, timeout=timeout)
        return client
    except Exception as e:
        print(f"  ✗ SSH 连接失败: {e}")
        return None


def ssh_exec(client, cmd, timeout=60):
    """执行 SSH 命令，返回 (exit_code, stdout, stderr)
    注意：对后台命令（含 & 或 nohup）使用短超时避免卡死"""
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode('utf-8', errors='replace').strip()
        err = stderr.read().decode('utf-8', errors='replace').strip()
        return exit_code, out, err
    except Exception as e:
        return -1, "", str(e)


def ssh_exec_background(client, cmd):
    """执行后台 SSH 命令（含 nohup/&），避免 paramiko 超时卡死
    使用短超时 + 忽略读取异常的方式"""
    full_cmd = f"{cmd} & disown"
    try:
        client.exec_command(full_cmd, timeout=3)
        # 不等返回，直接认为已提交
        return 0, "submitted", ""
    except Exception:
        # 后台命令超时是正常的
        return 0, "submitted", ""


def sftp_upload(client, local_path, remote_path):
    """通过 SFTP 上传文件"""
    sftp = client.open_sftp()
    try:
        sftp.put(local_path, remote_path)
        return True
    except Exception as e:
        print(f"  ✗ SFTP 上传失败: {e}")
        return False
    finally:
        sftp.close()


def sftp_download(client, remote_path, local_path):
    """通过 SFTP 下载文件"""
    sftp = client.open_sftp()
    try:
        sftp.get(remote_path, local_path)
        return True
    except Exception as e:
        print(f"  ✗ SFTP 下载失败: {e}")
        return False
    finally:
        sftp.close()


# ============== 检查函数 ==============

def check_prerequisites():
    """检查本地前置依赖"""
    print("\n" + "=" * 60)
    print("【前置检查】本地环境")
    print("=" * 60)

    checks = []

    try:
        import paramiko
        print(f"  ✓ paramiko ({paramiko.__version__})")
        checks.append(True)
    except ImportError:
        print("  ✗ paramiko 未安装！pip install paramiko")
        checks.append(False)

    assets_dir = get_assets_dir()
    tb_files = list(assets_dir.glob("TencentBench-*.tar.gz"))
    if tb_files:
        size_mb = tb_files[0].stat().st_size / (1024 * 1024)
        print(f"  ✓ TB 安装包: {tb_files[0].name} ({size_mb:.1f}MB)")
        checks.append(True)
    else:
        print("  ✗ 未找到 TB 安装包 (assets/TencentBench-*.tar.gz)")
        checks.append(False)

    cfg_file = assets_dir / "default.cfg"
    if cfg_file.exists():
        print("  ✓ 配置文件: default.cfg")
        checks.append(True)
    else:
        print("  ✗ 未找到 default.cfg")
        checks.append(False)

    return all(checks)


def check_ssh_connection(machine):
    """测试 SSH 连接"""
    vendor = machine["vendor"]
    info = VENDOR_INFO.get(vendor, {"cn": vendor})
    print(f"\n{'='*60}")
    print(f"【SSH 连接测试】{info['cn']} - {machine['ip']}")
    print("=" * 60)

    client = create_ssh_client(
        machine["ip"], machine["username"], machine["password"],
        port=machine.get("port", 22)
    )
    if client is None:
        return False

    rc, stdout, stderr = ssh_exec(client, "echo 'SSH_OK'")
    client.close()

    if rc == 0 and "SSH_OK" in stdout:
        print("  ✓ SSH 连接成功")
        return True
    else:
        print(f"  ✗ SSH 连接失败: {stderr}")
        return False


def check_server_env(machine):
    """检查服务器环境"""
    vendor = machine["vendor"]
    info = VENDOR_INFO.get(vendor, {"cn": vendor})
    print(f"\n{'='*60}")
    print(f"【服务器环境检查】{info['cn']} - {machine['ip']}")
    print("=" * 60)

    client = create_ssh_client(
        machine["ip"], machine["username"], machine["password"],
        port=machine.get("port", 22)
    )
    if client is None:
        return False

    checks = []

    # 操作系统
    rc, stdout, _ = ssh_exec(client, "cat /etc/os-release | head -3")
    if rc == 0:
        first_line = stdout.split("\n")[0]
        print(f"  操作系统: {first_line}")
    else:
        print("  操作系统: 无法获取")

    # CPU
    rc, stdout, _ = ssh_exec(client, "lscpu | grep 'Model name' | head -1")
    if rc == 0 and stdout:
        print(f"  CPU: {stdout}")

    # 内存
    rc, stdout, _ = ssh_exec(client, "free -h | grep Mem")
    if rc == 0:
        print(f"  内存: {stdout}")

    # 磁盘
    rc, stdout, _ = ssh_exec(client, "df -h / | tail -1")
    if rc == 0:
        print(f"  磁盘: {stdout}")

    # sudo
    rc, stdout, _ = ssh_exec(client, "sudo -n echo 'SUDO_OK' 2>/dev/null || echo 'SUDO_NEED_PASSWORD'")
    if rc == 0:
        if "SUDO_OK" in stdout:
            print("  ✓ sudo 权限: 免密")
            checks.append(True)
        else:
            print("  ⚠ sudo 权限: 需要密码")
            checks.append(True)
    else:
        print("  ✗ sudo 权限: 无")
        checks.append(False)

    # tb-runner
    rc, stdout, _ = ssh_exec(client, "which tb-runner 2>/dev/null || echo 'NOT_FOUND'")
    if "NOT_FOUND" in stdout:
        print("  tb-runner: 未安装（需要部署）")
    else:
        print(f"  tb-runner: 已安装 ({stdout})")

    # 运行中的测试
    rc, stdout, _ = ssh_exec(client, "ps aux | grep tb-runner | grep -v grep || echo 'NO_RUNNING_TEST'")
    if "NO_RUNNING_TEST" in stdout:
        print("  测试进程: 无运行中的测试")
    else:
        print("  ⚠ 测试进程: 已有测试在运行！")
        print(f"    {stdout}")

    client.close()
    return all(checks)


# ============== 部署函数 ==============

def _get_remote_path(username):
    """根据用户名确定远程 home 目录"""
    if username == "root":
        return "/root"
    else:
        return f"/home/{username}"


def _fix_ubuntu_user(client):
    """坑1: Ubuntu 系统可能没有 ubuntu 用户，tb-runner 会用 sudo su ubuntu 执行命令
    如果系统没有 ubuntu 用户就会报错，需要提前创建"""
    rc, stdout, _ = ssh_exec(client, "id ubuntu 2>/dev/null && echo EXISTS || echo NOT_EXISTS")
    if "EXISTS" in stdout:
        print("    ubuntu 用户已存在")
        return

    print("    创建 ubuntu 用户...")
    ssh_exec(client, "useradd -m -s /bin/bash ubuntu")
    # 设置 sudo 免密
    ssh_exec(client, 'echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu')
    ssh_exec(client, "chmod 440 /etc/sudoers.d/ubuntu")

    # 验证
    rc, stdout, _ = ssh_exec(client, "id ubuntu 2>/dev/null && echo OK || echo FAIL")
    if "OK" in stdout:
        print("    ✓ ubuntu 用户创建成功（sudo 免密）")
    else:
        print("    ⚠ ubuntu 用户创建失败，测试可能会报错")


def _install_tb_packages(client, remote_path, tb_dir):
    """坑2: Ubuntu 24.04 有 PEP668 限制，install.sh 的 pip install 会失败
    回退方案：手动 pip3 install --break-system-packages + 创建软链接"""
    # 先尝试正常 install.sh
    print("    执行 install.sh...")
    rc, stdout, stderr = ssh_exec(client,
        f"cd {remote_path}/{tb_dir} && sudo ./install.sh", timeout=300)

    if rc == 0:
        print("    ✓ install.sh 执行成功")
    else:
        err_lower = stderr.lower()
        if "externally-managed" in err_lower or "pep668" in err_lower or "managed-environment" in err_lower:
            # 坑2: PEP668 限制，使用 --break-system-packages
            print("    ⚠ install.sh 失败（PEP668 限制），使用回退方案...")
            print("    执行 pip3 install --break-system-packages ...")
            rc2, _, err2 = ssh_exec(client,
                f"cd {remote_path}/{tb_dir} && pip3 install . --break-system-packages 2>&1",
                timeout=300)
            if rc2 == 0:
                print("    ✓ pip3 install 成功")
            else:
                print(f"    ✗ pip3 install 也失败: {err2[:200]}")
                return False
        else:
            print(f"    ⚠ install.sh 返回非0 (rc={rc}): {stderr[:200]}")
            print("    尝试继续...")

    # 确保 tb-runner 在 PATH 中
    print("    创建 tb-runner 软链接...")
    ssh_exec(client, f"chmod +x {remote_path}/{tb_dir}/bin/*")
    ssh_exec(client, f"ln -sf {remote_path}/{tb_dir}/bin/tb-runner /usr/local/bin/tb-runner")
    ssh_exec(client, f"ln -sf {remote_path}/{tb_dir}/bin/tb /usr/local/bin/tb")

    # 验证
    rc, stdout, _ = ssh_exec(client, "tb-runner --version 2>&1 | head -3")
    if rc == 0 and stdout:
        print(f"    ✓ tb-runner 已就绪: {stdout}")
        return True
    else:
        print(f"    ⚠ tb-runner 验证异常: {stdout}")
        # 再试一次直接执行
        rc2, stdout2, _ = ssh_exec(client, f"{remote_path}/{tb_dir}/bin/tb-runner --version 2>&1 | head -3")
        if rc2 == 0 and stdout2:
            print(f"    ✓ tb-runner 可直接执行: {stdout2}")
            return True
        return False


def _fix_config_password(client, remote_path, password):
    """坑3: TOML 配置中 password 如果含 # 等特殊字符，必须用双引号包裹
    sed 命令在多层转义下容易丢引号，改用 Python 远程修改更可靠"""
    fix_script = f'''python3 -c "
import sys
with open('{remote_path}/default.cfg', 'r') as f:
    content = f.read()
# 确保 password 值被双引号包裹
import re
content = re.sub(r'^password\\s*=\\s*(.+)$', 'password = \\\"{password}\\\"', content, flags=re.MULTILINE)
with open('{remote_path}/default.cfg', 'w') as f:
    f.write(content)
print('OK')
"'''
    rc, stdout, _ = ssh_exec(client, fix_script)
    return rc == 0 and "OK" in stdout


def _detect_os(client):
    """自动检测远程操作系统类型，返回 (os_type, os_name)
    os_type: 'centos' 或 'ubuntu'
    os_name: 完整发行版名称"""
    rc, stdout, _ = ssh_exec(client, "cat /etc/os-release")
    if rc != 0:
        return "centos", "unknown"

    os_name = "unknown"
    os_type = "centos"

    for line in stdout.split("\n"):
        if line.startswith("PRETTY_NAME="):
            os_name = line.split("=", 1)[1].strip('"')
        if line.startswith("ID="):
            distro_id = line.split("=", 1)[1].strip('"').lower()
            if distro_id in ("ubuntu", "debian"):
                os_type = "ubuntu"
            elif distro_id in ("centos", "rhel", "fedora", "tlinux", "rocky", "alma"):
                os_type = "centos"

    return os_type, os_name


def deploy_and_test(machine):
    """部署 TB 并执行测试（完整流程，含所有坑的处理）"""
    vendor = machine["vendor"]
    info = VENDOR_INFO.get(vendor, {"cn": vendor})
    spec = machine["spec"]
    area = machine.get("area", "bj")
    username = machine["username"]
    ip = machine["ip"]
    password = machine["password"]

    print(f"\n{'='*60}")
    print(f"【部署并测试】{info['cn']} - {spec} - {ip}")
    print("=" * 60)

    client = create_ssh_client(ip, username, password, port=machine.get("port", 22))
    if client is None:
        return False

    # 自动检测操作系统（不依赖用户传入的 --os）
    os_type, os_name = _detect_os(client)
    print(f"  检测到操作系统: {os_name} (类型: {os_type})")

    # 远程路径：以实际用户名为准
    remote_path = _get_remote_path(username)
    test_case = "benchmark.compet_single_centos" if os_type == "centos" else "benchmark.compet_single"
    print(f"  远程路径: {remote_path}")
    print(f"  测试用例: {test_case}")

    assets_dir = get_assets_dir()
    tb_files = list(assets_dir.glob("TencentBench-*.tar.gz"))
    if not tb_files:
        print("  ✗ 未找到 TB 安装包，终止部署")
        client.close()
        return False

    tb_package = tb_files[0].name
    tb_dir = tb_package.replace(".tar.gz", "")

    # ---- Step 1: 上传 TB 安装包 ----
    print(f"\n  [Step 1/7] 上传 TB 安装包...")
    local_tb = str(assets_dir / tb_package)
    size_mb = os.path.getsize(local_tb) / (1024 * 1024)
    print(f"  上传 {tb_package} ({size_mb:.1f}MB) -> {remote_path}/")
    if not sftp_upload(client, local_tb, f"{remote_path}/{tb_package}"):
        client.close()
        return False
    print("  ✓ 上传成功")

    # ---- Step 2: 上传配置文件 ----
    print(f"\n  [Step 2/7] 上传并修改配置文件...")
    local_cfg = str(assets_dir / "default.cfg")
    if not sftp_upload(client, local_cfg, f"{remote_path}/default.cfg"):
        client.close()
        return False
    print("  ✓ default.cfg 上传成功")

    # 修改配置参数（用 Python 远程修改，避免 sed 转义问题）
    print("  修改配置参数...")
    config_fix_script = f"""python3 -c "
with open('{remote_path}/default.cfg', 'r') as f:
    content = f.read()
import re
content = re.sub(r'^sold_type\\s*=\\s.*$', 'sold_type = \\\"{spec}\\\"', content, flags=re.MULTILINE)
content = re.sub(r'^vendor\\s*=\\s.*$', 'vendor = \\\"{vendor}\\\"', content, flags=re.MULTILINE)
content = re.sub(r'^area\\s*=\\s.*$', 'area = \\\"{area}\\\"', content, flags=re.MULTILINE)
content = re.sub(r'^username\\s*=\\s.*$', 'username = \\\"{username}\\\"', content, flags=re.MULTILINE)
content = re.sub(r'^password\\s*=\\s.*$', 'password = \\\"{password}\\\"', content, flags=re.MULTILINE)
with open('{remote_path}/default.cfg', 'w') as f:
    f.write(content)
print('OK')
" """
    rc, stdout, _ = ssh_exec(client, config_fix_script)
    if rc == 0 and "OK" in stdout:
        print(f"  ✓ 配置修改完成 (vendor={vendor}, spec={spec}, area={area})")
    else:
        # 回退到 sed
        print("  ⚠ Python 修改失败，回退 sed...")
        ssh_exec(client, f"sed -i 's/^sold_type = .*/sold_type = \"{spec}\"/' {remote_path}/default.cfg")
        ssh_exec(client, f"sed -i 's/^vendor = .*/vendor = \"{vendor}\"/' {remote_path}/default.cfg")
        ssh_exec(client, f"sed -i 's/^area = .*/area = \"{area}\"/' {remote_path}/default.cfg")
        ssh_exec(client, f"sed -i 's/^username = .*/username = \"{username}\"/' {remote_path}/default.cfg")
        _fix_config_password(client, remote_path, password)

    # 验证配置
    rc, stdout, _ = ssh_exec(client,
        f"grep -E 'sold_type|vendor|area|username|password' {remote_path}/default.cfg | head -6")
    print("  配置验证:")
    for line in stdout.split("\n"):
        print(f"    {line}")

    # ---- Step 3: 解压安装 ----
    print(f"\n  [Step 3/7] 解压安装 TB...")
    rc, _, stderr = ssh_exec(client, f"cd {remote_path} && tar -xzf {tb_package}", timeout=120)
    if rc != 0:
        print(f"  ✗ 解压失败: {stderr}")
        client.close()
        return False
    print("  ✓ 解压成功")

    # 安装（含 PEP668 回退）
    if not _install_tb_packages(client, remote_path, tb_dir):
        print("  ✗ TB 安装失败，终止部署")
        client.close()
        return False

    # ---- Step 4: Ubuntu 系统创建 ubuntu 用户 ----
    print(f"\n  [Step 4/7] 环境修复...")
    if os_type == "ubuntu":
        _fix_ubuntu_user(client)
    else:
        print("    CentOS 系统，跳过 ubuntu 用户检查")

    # ---- Step 5: 启动测试 ----
    print(f"\n  [Step 5/7] 启动测试 ({test_case})...")

    # 清理旧日志
    ssh_exec(client, f"rm -f {remote_path}/runtb.log")

    if username == "root":
        run_cmd = (
            f"nohup tb-runner --cfg {remote_path}/default.cfg "
            f"--no-color --run {test_case} > {remote_path}/runtb.log 2>&1 & disown"
        )
    else:
        run_cmd = (
            f"nohup sudo tb-runner --cfg {remote_path}/default.cfg "
            f"--no-color --run {test_case} > {remote_path}/runtb.log 2>&1 & disown"
        )

    ssh_exec_background(client, run_cmd)

    # 等待并验证启动
    time.sleep(10)
    rc, stdout, _ = ssh_exec(client, "ps aux | grep tb-runner | grep -v grep")
    if rc == 0 and "tb-runner" in stdout:
        print("  ✓ 测试已启动！")
        # 只显示 python 进程行
        for line in stdout.split("\n"):
            if "tb-runner" in line and "python" in line:
                print(f"    {line.strip()[:120]}")
                break
    else:
        print("  ⚠ 未检测到 tb-runner 进程，查看日志...")
        rc, stdout, _ = ssh_exec(client, f"tail -30 {remote_path}/runtb.log 2>/dev/null")
        if stdout:
            print(f"    {stdout[:500]}")
        else:
            print("    日志为空，测试可能还在启动中")

    # ---- Step 6: 确认测试运行状态 ----
    print(f"\n  [Step 6/7] 确认测试状态...")
    time.sleep(5)
    rc, stdout, _ = ssh_exec(client, "ps aux | grep 'tb-runner\\|tencentbench' | grep -v grep | head -3")
    if stdout:
        print("  ✓ 测试进程运行中")
        # 检查结果目录
        rc, stdout, _ = ssh_exec(client, "ls -la /tmp/TENCENTBENCH/ 2>/dev/null || echo 'NO_RESULT_DIR'")
        if "NO_RESULT_DIR" not in stdout:
            print(f"  ✓ 结果目录已创建: /tmp/TENCENTBENCH/")
        else:
            print("  结果目录尚未创建（测试刚开始）")
    else:
        print("  ⚠ 未检测到测试进程")

    # ---- Step 7: 监控信息 ----
    print(f"\n  [Step 7/7] 监控命令")
    print("  ----")
    print(f"  查看实时日志:")
    print(f"    ssh {username}@{ip} 'tail -f {remote_path}/runtb.log'")
    print(f"  检查进程:")
    print(f"    ssh {username}@{ip} 'ps aux | grep tb-runner'")
    print(f"  检查结果:")
    print(f"    ssh {username}@{ip} 'ls -la /tmp/TENCENTBENCH/'")
    print(f"  下载结果:")
    print(f"    scp {username}@{ip}:/tmp/TENCENTBENCH/{{date}}/{{result}}.tar.gz .")
    print("  ----")

    client.close()
    return True


# ============== 主函数 ==============

def main():
    parser = argparse.ArgumentParser(description='云服务器连接测试 & TB 部署脚本')

    # 机器信息参数
    parser.add_argument('--ip', help='服务器 IP 地址')
    parser.add_argument('--user', '--username', dest='user', help='SSH 用户名')
    parser.add_argument('--password', '--pass', dest='password', help='SSH 密码')
    parser.add_argument('--vendor', '-v', help='厂商标识 (bdcloud/jscloud/qcloud/aliyun 等)')
    parser.add_argument('--spec', help='机器规格 (如 bcc.e1.c2m2, SA5 等)')
    parser.add_argument('--os', default='', help='操作系统 (centos/ubuntu), 不填则自动检测')
    parser.add_argument('--area', default='bj', help='地域代码 (bj/gz/sh 等), 默认 bj')

    # 配置文件方式
    parser.add_argument('--config', '-c', help='机器配置文件 (JSON)')

    # 操作模式
    parser.add_argument('--check', action='store_true', help='仅检查 SSH 连接和服务器环境')
    parser.add_argument('--deploy', action='store_true', help='部署 TB 并执行测试')
    parser.add_argument('--full', action='store_true', help='完整全链路（检查+部署）')

    args = parser.parse_args()

    if not any([args.check, args.deploy, args.full]):
        parser.print_help()
        print("\n请指定操作模式: --check / --deploy / --full")
        sys.exit(1)

    # 获取机器列表
    machines = []

    if args.ip:
        if not args.user or not args.password:
            print("✗ 使用 --ip 时必须同时指定 --user 和 --password")
            sys.exit(1)

        vendor = args.vendor or "bdcloud"
        info = VENDOR_INFO.get(vendor, {"cn": vendor})
        spec = args.spec or info.get("default_spec", "unknown")
        os_type = args.os or "centos"

        machines = [{
            "id": f"{vendor}-{args.area}-001",
            "vendor": vendor,
            "spec": spec,
            "ip": args.ip,
            "username": args.user,
            "password": args.password,
            "os": os_type,
            "area": args.area
        }]

    elif args.config:
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            print(f"✗ 无法读取配置文件: {e}")
            sys.exit(1)

        machines = config.get("machines", [])
        if not machines:
            print("✗ 配置文件中无 machines")
            sys.exit(1)
    else:
        print("✗ 请指定机器信息：使用 --ip/--user/--password 或 --config")
        print("\n示例:")
        print("  python test_connect.py --ip 120.48.51.127 --user root --password 'xxx' --vendor bdcloud --check")
        print("  python test_connect.py --config test_baidu_ksyun.json --full")
        sys.exit(1)

    print("=" * 60)
    print("云服务器连接测试 & TB 部署")
    print(f"测试机器数: {len(machines)}")
    for m in machines:
        info = VENDOR_INFO.get(m["vendor"], {"cn": m["vendor"]})
        print(f"  - {info['cn']} {m['spec']} ({m['ip']})")

    # 前置检查
    if not check_prerequisites():
        print("\n✗ 前置检查未通过")
        sys.exit(1)

    # 检查连接
    connected_machines = []
    if args.check or args.full:
        for m in machines:
            if check_ssh_connection(m):
                check_server_env(m)
                connected_machines.append(m)
            else:
                info = VENDOR_INFO.get(m["vendor"], {"cn": m["vendor"]})
                print(f"\n  ✗ {info['cn']} {m['ip']} 连接失败，跳过")

        if not connected_machines:
            print("\n✗ 所有机器连接失败")
            sys.exit(1)

    # 部署测试
    if args.deploy or args.full:
        target_machines = connected_machines if args.full else machines
        for m in target_machines:
            if not check_ssh_connection(m):
                continue
            deploy_and_test(m)

    print(f"\n{'='*60}")
    print("完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
