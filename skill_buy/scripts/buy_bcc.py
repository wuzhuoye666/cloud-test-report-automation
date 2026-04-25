#!/usr/bin/env python3
"""
百度云 BCC 云服务器购买工具 (Skill 版本)
==========================================
配置来源:
  - AK/SK: 环境变量 BCE_AK / BCE_SK (或 .env 文件)
  - 其他配置: bcc_config.json (同目录)

用法:
  python buy_bcc.py buy                          # 购买服务器（使用 JSON 配置）
  python buy_bcc.py buy --spec bcc.g8.c8m32      # 覆盖规格
  python buy_bcc.py buy --zone cn-bj-a            # 覆盖可用区
  python buy_bcc.py query-images                  # 查询可用镜像
  python buy_bcc.py query-specs                   # 查询可用规格
  python buy_bcc.py query-resources               # 查询VPC/子网/安全组
  python buy_bcc.py show-config                   # 显示当前加载的配置
  python buy_bcc.py resolve-image ubuntu22        # 智能匹配镜像并回写配置
  python buy_bcc.py resolve-spec 8核32G           # 智能匹配规格并回写配置
  python buy_bcc.py resolve "ubuntu 8c32g"        # 一键匹配镜像+规格并回写
"""

import argparse
import ipaddress
import json
import os
import re
import secrets
import string
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from baidubce.auth.bce_credentials import BceCredentials
from baidubce.bce_client_configuration import BceClientConfiguration
from baidubce.exception import BceHttpClientError
from baidubce.services.bcc import bcc_model
from baidubce.services.bcc.bcc_client import BccClient


# ============================================================
# 配置加载
# ============================================================

def get_skill_root() -> str:
    """Skill 根目录 (scripts/ 的上级目录)"""
    return os.path.dirname(os.path.abspath(__file__))


def get_script_dir() -> str:
    """脚本所在目录"""
    return os.path.abspath(os.path.dirname(__file__))


def _default_config_path() -> str:
    """默认配置文件路径: assets/bcc_config.json"""
    return os.path.join(get_skill_root(), "assets", "bcc_config.json")


def load_json_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """从 JSON 文件加载配置"""
    if config_path is None:
        config_path = _default_config_path()

    if not os.path.exists(config_path):
        print(f"[WARN] 配置文件不存在: {config_path}，使用默认值")
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_credentials() -> Dict[str, str]:
    """从环境变量 / .env 加载 AK/SK（向上查找 .env 文件）"""
    # 依次尝试: 脚本目录 → skill根目录 → 当前工作目录
    env_candidates = [
        get_script_dir(),
        get_skill_root(),
        os.getcwd(),
    ]
    for d in env_candidates:
        env_file = os.path.join(d, ".env")
        if os.path.exists(env_file):
            load_dotenv(env_file)
            break
    else:
        # 都找不到也尝试调用无参的load_dotenv（会找cwd）
        load_dotenv()

    ak = os.getenv("BCE_AK", "").strip()
    sk = os.getenv("BCE_SK", "").strip()

    if not ak or not sk:
        print("[ERROR] 缺少凭证: 请设置环境变量 BCE_AK 和 BCE_SK")
        print("  Windows PowerShell: $env:BCE_AK=\"your_ak\"; $env:BCE_SK=\"your_sk\"")
        print("  Linux/Mac:          export BCE_AK=your_sk && export BCE_SK=your_sk")
        print(f"  或在以下任一位置创建 .env 文件写入 AK/SK:")
        print(f"    - {os.path.join(get_skill_root(), '.env')} (推荐)")
        print(f"    - {os.path.join(get_script_dir(), '.env')}")
        print(f"    - 当前工作目录下的 .env")
        sys.exit(1)

    return {"ak": ak, "sk": sk}


def merge_config(json_cfg: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """合并 JSON 配置 + CLI 覆盖参数 + 默认值，输出扁平化配置字典"""

    region = overrides.get("region") or json_cfg.get("region", {}).get("value", "bj")
    zone = overrides.get("zoneName") or json_cfg.get("zoneName", {}).get("value", "cn-bj-d")

    inst = json_cfg.get("instance", {})
    img = json_cfg.get("image", {})
    disk = json_cfg.get("systemDisk", {})
    net = json_cfg.get("network", {})
    eip_cfg = json_cfg.get("eip", {})

    spec = overrides.get("spec") or inst.get("spec", "")

    config = {
        # 凭证 (来自环境变量)
        "ak": "",
        "sk": "",
        # 基础
        "region": region,
        "zone": zone,
        "instance_name": overrides.get("name") or inst.get("name", "bcc-server"),
        # 镜像
        "image_id": img.get("imageId", ""),
        "image_name": img.get("imageName", ""),
        # 规格
        "spec_id": spec,
        # 系统盘
        "disk_type": disk.get("storageType", "SSD_Enhanced"),
        "disk_size_gb": int(disk.get("sizeInGb", 40)),
        # 网络
        "subnet_id": net.get("subnetId", ""),
        "vpc_id": net.get("vpcId", ""),
        "security_group_id": (net.get("securityGroupIds") or [""])[0],
        # EIP
        "buy_eip": eip_cfg.get("enabled", True),
        "eip_name": eip_cfg.get("name", "bcc-eip"),
        "internet_charge_type": eip_cfg.get("internetChargeType", "TRAFFIC_POSTPAID_BY_HOUR"),
        "bandwidth_mbps": int(eip_cfg.get("bandwidthInMbps", 100)),
        # 密码
        "admin_pass": json_cfg.get("adminPass", ""),
        # 数量
        "purchase_count": int(inst.get("purchaseCount", 1)),
    }

    return config


def load_config(overrides: Optional[Dict[str, Any]] = None, config_path: Optional[str] = None) -> Dict[str, str]:
    """统一入口: JSON配置 + 环境变量AK/SK + CLI覆盖"""
    creds = load_credentials()
    json_cfg = load_json_config(config_path)
    cfg = merge_config(json_cfg, overrides or {})
    cfg.update(creds)  # ak/sk 最后覆盖，确保优先级最高
    return cfg


# ============================================================
# 客户端构建
# ============================================================

def build_client(config: Dict[str, str], service: str = "bcc") -> BccClient:
    """构建 API 客户端"""
    region = config["region"]
    cred = BceCredentials(config["ak"], config["sk"])
    endpoint = f"{service}.{region}.baidubce.com"
    cfg = BceClientConfiguration(credentials=cred, endpoint=endpoint)
    return BccClient(cfg)


def body_map(resp: Any) -> Dict[str, Any]:
    """提取响应 body"""
    if hasattr(resp, "get_body_map"):
        b = resp.get_body_map()
        if isinstance(b, dict):
            return b
    return {}


# ============================================================
# 密码生成
# ============================================================

def make_password(length: int = 12) -> str:
    """生成随机密码"""
    chars = string.ascii_letters + string.digits + "!@#$%^*()"
    while True:
        pwd = "".join(secrets.choice(chars) for _ in range(length))
        if (any(c.isalpha() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "!@#$%^*()" for c in pwd)):
            return pwd


def mask_password(pwd: str) -> str:
    """脱敏显示密码"""
    if len(pwd) <= 4:
        return "*" * len(pwd)
    return pwd[:2] + "*" * (len(pwd) - 4) + pwd[-2:]


# ============================================================
# IP 提取
# ============================================================

def extract_ip(data: Any) -> Optional[str]:
    """递归提取 IPv4 地址"""
    if isinstance(data, str):
        try:
            ip = ipaddress.ip_address(data)
            if isinstance(ip, ipaddress.IPv4Address):
                return data
        except ValueError:
            pass
    elif isinstance(data, list):
        for v in data:
            found = extract_ip(v)
            if found:
                return found
    elif isinstance(data, dict):
        for v in data.values():
            found = extract_ip(v)
            if found:
                return found
    return None


def infer_login_user(image_name: str) -> str:
    """根据镜像推断登录用户名"""
    low = image_name.lower()
    if "windows" in low:
        return "Administrator"
    if "ubuntu" in low:
        return "ubuntu"
    if "debian" in low:
        return "debian"
    return "root"


# ============================================================
# 查询命令
# ============================================================

def cmd_query_images(config: Dict[str, str]) -> None:
    """查询可用公共镜像"""
    client = build_client(config)
    resp = client.list_images()
    data = body_map(resp)
    images = data.get("images", [])

    print(f"\n=== 公共镜像列表 (共 {len(images)} 个) ===\n")

    categories = {}
    for img in images:
        img_id = img.get("id", "")
        name = (img.get("name", "") or "").strip()
        os_name = (img.get("osName", "") or "").strip()
        os_ver = (img.get("osVersion", "") or "").strip()

        full_name = f"{os_name} {os_ver} - {name}" if name else f"{os_name} {os_ver}"
        key = os_name.lower().split()[0] if os_name else "other"

        categories.setdefault(key, []).append({
            "id": img_id,
            "name": full_name,
        })

    for cat, items in sorted(categories.items()):
        print(f"--- {cat.upper()} ---")
        for item in items[:10]:
            arch_tag = ""
            nl = item["name"].lower()
            if "aarch64" in nl or "arm" in nl:
                arch_tag = " [ARM]"
            elif "amd64" in nl or "x86_64" in nl or "(64bit)" in nl:
                arch_tag = " [x86]"
            print(f"  {item['id']:<18} |{item['name']}{arch_tag}")
        if len(items) > 10:
            print(f"  ... 还有 {len(items)-10} 个")
        print()


def cmd_query_specs(config: Dict[str, str]) -> None:
    """查询可用实例规格"""
    client = build_client(config)
    resp = client.list_flavor_spec(zone_name=config["zone"])
    data = body_map(resp)
    zone_resources = data.get("zoneResources") or []

    print(f"\n=== 实例规格列表 (区域: {config['zone']}) ===\n")

    rows = []
    for zr in zone_resources:
        if not isinstance(zr, dict):
            continue
        for group in (zr.get("bccResources") or {}).get("flavorGroups") or []:
            for flavor in group.get("flavors") or []:
                cpu = flavor.get("cpuCount", 0)
                mem = flavor.get("memoryCapacityInGB", 0)
                if cpu <= 16 and mem <= 128:
                    rows.append({
                        "spec": flavor.get("spec", ""),
                        "cpu": cpu,
                        "mem": mem,
                        "disk": ",".join(flavor.get("systemDiskType") or [])[:3],
                    })

    rows.sort(key=lambda x: (x["cpu"], x["mem"]))

    print(f"{'规格':<24} {'CPU':>4} {'内存':>6} {'支持的磁盘类型'}")
    print("-" * 75)
    for r in rows[:80]:
        print(f"{r['spec']:<24} {r['cpu']:>4}C {r['mem']:>4}GB  {r['disk']}")

    if len(rows) > 80:
        print(f"\n... 还有 {len(rows)-80} 个更大规格")


def cmd_query_resources(config: Dict[str, str]) -> None:
    """查询 VPC / 子网 / 安全组"""
    from baidubce.services.vpc.vpc_client import VpcClient

    region = config["region"]
    cred = BceCredentials(config["ak"], config["sk"])

    print(f"\n=== 网络资源列表 (区域: {region}) ===\n")

    vpc_cfg = BceClientConfiguration(credentials=cred, endpoint=f"vpc.{region}.baidubce.com")
    vpc_client = VpcClient(vpc_cfg)

    print("--- VPC ---")
    try:
        resp = vpc_client.list_vpcs(max_keys=50)
        for vpc in body_map(resp).get("vpcs", [])[:10]:
            print(f"  {vpc.get('vpcId'):<20} | {vpc.get('name') or 'N/A':<20} | CIDR: {vpc.get('cidr', 'N/A')}")
    except Exception as e:
        print(f"  查询失败: {e}")

    print("\n--- 子网 ---")
    try:
        resp = vpc_client.list_subnets(max_keys=50)
        for sn in body_map(resp).get("subnets", [])[:15]:
            print(f"  {sn.get('subnetId'):<20} | 可用区:{sn.get('zoneName','?'):<12} | "
                  f"VPC:{(sn.get('vpcId') or '')[:12]:<14} | CIDR: {sn.get('cidr', 'N/A')}")
    except Exception as e:
        print(f"  查询失败: {e}")

    print("\n--- 安全组 ---")
    try:
        resp = vpc_client.list_security_groups(max_keys=50)
        for sg in body_map(resp).get("securityGroups", []):
            print(f"  {sg.get('securityGroupId'):<20} | {sg.get('name') or 'N/A':<20} | "
                  f"规则数: {len(sg.get('rules') or [])}")
    except Exception as e:
        print(f"  查询失败: {e}")


def cmd_show_config(config: Dict[str, str], raw_json: Dict[str, Any], config_path: Optional[str] = None) -> None:
    """显示当前加载的完整配置"""
    print("=" * 60)
    print("当前 BCC 配置 (bcc_config.json)")
    print("=" * 60)

    # 显示原始 JSON 结构化内容
    def _show_section(label: str, data: Dict[str, Any], indent: int = 0) -> None:
        prefix = "  " * indent
        print(f"\n{prefix}[{label}]")
        for k, v in data.items():
            if k.startswith("_"):
                continue
            if isinstance(v, dict):
                _show_section(k, v, indent + 1)
            elif isinstance(v, list):
                print(f"{prefix}  {k}: {json.dumps(v, ensure_ascii=False)}")
            else:
                print(f"{prefix}  {k}: {v}")

    for section_key in ("region", "zoneName", "instance", "image", "systemDisk",
                         "network", "eip"):
        if section_key in raw_json:
            val = raw_json[section_key]
            if isinstance(val, dict):
                _show_section(section_key, val)
            else:
                print(f"  {section_key}: {val}")

    print(f"\n  adminPass: {'******已设置' if raw_json.get('adminPass') else '(自动生成)'}")

    print(f"\n{'-' * 60}")
    print("凭证来源: 环境变量 BCE_AK / BCE_SK")
    print(f"  BCE_AK:   {config['ak'][:8]}...{config['ak'][-4:]}" if len(config.get("ak", "")) > 12 else f"  BCE_AK:   {config.get('ak', '(未设置)')}")
    print(f"  BCE_SK:   {config['sk'][:4]}****")
    print(f"\n配置文件路径: {config_path or _default_config_path()}")


# ============================================================
# 智能匹配：根据用户关键词自动查找镜像/规格并回写配置
# ============================================================

def fuzzy_match(text: str, keywords: List[str]) -> int:
    """计算文本与关键词列表的匹配得分（命中越多分越高）"""
    text_lower = text.lower()
    score = 0
    for kw in keywords:
        if kw.lower() in text_lower:
            score += 1
        # 部分匹配也给分
        for part in kw.lower().split():
            if len(part) >= 3 and part in text_lower:
                score += 0.5
    return score


def cmd_resolve_image(config: Dict[str, str], keyword: str,
                      config_path: Optional[str] = None) -> Tuple[str, str]:
    """根据关键词智能匹配镜像，返回 (imageId, imageName)，并回写配置"""
    client = build_client(config)
    resp = client.list_images()
    images = body_map(resp).get("images", [])

    if not images:
        print("[ERROR] 未查询到任何可用镜像")
        sys.exit(1)

    # 构建搜索关键词
    search_terms = [keyword]
    # 常见别名映射
    alias_map = {
        "ubuntu22": "Ubuntu 22.04",
        "ubuntu20": "Ubuntu 20.04",
        "ubuntu24": "Ubuntu 24.04",
        "centos7": "CentOS 7",
        "centos8": "CentOS 8",
        "centos9": "CentOS 9",
        "debian12": "Debian 12",
        "debian11": "Debian 11",
        "win2022": "Windows Server 2022",
        "win2019": "Windows Server 2019",
        "rocky": "Rocky Linux",
        "almalinux": "AlmaLinux",
        "openeuler": "openEuler",
    }
    kw_lower = keyword.lower().replace(" ", "").replace(".", "").replace("-", "")
    for alias, full in alias_map.items():
        if alias in kw_lower or full.lower() in kw_lower:
            search_terms.append(full)
            break

    # 评分排序
    scored = []
    for img in images:
        name_parts = [
            img.get("name", ""),
            img.get("osName", ""),
            img.get("osVersion", ""),
            img.get("id", ""),
        ]
        combined_text = " ".join(str(p) for p in name_parts if p)
        s = fuzzy_match(combined_text, search_terms)
        if s > 0:
            scored.append((s, img))

    scored.sort(key=lambda x: -x[0])

    print(f"\n=== 镜像智能匹配 (关键词: '{keyword}') ===")
    if not scored:
        # 无匹配时，显示公共镜像前10个供参考
        print(f"  [WARN] 未找到匹配 '{keyword}' 的镜像，可用镜像:")
        public_imgs = [i for i in images if i.get("type") == "Public"]
        for i, img in enumerate(public_imgs[:10], 1):
            os_name = img.get("osName", "")
            os_ver = img.get("osVersion", "")
            print(f"  {i}. {img['id']:<18} | {os_name} {os_ver}")
        return "", ""

    # 显示 Top 匹配结果（最多5个）
    best_img = None
    for rank, (score, img) in enumerate(scored[:5], 1):
        marker = " >>>" if rank == 1 else ""
        img_id = img.get("id", "")
        os_name = img.get("osName", "")
        os_ver = img.get("osVersion", "")
        img_type = img.get("type", "")
        print(f"  {rank}. [{score:.0f}分] {img_id:<18} | {os_name} {os_ver} ({img_type}){marker}")
        if not best_img:
            best_img = img

    image_id = best_img["id"]
    image_name = f"{best_img.get('osName', '')} {best_img.get('osVersion', '')}"
    print(f"\n  [AUTO] 选择: {image_id} ({image_name})")

    # 回写配置文件
    _write_config_image(image_id, image_name, config_path)

    return image_id, image_name


def parse_spec_keyword(keyword: str) -> Optional[Tuple[int, int]]:
    """从自然语言中解析 CPU 核数和内存大小(GB)

    支持格式:
      - "8核32G", "8c32g", "8C32G"
      - "4核16g", "4c16g"
      - "2c2g", "2核2g"
      - "8 core 32gb"
    """
    keyword_clean = keyword.strip().lower()

    # 正则匹配各种写法
    patterns = [
        r"(\d+)\s*[核cC]\s*(\d+)\s*[gG]",           # 8核32g, 8c32g
        r"(\d+)\s*core[s]?\s*(\d+)\s*gb?",          # 8 cores 32gb
        r"(\d+)\s*c\s+(\d+)\s*g",                   # 8c32g
        r"c(\d+)m(\d+)",                             # c8m32 (百度规格命名风格)
    ]

    for pat in patterns:
        m = re.search(pat, keyword_clean)
        if m:
            cpu = int(m.group(1))
            mem = int(m.group(2))
            return cpu, mem

    return None


def cmd_resolve_spec(config: Dict[str, str], keyword: str,
                     config_path: Optional[str] = None) -> str:
    """根据关键词/核数内存智能匹配规格，返回 spec 名称，并回写配置"""
    client = build_client(config)
    zone = config["zone"]
    resp = client.list_flavor_spec(zone_name=zone)
    zone_resources = body_map(resp).get("zoneResources") or []

    all_specs = []
    for zr in zone_resources:
        if not isinstance(zr, dict):
            continue
        for group in (zr.get("bccResources") or {}).get("flavorGroups") or []:
            for flavor in group.get("flavors") or []:
                pt = str(flavor.get("productType", "")).lower()
                if pt == "postpaid":
                    all_specs.append({
                        "spec": flavor.get("spec", ""),
                        "cpu": flavor.get("cpuCount", 0),
                        "mem": flavor.get("memoryCapacityInGB", 0),
                    })

    if not all_specs:
        print(f"[ERROR] 可用区 {zone} 未找到可用规格")
        sys.exit(1)

    parsed_cpu_mem = parse_spec_keyword(keyword)

    print(f"\n=== 规格智能匹配 (关键词: '{keyword}') ===")

    best_spec = None
    best_score = -1
    results = []

    for s in all_specs:
        cpu, mem = s["cpu"], s["mem"]
        spec_name = s["spec"]

        # 计算匹配得分
        if parsed_cpu_mem:
            target_cpu, target_mem = parsed_cpu_mem
            # 精确匹配得满分，CPU和内存分别评分
            cpu_score = max(0, 10 - abs(cpu - target_cpu)) * 2
            mem_score = max(0, 10 - abs(mem - target_mem))
            # 精确匹配加分
            if cpu == target_cpu and mem == target_mem:
                exact_bonus = 100
            elif cpu >= target_cpu and mem >= target_mem:
                exact_bonus = 50  # 大于等于也行（向上兼容）
            else:
                exact_bonus = 0
            score = cpu_score + mem_score + exact_bonus
            # 关键词直接匹配 spec 名字
            if keyword.lower() in spec_name.lower():
                score += 200
        else:
            # 纯文本模糊匹配 spec 名字
            s = fuzzy_match(spec_name, [keyword])
            score = s * 10 if s > 0 else 0

        results.append((score, s))

        if score > best_score:
            best_score = score
            best_spec = s

    # 按 score 排序显示 top 结果
    results.sort(key=lambda x: -x[0])
    shown = 0
    for score, s in results[:10]:
        if score <= 0 and shown >= 3:
            break
        marker = " >>>" if s is best_spec else ""
        print(f"  [{score:.0f}] {s['spec']:<24} {s['cpu']:>2}C/{s['mem']:>3}GB{marker}")
        shown += 1

    if best_spec:
        spec_name = best_spec["spec"]
        print(f"\n  [AUTO] 选择: {spec_name} ({best_spec['cpu']}核{best_spec['mem']}G)")
        _write_config_spec(spec_name, config_path)
        return spec_name
    else:
        print(f"  [WARN] 未找到匹配的规格，可用的最小规格:")
        all_specs.sort(key=lambda x: (x["cpu"], x["mem"]))
        for s in all_specs[:5]:
            print(f"  {s['spec']}  {s['cpu']}C/{s['mem']}GB")
        return ""


def cmd_resolve_all(keyword: str, config: Dict[str, str],
                   config_path: Optional[str] = None) -> Dict[str, str]:
    """一键智能匹配：从用户一句话中同时提取镜像和规格需求

    示例输入: "ubuntu22 8核32g", "centos7 4c16g", "买一台ubuntu 8c32g的服务器"
    返回更新后的 config
    """
    print("=" * 60)
    print(f"BCC 智能配置解析: \"{keyword}\"")
    print("=" * 60)

    updated = dict(config)

    # 尝试拆分关键词中的镜像和规格部分
    # 策略：先识别 OS 关键词做镜像匹配，再识别 CPU/内存做规格匹配

    # OS 关键词识别
    os_keywords = []
    os_patterns = {
        "ubuntu": ["ubuntu"],
        "centos": ["centos"],
        "debian": ["debian"],
        "windows": ["windows", "win"],
        "rocky": ["rocky"],
        "almalinux": ["almalinux", "alma"],
        "openeuler": ["openeuler", "euler"],
        "redhat": ["redhat", "rhel"],
    }
    kw_lower = keyword.lower()

    detected_os = ""
    for os_name, patterns in os_patterns.items():
        for p in patterns:
            if p in kw_lower:
                detected_os = os_name
                # 提取版本号
                ver_match = re.search(r'(\d{2}(?:\.\d+)?)', keyword.replace(" ", ""))
                if ver_match:
                    detected_os += ver_match.group(1).replace(".", "")
                os_keywords.append(detected_os)
                break
        if os_keywords:
            break

    # 规格关键词识别（提取数字部分）
    spec_part = keyword
    # 移除已识别为 OS 的部分
    for okw in os_keywords:
        spec_part = re.sub(re.escape(okw), " ", spec_part, flags=re.IGNORECASE)

    spec_candidate = spec_part.strip() or keyword

    # Step 1: 匹配镜像
    if os_keywords:
        print(f"\n--- 镜像匹配 ---")
        image_id, image_name = cmd_resolve_image(config, os_keywords[0], config_path)
        if image_id:
            updated["image_id"] = image_id
            updated["image_name"] = image_name
    else:
        # 尝试整个关键词去匹配镜像
        print(f"\n--- 镜像匹配 (尝试整体匹配) ---")
        image_id, image_name = cmd_resolve_image(config, keyword, config_path)
        if image_id:
            updated["image_id"] = image_id
            updated["image_name"] = image_name

    # Step 2: 匹配规格
    has_spec = any(c.isdigit() for c in spec_candidate)
    if has_spec or re.search(r'\d+[cC]', spec_candidate):
        print(f"\n--- 规格匹配 ---")
        spec = cmd_resolve_spec(config, spec_candidate, config_path)
        if spec:
            updated["spec_id"] = spec

    print(f"\n{'='*60}")
    print(f"解析完成！可直接执行:")
    print(f"  python scripts/buy_bcc.py buy")
    print(f"{'='*60}")

    return updated


def _write_config_image(image_id: str, image_name: str,
                        config_path: Optional[str] = None) -> None:
    """回写镜像信息到 JSON 配置"""
    path = config_path or _default_config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("image", {})["imageId"] = image_id
        cfg["image"]["imageName"] = image_name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print(f"  [OK] 已回写镜像到: {path}")
    except Exception as e:
        print(f"  [WARN] 回写镜像失败: {e}")


def _write_config_spec(spec: str, config_path: Optional[str] = None) -> None:
    """回写规格到 JSON 配置"""
    path = config_path or _default_config_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("instance", {})["spec"] = spec
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print(f"  [OK] 已回写规格到: {path}")
    except Exception as e:
        print(f"  [WARN] 回写规格失败: {e}")


# ============================================================
# 购买核心逻辑
# ============================================================

def auto_resolve_network(config: Dict[str, str], config_path: Optional[str] = None) -> Dict[str, str]:
    """自动查询并填充缺失的子网/安全组/VPC 信息"""
    from baidubce.services.vpc.vpc_client import VpcClient

    region = config["region"]
    zone = config["zone"]
    cred = BceCredentials(config["ak"], config["sk"])
    vpc_cfg = BceClientConfiguration(credentials=cred, endpoint=f"vpc.{region}.baidubce.com")
    vpc_client = VpcClient(vpc_cfg)

    resolved = dict(config)
    any_auto = False

    # --- 自动选子网 ---
    if not resolved.get("subnet_id"):
        print(f"\n  [AUTO] 查询可用区 {zone} 的子网...")
        try:
            resp = vpc_client.list_subnets(max_keys=50)
            subnets = body_map(resp).get("subnets", [])
            # 优先匹配目标可用区的子网
            matched = [s for s in subnets if s.get("zoneName") == zone]
            if not matched:
                matched = subnets
            if matched:
                picked = matched[0]
                resolved["subnet_id"] = picked["subnetId"]
                resolved["vpc_id"] = picked.get("vpcId", resolved.get("vpc_id", ""))
                print(f"  [AUTO] 自动选择子网: {picked['subnetId']} (可用区: {picked.get('zoneName', '?')})")
                any_auto = True
            else:
                print(f"  [ERROR] 未找到可用子网，请先在控制台创建")
        except Exception as e:
            print(f"  [ERROR] 查询子网失败: {e}")

    # --- 自动选安全组 ---
    if not resolved.get("security_group_id"):
        print(f"  [AUTO] 查询安全组...")
        try:
            resp = vpc_client.list_security_groups(max_keys=50)
            sgs = body_map(resp).get("securityGroups", [])
            if sgs:
                picked = sgs[0]
                resolved["security_group_id"] = picked["securityGroupId"]
                print(f"  [AUTO] 自动选择安全组: {picked['securityGroupId']} ({picked.get('name', 'N/A')})")
                any_auto = True
            else:
                print(f"  [ERROR] 未找到安全组，请先在控制台创建")
        except Exception as e:
            print(f"  [ERROR] 查询安全组失败: {e}")

    # --- 回写到 JSON 配置文件 ---
    if any_auto:
        _write_path = config_path or _default_config_path()
        try:
            with open(_write_path, "r", encoding="utf-8") as f:
                jcfg = json.load(f)
            net = jcfg.setdefault("network", {})
            if resolved.get("subnet_id"):
                net["subnetId"] = resolved["subnet_id"]
            if resolved.get("vpc_id"):
                net["vpcId"] = resolved["vpc_id"]
            if resolved.get("security_group_id"):
                sg_list = net.setdefault("securityGroupIds", [])
                if not sg_list or sg_list[0] != resolved["security_group_id"]:
                    net["securityGroupIds"] = [resolved["security_group_id"]]
            with open(_write_path, "w", encoding="utf-8") as f:
                json.dump(jcfg, f, ensure_ascii=False, indent=2)
            print(f"  [AUTO] 已回写配置到: {_write_path}")
        except Exception as e:
            print(f"  [WARN] 回写配置文件失败: {e}（不影响购买）")

    return resolved


def do_buy(config: Dict[str, str], config_path: Optional[str] = None) -> int:
    """执行购买流程"""

    # 镜像仍需手动指定（涉及操作系统选择）
    if not config.get("image_id"):
        print("[ERROR] 缺少镜像配置 image_id，请编辑 bcc_config.json 或使用 query-images 查看")
        return 1

    client = build_client(config)
    region = config["region"]
    zone = config["zone"]

    # 自动解析子网/安全组（如果配置为空）
    config = auto_resolve_network(config, config_path=config_path)

    # 二次校验（自动解析可能失败）
    for key in ("subnet_id", "security_group_id"):
        if not config[key]:
            print(f"[ERROR] 无法自动获取 {key}，请手动编辑 bcc_config.json 或使用 query-resources 查看")
            return 1

    print("=" * 60)
    print("百度云 BCC 云服务器购买")
    print("=" * 60)

    # Step 1: 显示配置摘要
    print(f"\n[1/5] 购买配置:")
    print(f"  区域:       {region}")
    print(f"  可用区:     {zone}")
    print(f"  实例名:     {config['instance_name']}")
    print(f"  镜像:       {config['image_id']} ({config['image_name']})")
    print(f"  系统盘:     {config['disk_size_gb']}GiB {config['disk_type']}")
    print(f"  子网:       {config['subnet_id']}")
    print(f"  安全组:     {config['security_group_id']}")
    print(f"  公网IP:     {'是' if config['buy_eip'] else '否'} ({config['bandwidth_mbps']}Mbps)")
    print(f"  计费方式:   Postpaid (按量付费)")

    # 密码处理
    admin_pass = config["admin_pass"]
    if not admin_pass:
        print(f"\n  [INFO] 未设置 adminPass，自动生成密码...")
        admin_pass = make_password(12)
    print(f"  登录密码:   {mask_password(admin_pass)}")

    # Step 2: 查询并选择规格
    print(f"\n[2/5] 查询可用规格...")
    resp = client.list_flavor_spec(zone_name=zone)
    data = body_map(resp)
    zone_resources = data.get("zoneResources") or []

    all_specs = []
    target_spec = config.get("spec_id", "")

    for zr in zone_resources:
        if not isinstance(zr, dict):
            continue
        for group in (zr.get("bccResources") or {}).get("flavorGroups") or []:
            for flavor in group.get("flavors") or []:
                if str(flavor.get("productType", "")).lower() == "postpaid":
                    all_specs.append({
                        "spec": flavor.get("spec", ""),
                        "cpu": flavor.get("cpuCount", 0),
                        "mem": flavor.get("memoryCapacityInGB", 0),
                        "disk_types": flavor.get("systemDiskType") or [],
                    })

    if not all_specs:
        print("[ERROR] 未找到可用规格")
        return 1

    picked = None
    if target_spec:
        for s in all_specs:
            if s["spec"] == target_spec:
                picked = s
                break
        if not picked:
            print(f"[WARN] 规格 '{target_spec}' 不可用，自动选择替代规格")

    if not picked:
        all_specs.sort(key=lambda x: (x["cpu"], x["mem"]))
        picked = all_specs[0]

    print(f"  选择规格: {picked['spec']} ({picked['cpu']}核{picked['mem']}G)")

    # 验证磁盘类型兼容性
    supported_disks = set(str(d) for d in picked["disk_types"])
    if supported_disks and config["disk_type"] not in supported_disks:
        fallback = sorted(supported_disks)[0]
        print(f"  [WARN] 磁盘类型不兼容，改为: {fallback}")
        config["disk_type"] = fallback

    # Step 3: 构建请求 (对齐百度云 API 官方字段)
    print(f"\n[3/5] 构建购买请求...")

    payload = {
        "spec": picked["spec"],
        "zoneName": zone,
        "billing": {
            "paymentTiming": "Postpaid",
        },
        "name": config["instance_name"],
        "imageId": config["image_id"],
        "rootDiskSizeInGb": config["disk_size_gb"],
        "rootDiskStorageType": config["disk_type"],
        "subnetId": config["subnet_id"],
        "securityGroupIds": [config["security_group_id"]],
        "adminPass": admin_pass,
        "purchaseCount": config.get("purchase_count", 1),
    }

    if config["buy_eip"]:
        payload["networkCapacityInMbps"] = config["bandwidth_mbps"]

    # Step 4: 执行购买
    print(f"\n[4/5] 调用购买接口...")

    billing = bcc_model.Billing(paymentTiming="Postpaid")

    try:
        resp = client.create_instance_by_spec(
            spec=payload["spec"],
            image_id=payload["imageId"],
            billing=billing,
            root_disk_size_in_gb=payload["rootDiskSizeInGb"],
            root_disk_storage_type=payload["rootDiskStorageType"],
            name=payload["name"],
            zone_name=payload["zoneName"],
            subnet_id=payload["subnetId"],
            security_group_ids=payload["securityGroupIds"],
            admin_pass=payload["adminPass"],
            purchase_count=payload["purchaseCount"],
            internet_charge_type=config.get("internet_charge_type"),
            network_capacity_in_mbs=payload.get("networkCapacityInMbps", 0),
        )

        result_data = body_map(resp)
        instance_id = result_data.get("instanceId")
        if not instance_id:
            iids = result_data.get("instanceIds") or []
            instance_id = iids[0] if iids else ""

        if not instance_id:
            raise RuntimeError(f"响应中无实例ID: {result_data}")

        print(f"  实例ID: {instance_id}")

    except BceHttpClientError as ex:
        err_msg = str(ex)
        print(f"\n{'='*60}")
        print("购买失败!")
        print("=" * 60)

        if "insufficient" in err_msg.lower() or "余额" in err_msg:
            print("原因: 余额不足，请前往控制台充值")
        elif "image arch" in err_msg.lower():
            print("原因: 镜像架构与实例规格不匹配 (ARM vs x86)")
        elif "not create.*mkt image" in err_msg.lower():
            print("原因: 该镜像为市场镜像，不支持API创建")
        elif "root disk size" in err_msg.lower():
            print("原因: 系统盘大小不满足镜像最低要求")
        else:
            print(f"原因: {err_msg}")
        return 2

    # Step 5: 等待 IP 分配
    print(f"\n[5/5] 等待公网IP分配...")

    ip_addr = None
    start = time.time()

    while time.time() - start < 600:
        detail_resp = client.get_instance(instance_id)
        detail = body_map(detail_resp)
        ip_addr = extract_ip(detail)
        if ip_addr:
            break
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(8)

    print()

    # 输出结果
    login_user = infer_login_user(config["image_name"])

    # 构建标准化的结果 JSON（供其他 skill 读取）
    result = {
        "$schema": "bcc-instance-result-v1",
        "status": "SUCCESS",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "provider": "baidu-bce",
        "service": "BCC",
        "instance": {
            "id": instance_id,
            "name": config["instance_name"],
            "spec": picked["spec"],
            "cpu": picked.get("cpu", 0),
            "memory_gb": picked.get("mem", 0),
            "region": region,
            "zone": zone,
            "image_id": config["image_id"],
            "image_name": config["image_name"],
            "disk": f"{config['disk_size_gb']}GiB {config['disk_type']}",
        },
        "network": {
            "public_ip": ip_addr or "",
            "private_ip": "",          # 内网IP（如有）
            "eip_enabled": config["buy_eip"],
            "eip_charge_type": "TRAFFIC_POSTPAID_BY_HOUR" if config["buy_eip"] else "",
            "bandwidth_mbps": config["bandwidth_mbps"] if config["buy_eip"] else 0,
        },
        "access": {
            "ssh_command": f"ssh {login_user}@{ip_addr}" if ip_addr else "",
            "username": login_user,
            "password": admin_pass,
            "port": 22,
        },
        "console_url": f"https://console.bce.baidu.com/bcc/{region}/instance/detail?instanceId={instance_id}",
    }

    print(f"\n{'='*60}")
    print("购买成功!")
    print("=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if ip_addr:
        print(f"\n连接信息:")
        print(f"  SSH:  {result['access']['ssh_command']}")
        print(f"  用户: {result['access']['username']}")
        print(f"  密码: {admin_pass}")
        print(f"  控制台: {result['console_url']}")

    # 保存结果 JSON（输出到配置文件同目录，方便其他 skill 读取）
    config_dir = os.path.dirname(os.path.abspath(config_path)) if config_path else os.path.join(get_skill_root(), "assets")
    output_file = os.path.join(config_dir, "server_info.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: {output_file}")

    return 0


# ============================================================
# CLI 入口
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="百度云 BCC 云服务器购买工具 (Skill 版)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python buy_bcc.py buy                          # 使用 JSON 配置购买
  python buy_bcc.py buy --spec bcc.g8.c8m32      # 覆盖规格
  python buy_bcc.py buy --zone cn-bj-a --name my-server
  python buy_bcc.py show-config                  # 显示当前配置
  python buy_bcc.py query-images                 # 查看可用镜像
  python buy_bcc.py query-specs                  # 查看可用规格
  python buy_bcc.py query-resources              # 查看 VPC/子网/安全组
  python buy_bcc.py resolve-image ubuntu22       # 智能匹配镜像并回写配置
  python buy_bcc.py resolve-spec 8核32G           # 智能匹配规格并回写配置
  python buy_bcc.py resolve "ubuntu 8c32g"       # 一键匹配镜像+规格并回写
        """,
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="buy",
        choices=["buy", "query-images", "query-specs", "query-resources",
                 "show-config", "resolve-image", "resolve-spec", "resolve"],
        help="要执行的命令 (默认: buy)",
    )
    # CLI 覆盖参数 (可选，优先于 JSON 配置)
    parser.add_argument("--spec", help="实例规格，如 bcc.g8.c8m32")
    parser.add_argument("--zone", dest="zoneName", help="可用区，如 cn-bj-a")
    parser.add_argument("--region", help="地域代码，如 bj/gz/su")
    parser.add_argument("--name", help="实例名称")
    parser.add_argument("--config", metavar="PATH", help="指定 bcc_config.json 的路径")
    parser.add_argument("keyword", nargs="?", help="智能匹配关键词 (resolve/resolve-image/resolve-spec 命令使用)")

    args = parser.parse_args()

    # 收集 CLI 覆盖项
    overrides = {}
    if args.spec:
        overrides["spec"] = args.spec
    if args.zoneName:
        overrides["zoneName"] = args.zoneName
    if args.region:
        overrides["region"] = args.region
    if args.name:
        overrides["name"] = args.name

    # 加载配置
    raw_json = load_json_config(args.config)
    config = load_config(overrides, config_path=args.config)

    if args.command == "buy":
        return do_buy(config, config_path=args.config)
    elif args.command == "query-images":
        cmd_query_images(config)
        return 0
    elif args.command == "query-specs":
        cmd_query_specs(config)
        return 0
    elif args.command == "query-resources":
        cmd_query_resources(config)
        return 0
    elif args.command == "show-config":
        cmd_show_config(config, raw_json, config_path=args.config)
        return 0
    elif args.command == "resolve-image":
        if not args.keyword:
            print("用法: python buy_bcc.py resolve-image <镜像关键词>")
            print("示例: python buy_bcc.py resolve-image ubuntu22")
            print("      python buy_bcc.py resolve-image centos7")
            return 1
        img_id, img_name = cmd_resolve_image(config, args.keyword, config_path=args.config)
        if img_id:
            print(f"\n匹配结果: {img_id} | {img_name}")
        return 0
    elif args.command == "resolve-spec":
        if not args.keyword:
            print("用法: python buy_bcc.py resolve-spec <规格关键词>")
            print("示例: python buy_bcc.py resolve-spec 8核32g")
            print("      python buy_bcc.py resolve-spec 4c16g")
            print("      python buy_bcc.py resolve-spec bcc.g8.c8m32")
            return 1
        spec = cmd_resolve_spec(config, args.keyword, config_path=args.config)
        if spec:
            print(f"\n匹配结果: {spec}")
        return 0
    elif args.command == "resolve":
        if not args.keyword:
            print("用法: python buy_bcc.py resolve \"<一句话描述>\"")
            print("示例: python buy_bcc.py resolve \"ubuntu22 8核32g\"")
            print("      python buy_bcc.py resolve \"centos7 4c16g 广州\"")
            return 1
        # 如果关键词包含地域信息，先提取覆盖 region
        kw_lower = (args.keyword or "").lower()
        region_overrides = {"北京": "bj", "广州": "gz", "苏州": "su",
                           "保定": "bd", "武汉": "fwh", "香港": "hkg",
                           "成都": "cd", "南京": "nj"}
        for rname, rcode in region_overrides.items():
            if rname in kw_lower:
                overrides["region"] = rcode
                break
        config = load_config(overrides, config_path=args.config)
        raw_json = load_json_config(args.config)  # refresh after potential override
        cmd_resolve_all(args.keyword, config, config_path=args.config)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
