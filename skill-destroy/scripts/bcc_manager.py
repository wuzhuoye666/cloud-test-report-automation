#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
百度智能云 BCC 云服务器管理工具
功能：查询、关机、销毁/删除 BCC 实例

依赖安装: pip install bce-python-sdk

使用前请先配置你的 AK/SK 和地域信息
"""

import sys
import os
import json
from baidubce.auth.bce_credentials import BceCredentials
from baidubce.bce_client_configuration import BceClientConfiguration
from baidubce.services.bcc import bcc_client
from baidubce.exception import BceHttpClientError


# ==================== 配置加载 ====================
# AK/SK 和地域端点通过以下优先级加载:
#   1. 环境变量: BCE_AK / BCE_SK / BCE_HOST (最高优先级)
#   2. .env 文件 (自动按以下顺序逐级向上查找，找到即止):
#      a) 脚本所在目录:           scripts/.env
#      b) 脚本上级目录(skill根):   baidu-bcc-manager/.env
#      c) 再上级目录(项目根):       project/.env
#      d) 当前工作目录:             cwd/.env
#
# 使用方法:
#   方式一: 设置环境变量
#     export BCE_AK="your-ak" BCE_SK="your-sk"
#   方式二: 在上述任意位置创建 .env 文件:
#     BCE_AK=your-access-key-id
#     BCE_SK=your-secret-access-key
#     BCE_HOST=http://bcc.bj.baidubce.com
#
# 获取地址: https://console.bce.baidu.com/iam/#/iam/accesslist

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_env_file():
    """逐级向上查找 .env 文件，返回找到的路径或 None"""
    # 候选目录列表（按优先级排序）
    candidates = [
        _SCRIPT_DIR,                                    # a) 脚本同目录
        os.path.dirname(_SCRIPT_DIR),                   # b) skill 根目录
        os.path.dirname(os.path.dirname(_SCRIPT_DIR)), # c) 再上级(项目根)
        os.getcwd(),                                    # d) 当前工作目录
    ]
    # 去重（保持顺序）
    seen = set()
    unique_candidates = []
    for d in candidates:
        abs_d = os.path.abspath(d)
        if abs_d not in seen:
            seen.add(abs_d)
            unique_candidates.append(abs_d)

    for directory in unique_candidates:
        env_path = os.path.join(directory, '.env')
        if os.path.isfile(env_path):
            return env_path

    return None


_ENV_FILE = _find_env_file()


def _load_env_file(env_path):
    """从 .env 文件加载键值对到环境变量"""
    if not os.path.isfile(env_path):
        return
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:  # 不覆盖已有的环境变量
                os.environ[key] = value


# 加载 .env 文件（如果存在）
_load_env_file(_ENV_FILE)

# 从环境变量读取配置
AK = os.environ.get('BCE_AK', '')
SK = os.environ.get('BCE_SK', '')
HOST = os.environ.get('BCE_HOST', 'http://bcc.bj.baidubce.com')
# =================================================


def create_bcc_client():
    """创建并返回BCC客户端"""
    config = BceClientConfiguration(
        credentials=BceCredentials(AK, SK),
        endpoint=HOST
    )
    return bcc_client.BccClient(config)


def list_all_instances(client):
    """
    查询所有BCC实例列表
    返回: 实例列表
    """
    print("\n" + "="*60)
    print("正在查询所有BCC实例...")
    print("="*60)
    
    instances = []
    marker = None
    
    while True:
        try:
            if marker:
                response = client.list_instances(marker=marker, max_keys=100)
            else:
                response = client.list_instances(max_keys=100)
            
            if response and hasattr(response, 'instances') and response.instances:
                instances.extend(response.instances)
            
            # 检查是否有下一页
            if response and hasattr(response, 'is_truncated') and response.is_truncated:
                marker = response.next_marker
            else:
                break
                
        except BceHttpClientError as e:
            print(f"\n❌ 查询实例失败: {e}")
            return None
    
    return instances


def display_instances(instances):
    """格式化显示实例信息"""
    if not instances:
        print("\n⚠️  未找到任何BCC实例")
        return
    
    print(f"\n📋 共找到 {len(instances)} 个实例:\n")
    print("-"*90)
    print(f"{'序号':<4} {'实例ID':<20} {'名称':<18} {'状态':<12} {'IP地址':<16} {'计费方式':<10}")
    print("-"*90)
    
    for idx, inst in enumerate(instances, 1):
        instance_id = getattr(inst, 'instance_id', 'N/A')
        name = getattr(inst, 'name', 'N/A') or 'N/A'
        status = getattr(inst, 'status', 'N/A')
        
        # 获取内网IP
        internal_ip = 'N/A'
        if hasattr(inst, 'inner_ip_address') and inst.inner_ip_address:
            internal_ip = inst.inner_ip_address[0] if isinstance(inst.inner_ip_address, list) else inst.inner_ip_address
        
        # 获取公网IP
        public_ip = ''
        if hasattr(inst, 'public_ip') and inst.public_ip:
            public_ip = inst.public_ip[0] if isinstance(inst.public_ip, list) else inst.public_ip
        
        ip_display = f"{internal_ip}" + (f" / {public_ip}" if public_ip and public_ip != internal_ip else "")
        
        # 计费方式
        payment_timing = getattr(inst, 'payment_timing', 'N/A')
        payment_display = '包年包月' if payment_timing == 'Prepaid' else ('按量付费' if payment_timing == 'Postpaid' else payment_timing)
        
        print(f"{idx:<4} {instance_id:<20} {str(name)[:17]:<18} {status:<12} {ip_display[:15]:<16} {payment_display:<10}")
    
    print("-"*90)


def stop_instance(client, instance_id, force_stop=False, no_charge=True):
    """
    停止(关机)指定实例
    
    参数:
        client: BCC客户端
        instance_id: 实例ID
        force_stop: 是否强制停止(True=强制/断电, False=正常关机)
        no_charge: 是否关机不计费(仅按量付费实例有效)
    
    返回: bool 操作是否成功
    """
    try:
        print(f"\n⏳ 正在{'强制' if force_stop else ''}停止实例: {instance_id}")
        print(f"   强制模式: {'是' if force_stop else '否'}")
        print(f"   关机不计费: {'是' if no_charge else '否'}")
        
        response = client.stop_instance(
            instance_id=instance_id,
            force_stop=force_stop,
            stopWithNoCharge=no_charge
        )
        
        print(f"✅ 实例 {instance_id} 停止成功!")
        return True
        
    except BceHttpClientError as e:
        error_msg = str(e)
        if "InvalidInstanceState" in error_msg or "instance is not Running" in error_msg.lower():
            print(f"❌ 停止失败: 实例当前状态不允许停止(可能已停止或正在状态变更中)")
        elif "InstanceNotFound" in error_msg or "not found" in error_msg.lower():
            print(f"❌ 停止失败: 实例不存在")
        else:
            print(f"❌ 停止实例失败: {e}")
        return False


def release_instance(client, instance_id, related_resources=False):
    """
    释放(销毁/删除)指定实例
    注意: 此操作不可逆，释放后数据将无法恢复！
    
    参数:
        client: BCC客户端
        instance_id: 实例ID
        related_resources: 是否同时释放关联资源(EIP/CDS等)
    
    返回: bool 操作是否成功
    """
    try:
        print(f"\n⏳ 正在释放(销毁)实例: {instance_id}")
        print(f"   同时释放关联资源: {'是' if related_resources else '否'}")
        
        if related_resources:
            # 使用带关联资源的释放接口
            from baidubce.services.bcc.bcc_model import ReleaseInstanceModel
            
            release_model = ReleaseInstanceModel(
                instanceId=instance_id,
                relatedReleaseWithInstance=["EIP", "CDS", "SNAP", "ENI"]
            )
            response = client.release_instance_with_related_resources(release_model)
        else:
            # 简单释放(仅释放实例本身)
            response = client.release_instance(instance_id=instance_id)
        
        print(f"✅✅✅ 实例 {instance_id} 已成功销毁删除！")
        if related_resources:
            print("   关联资源(EIP/CDS/快照/网卡)也已一并释放")
        return True
        
    except BceHttpClientError as e:
        error_msg = str(e)
        if "prepaid" in error_msg.lower() or "Prepaid" in error_msg:
            print(f"❌ 释放失败: 该实例为包年包月(预付费)实例，需要使用提前释放接口或等待到期")
            print("   提示: 预付费实例需先转为按量付费或使用专门的预付费释放接口")
        elif "InstanceNotFound" in error_msg or "not found" in error_msg.lower():
            print(f"❌ 释放失败: 实例不存在")
        elif "InvalidInstanceState" in error_msg:
            print(f"❌ 释放失败: 实例当前状态不允许释放(请确保实例处于Stopped状态)")
        else:
            print(f"❌ 释放实例失败: {e}")
        return False


def batch_stop_instances(client, instance_ids, force_stop=False, no_charge=True):
    """批量停止多个实例"""
    success_count = 0
    fail_count = 0
    
    for instance_id in instance_ids:
        if stop_instance(client, instance_id, force_stop, no_charge):
            success_count += 1
        else:
            fail_count += 1
    
    print(f"\n📊 批量停止完成: 成功 {success_count} 个, 失败 {fail_count} 个")
    return success_count, fail_count


def batch_release_instances(client, instance_ids, related_resources=False):
    """批量释放多个实例"""
    success_count = 0
    fail_count = 0
    
    for instance_id in instance_ids:
        if release_instance(client, instance_id, related_resources):
            success_count += 1
        else:
            fail_count += 1
    
    print(f"\n📊 批量销毁完成: 成功 {success_count} 个, 失败 {fail_count} 个")
    return success_count, fail_count


def get_user_confirmation(action, instance_info):
    """获取用户确认"""
    print(f"\n⚠️  ⚠️  ⚠️  警告 ⚠️  ⚠️  ⚠️")
    print(f"您即将执行操作: 【{action}】")
    print(f"目标实例:")
    print(f"  {instance_info}")
    print("\n此操作不可逆！请确认是否继续？")
    
    confirm = input("\n输入 'YES' 确认执行, 其他任意键取消: ").strip()
    return confirm == 'YES'


def main():
    """主函数 - 交互式菜单"""
    print("\n" + "="*60)
    print("  🖥️  百度智能云 BCC 云服务器管理工具")
    print("  功能: 查询 | 关机 | 销毁/删除 实例")
    print("="*60)
    
    # 检查配置
    if not AK or not SK:
        print("\n❌ 错误: 未检测到百度云AK/SK配置!")
        print(f"\n   请选择以下方式之一进行配置:")
        print(f"\n   方式一: 创建 .env 文件（脚本会自动在以下位置逐级查找）:")
        print(f"     1) scripts/.env              (脚本同目录)")
        print(f"     2) baidu-bcc-manager/.env     (skill根目录)")
        print(f"     3) 项目根目录/.env            (上级项目)")
        print(f"     4) 当前工作目录/.env           (cwd)")
        print(f"\n   .env 文件内容:")
        print(f"     BCE_AK=your-access-key-id")
        print(f"     BCE_SK=your-secret-access-key")
        print(f"     BCE_HOST=http://bcc.bj.baidubce.com  # 可选,默认北京")
        if _ENV_FILE:
            print(f"\n   ℹ️  已找到 .env 文件但缺少 AK/SK: {_ENV_FILE}")
        else:
            print(f"\n   ℹ️  未找到 .env 文件，搜索路径从: {_SCRIPT_DIR} 向上查找")
        print(f"\n   方式二: 设置环境变量(优先级更高):")
        print(f"     export BCE_AK='xxx' BCE_SK='xxx'")
        print(f"\n   获取AK/SK地址: https://console.bce.baidu.com/iam/#/iam/accesslist")
        sys.exit(1)
    
    # 创建客户端
    client = create_bcc_client()
    print(f"\n✅ 已连接到BCC服务 (端点: {HOST})")
    
    while True:
        print("\n" + "="*60)
        print("请选择操作:")
        print("="*60)
        print("  1. 📋 查看所有实例")
        print("  2. ⏹️  关机(停止)单个实例")
        print("  3. 🗑️  销毁/删除单个实例")
        print("  4. ⏹️  批量关机(停止)实例")
        print("  5. 🗑️  批量销毁/删除实例")
        print("  6. 🔄 智能模式: 先关机再销毁")
        print("  0. ❌ 退出程序")
        print("-"*60)
        
        choice = input("请输入选项编号 [0-6]: ").strip()
        
        if choice == '0':
            print("\n感谢使用，再见! 👋")
            break
            
        elif choice == '1':
            # 查看所有实例
            instances = list_all_instances(client)
            if instances:
                display_instances(instances)
                
        elif choice == '2':
            # 关机单个实例
            instances = list_all_instances(client)
            if not instances:
                continue
                
            display_instances(instances)
            
            try:
                idx = int(input("\n请输入要关机的实例序号: ").strip()) - 1
                if 0 <= idx < len(instances):
                    target = instances[idx]
                    instance_id = target.instance_id
                    
                    info = f"ID: {instance_id}, 名称: {getattr(target, 'name', 'N/A')}, 状态: {target.status}"
                    
                    # 选择停止模式
                    print("\n请选择停止模式:")
                    print("  1. 正常关机 (推荐)")
                    print("  2. 强制关机 (可能导致数据丢失)")
                    mode = input("请选择 [1/2], 默认为正常关机: ").strip() or '1'
                    force = (mode == '2')
                    
                    # 是否关机不计费
                    no_charge_input = input("是否开启'关机不计费'(仅按量付费有效)? [Y/n]: ").strip().lower()
                    no_charge = no_charge_input != 'n'
                    
                    if get_user_confirmation("关机(停止)", info):
                        stop_instance(client, instance_id, force_stop=force, no_charge=no_charge)
                else:
                    print("❌ 无效的序号")
            except ValueError:
                print("❌ 请输入有效的数字")
                
        elif choice == '3':
            # 销毁单个实例
            instances = list_all_instances(client)
            if not instances:
                continue
                
            display_instances(instances)
            
            try:
                idx = int(input("\n请输入要销毁的实例序号: ").strip()) - 1
                if 0 <= idx < len(instances):
                    target = instances[idx]
                    instance_id = target.instance_id
                    
                    info = f"ID: {instance_id}, 名称: {getattr(target, 'name', 'N/A')}, 状态: {target.status}"
                    
                    # 是否关联释放资源
                    rel_input = input("是否同时释放关联资源(EIP/磁盘/快照)? [y/N]: ").strip().lower()
                    related = rel_input == 'y'
                    
                    if get_user_confirmation("销毁/删除(不可逆)", info):
                        release_instance(client, instance_id, related_resources=related)
                else:
                    print("❌ 无效的序号")
            except ValueError:
                print("❌ 请输入有效的数字")
                
        elif choice == '4':
            # 批量关机
            instances = list_all_instances(client)
            if not instances:
                continue
                
            display_instances(instances)
            
            input_str = input("\n请输入要关机的实例序号(逗号分隔，如: 1,3,5): ").strip()
            try:
                indices = [int(x.strip()) - 1 for x in input_str.split(',') if x.strip()]
                target_instances = [instances[i] for i in indices if 0 <= i < len(instances)]
                
                if not target_instances:
                    print("❌ 无有效的实例序号")
                    continue
                    
                ids = [inst.instance_id for inst in target_instances]
                info = f"共 {len(ids)} 个实例: {', '.join(ids)}"
                
                force_input = input("是否强制关机? [y/N]: ").strip().lower()
                force = force_input == 'y'
                
                if get_user_confirmation("批量关机", info):
                    batch_stop_instances(client, ids, force_stop=force)
            except ValueError:
                print("❌ 输入格式错误，请用逗号分隔数字")
                
        elif choice == '5':
            # 批量销毁
            instances = list_all_instances(client)
            if not instances:
                continue
                
            display_instances(instances)
            
            input_str = input("\n请输入要销毁的实例序号(逗号分隔，如: 1,3,5): ").strip()
            try:
                indices = [int(x.strip()) - 1 for x in input_str.split(',') if x.strip()]
                target_instances = [instances[i] for i in indices if 0 <= i < len(instances)]
                
                if not target_instances:
                    print("❌ 无有效的实例序号")
                    continue
                    
                ids = [inst.instance_id for inst in target_instances]
                info = f"共 {len(ids)} 个实例: {', '.join(ids)}"
                
                if get_user_confirmation("批量销毁/删除(不可逆)", info):
                    batch_release_instances(client, ids)
            except ValueError:
                print("❌ 输入格式错误，请用逗号分隔数字")
                
        elif choice == '6':
            # 智能模式：先关机再销毁
            instances = list_all_instances(client)
            if not instances:
                continue
                
            display_instances(instances)
            
            try:
                idx = int(input("\n请输入目标实例序号: ").strip()) - 1
                if 0 <= idx < len(instances):
                    target = instances[idx]
                    instance_id = target.instance_id
                    
                    info = f"ID: {instance_id}, 名称: {getattr(target, 'name', 'N/A')}, 当前状态: {target.status}"
                    
                    if get_user_confirmation("智能模式(先关机再销毁)", info):
                        # 第一步：关机
                        print("\n--- 第1步: 关机 ---")
                        if target.status == 'Running':
                            stop_success = stop_instance(client, instance_id, force_stop=False)
                            if stop_success:
                                import time
                                print("⏳ 等待实例完全停止...")
                                time.sleep(5)  # 等待关机完成
                            else:
                                print("⚠️  关机失败，尝试直接释放...")
                        else:
                            print(f"ℹ️  实例当前状态为 {target.status}，跳过关机步骤")
                        
                        # 第二步：销毁
                        print("\n--- 第2步: 销毁 ---")
                        release_instance(client, instance_id)
                else:
                    print("❌ 无效的序号")
            except ValueError:
                print("❌ 请输入有效的数字")
                
        else:
            print("❌ 无效的选项，请重新选择")


if __name__ == '__main__':
    main()
