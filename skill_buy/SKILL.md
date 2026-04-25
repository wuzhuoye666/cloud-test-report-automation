---
name: baidu-bcc-buyer
description: 购买和管理百度云BCC云服务器实例。当用户需要购买百度云服务器、查询BCC实例规格/镜像/价格/网络资源时使用此skill。支持按量付费购买、自动解析子网安全组、自然语言智能匹配镜像规格、多地域价格对比。
---

# 百度云 BCC 云服务器购买 Skill

## Overview

通过百度云 BCC API 实现云服务器的自动化购买。支持**自然语言智能匹配**——用户只需说"ubuntu22 8核32g"，即可自动查 API 匹配最优镜像和规格，回写配置后一键下单。

## Prerequisites

### 环境变量（必填）

| 变量 | 说明 |
|------|------|
| `BCE_AK` | 百度云 Access Key ID |
| `BCE_SK` | 百度云 Secret Access Key |

设置方式：
- Windows PowerShell: `$env:BCE_AK="your_ak"; $env:BCE_SK="your_sk"`
- Linux/Mac: `export BCE_AK=your_sk && export BCE_SK=your_sk`
- 或在项目根目录创建 `.env` 文件写入这两行

### Python 依赖

```bash
pip install python-dotenv baidu-bce-sdk
```

## Workflow（推荐：智能模式）

用户只需用自然语言描述需求，skill 自动完成其余步骤：

```
用户说: "帮我买一台 ubuntu 8核32G 的服务器"
        ↓
  Step 1: 智能解析 → resolve "ubuntu 8核32g"
    ├─ 自动识别 OS=Ubuntu 22.04 → 查 API 匹配最佳镜像ID
    └─ 自动识别 规格=8C/32G → 查可用区规格列表匹配 spec
        ↓ (结果自动回写 bcc_config.json)
  Step 2: 一键购买 → buy
    ├─ 加载配置 + AK/SK
    ├─ 自动填充子网/安全组(如为空)
    └─ 调用 createInstanceBySpec API → 等待IP分配 → 输出连接信息
```

### 命令参考

```bash
# ===== 智能模式（推荐） =====

# 一键解析 + 回写配置（一句话搞定镜像+规格）
python scripts/buy_bcc.py resolve "ubuntu22 8核32g"
python scripts/bcc.py resolve "centos7 4c16g 广州"       # 含地域信息
python scripts/buy_bcc.py resolve "windows 2022 8核16g"

# 单独匹配镜像
python scripts/buy_bcc.py resolve-image ubuntu22         # 关键词模糊匹配
python scripts/buy_bcc.py resolve-image centos7
python scripts/buy_bcc.py resolve-image win2022

# 单独匹配规格
python scripts/buy_bcc.py resolve-spec 8核32g           # 支持多种写法
python scripts/buy_bcc.py resolve-spec 4c16g             # 4c16g / c4m16 / C4M16 均可
python scripts/buy_bcc.py resolve-spec bcc.g8.c8m32      # 直接写完整spec名也行

# ===== 手动模式 =====

# 购买（使用 JSON 配置或 CLI 参数）
python scripts/buy_bcc.py buy                            # 用配置文件中的参数
python scripts/buy_bcc.py buy --spec bcc.g8.c8m32        # 覆盖规格
python scripts/buy_bcc.py buy --zone cn-bj-a              # 覆盖可用区

# 查询资源
python scripts/buy_bcc.py query-images                   # 查看所有可用镜像
python scripts/buy_bcc.py query-specs                    # 查看目标可用区规格
python scripts/buy_bcc.py query-resources                # 查看 VPC/子网/安全组
python scripts/buy_bcc.py show-config                    # 显示当前配置
```

### 智能匹配支持的自然语言格式

| 需求 | 用户输入示例 | 解析结果 |
|------|-------------|---------|
| Ubuntu 22.04 + 8核32G | `"ubuntu22 8核32g"` | 镜像=m-xxx, 规格=bcc.e2.c8m32 |
| CentOS 7 + 4核16G | `"centos7 4c16g"` | 镜像=m-xxx, 规格=bcc.e2.c4m16 |
| Windows 2019 + 8核16G | `"win2019 8c16g"` | 镜像=m-xxx, 规格=bcc.e2.c8m16 |
| 指定地域 | `"ubuntu 北京 2核4G"` | region=bj, 其余同上 |
| 直接指定规格名 | `"bcc.g8.c8m32"` | 精确匹配该规格 |

**规格关键词支持:** `8核32g` / `8c32g` / `8C32G` / `8 core 32gb` / `c8m32` 等多种写法

**OS关键词支持:** ubuntu/centos/debian/windows(win)/rocky/almalinux/openeuler/redhat(rhel)，可带版本号

## Configuration Reference

`assets/bcc_config.json` 结构：

```json
{
  "region": { "value": "bj" },
  "zoneName": { "value": "cn-bj-d" },
  "instance": { "spec": "", "name": "bcc-server", "purchaseCount": 1 },
  "image": { "imageId": "", "imageName": "" },
  "systemDisk": { "storageType": "SSD_Enhanced", "sizeInGb": 100 },
  "network": { "subnetId": "", "vpcId": "", "securityGroupIds": [] },
  "eip": { "enabled": true, "bandwidthInMbps": 100, "internetChargeType": "TRAFFIC_POSTPAID_BY_HOUR" },
  "adminPass": ""
}
```

**字段填充优先级：**

| 字段 | 来源 | 说明 |
|------|------|------|
| AK/SK | **环境变量** BCE_AK/BCE_SK | 必须设置 |
| image.imageId | `resolve` 命令自动填充 | 从API智能匹配 |
| instance.spec | `resolve` 命令自动填充 | 从API智能匹配 |
| network.subnetId | 购买时**自动查询填充** | 选目标可用区的第一个 |
| network.securityGroupIds | 购买时**自动查询填充** | 选第一个安全组 |
| adminPass | 留空则自动生成12位随机密码 | - |

**总结：用户真正需要手动设置的只有 AK/SK，其余均可自动化！**

## Output: server_info.json

购买成功后自动输出到 `assets/server_info.json`（与配置文件同目录），结构如下：

```json
{
  "$schema": "bcc-instance-result-v1",
  "status": "SUCCESS",
  "timestamp": "2026-04-25T13:08:00+0800",
  "provider": "baidu-bce",
  "service": "BCC",
  "instance": {
    "id": "i-ZJCtvN9A",
    "name": "bcc-server",
    "spec": "bcc.e1.c2m2",
    "cpu": 2,
    "memory_gb": 2,
    "region": "bj",
    "zone": "cn-bj-d",
    "image_id": "m-wB3qoLhR",
    "image_name": "Ubuntu 22.04 LTS",
    "disk": "40GiB SSD_Enhanced"
  },
  "network": {
    "public_ip": "192.168.16.3",
    "private_ip": "",
    "eip_enabled": true,
    "eip_charge_type": "TRAFFIC_POSTPAID_BY_HOUR",
    "bandwidth_mbps": 100
  },
  "access": {
    "ssh_command": "ssh ubuntu@192.168.16.3",
    "username": "ubuntu",
    "password": "Perf@host#2024",
    "port": 22
  },
  "console_url": "https://console.bce.baidu.com/bcc/bj/instance/detail?instanceId=i-ZJCtvN9A"
}
```

**其他 skill 读取示例：**
```python
import json
with open("server_info.json") as f:
    info = json.load(f)
# 直接获取连接信息
ssh_cmd = info["access"]["ssh_command"]       # ssh ubuntu@192.168.16.3
host = info["network"]["public_ip"]            # 192.168.16.3
user = info["access"]["username"]              # ubuntu
pwd = info["access"]["password"]               # Perf@host#2024
```

## Resources

### scripts/
- **buy_bcc.py**: 核心脚本，集成 7 个命令：
  - `resolve` — 一键智能匹配镜像+规格
  - `resolve-image` — 单独智能匹配镜像
  - `resolve-spec` — 单独智能匹配规格
  - `buy` — 执行购买（含自动子网/安全组解析）
  - `query-images` / `query-specs` / `query-resources` / `show-config`

### assets/
- **bcc_config.json**: 默认配置模板，运行时被 `resolve` 命令自动回写
