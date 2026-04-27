---
name: skill-destroy
description: 百度智能云BCC云服务器实例管理工具。当用户需要查询、关机/停止、销毁/删除百度云BCC实例时触发此skill。支持单个和批量操作，包含智能模式（先关机再销毁）。适用于运维管理、资源清理、成本优化等场景。关键词：百度云、BCC、云服务器、销毁实例、关机、释放实例。
---

# Baidu BCC Manager - 百度智能云云服务器管理

## Overview

此 skill 提供对百度智能云 BCC (Baidu Cloud Compute) 云服务器的完整生命周期管理能力，包括查询实例列表、停止(关机)实例、释放(销毁删除)实例等核心操作。基于百度官方 Python SDK (bce-python-sdk) 实现，通过交互式命令行界面提供安全的操作流程。

## Quick Start

### 前置条件

1. **安装依赖**（使用 skill 根目录的依赖清单）：
   ```bash
   pip install -r requirements.txt
   ```

2. 配置 AK/SK 凭证（二选一）：

**方式 A — `.env` 文件（推荐）：**

脚本会**自动按优先级逐级向上查找** `.env` 文件，找到即止：

```
搜索顺序:
1) scripts/.env              ← 脚本同目录
2) skill-destroy/.env        ← skill 根目录 (最常用)
3) 项目根目录/.env            ← 上级项目目录
4) 当前工作目录/.env           ← 运行时 cwd
```

```bash
cp .env.example .env
# 编辑 .env，填入实际值
```

| 配置项 | 说明 | 获取地址 |
|--------|------|----------|
| `BCE_AK` | Access Key ID | https://console.bce.baidu.com/iam/#/iam/accesslist |
| `BCE_SK` | Secret Access Key | 同上 |
| `BCE_HOST` | 地域端点（可选，默认北京） | 见下方地域对照表 |

**方式 B — 环境变量（优先级最高）：**
```bash
export BCE_AK="your-ak" BCE_SK="your-sk"
export BCE_HOST="http://bcc.bj.baidubce.com"
```

> 加载优先级：环境变量 > `.env` 文件（取第一个找到的）。

3. **地域端点选择**（必须与实例所在地域一致）：

| 地域 | Endpoint |
|------|----------|
| 北京 | `http://bcc.bj.baidubce.com` |
| 广州 | `http://bcc.gz.baidubce.com` |
| 苏州 | `http://bcc.su.baidubce.com` |
| 保定 | `http://bcc.bd.baidubce.com` |

### 运行脚本

```bash
python scripts/bcc_manager.py
```

## Core Capabilities

### 1. 查询实例列表

列出账号下所有 BCC 实例的详细信息，包括实例ID、名称、状态(Running/Stopped)、内网IP、公网IP、计费方式(Postpaid/Prepaid)。

- 脚本启动后选择菜单项 `1`
- 自动分页获取全部实例（每页最多100条）

### 2. 停止/关机实例 (`stop_instance`)

支持两种关机模式和可选的"关机不计费"功能。

**参数说明：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `instance_id` | string | 目标实例ID，格式为 `i-xxxxx` |
| `force_stop` | bool | `False`=正常关机(推荐)，`True`=强制断电(可能丢数据) |
| `stopWithNoCharge` | bool | 仅Postpaid有效，`True`=停止后不收费 |

**调用示例（代码级）：**
```python
from scripts.bcc_manager import create_bcc_client, stop_instance
client = create_bcc_client()
stop_instance(client, "i-abc123", force_stop=False, no_charge=True)
```

**注意事项：**
- 实例状态必须是 Running 才能执行停止操作
- 强制关机等同于物理断电，可能导致未写入磁盘的数据丢失
- Prepaid（包年包月）实例停止后仍继续计费

### 3. 释放/销毁/删除实例 (`release_instance`)

永久删除云服务器实例，**此操作不可逆**。

**参数说明：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `instance_id` | string | 目标实例ID |
| `related_resources` | bool | 是否同时释放关联资源(EIP/CDS/快照/ENI) |

**关联释放资源类型：**

| 资源类型 | 说明 |
|----------|------|
| EIP | 弹性公网IP |
| CDS | 数据盘 |
| SNAP | 快照 |
| ENI | 弹性网卡 |

**重要限制：**
- Postpaid（按量付费）实例可直接释放
- Prepaid（包年包月）实例需先转为按量付费或使用专门的预付费提前释放接口
- 某些状态下可能需要先停止实例才能释放

### 4. 批量操作

支持批量停止和批量释放多个实例：

- **批量停止**: 输入多个实例序号（逗号分隔），如 `1,3,5`
- **批量释放**: 同上，一次性销毁多台实例
- 所有批量操作前均需二次确认（输入 `YES`）

### 5. 智能模式（推荐）

自动执行两步流程：

1. **检查状态并关机** — 若实例处于Running状态，先执行正常关机；已停止则跳过
2. **等待+销毁** — 等待5秒确保关机完成，然后执行释放操作

适用于需要一键完成"关机→销毁"全流程的场景。

## Workflow Decision Tree

```
用户请求管理百度云BCC实例？
│
├─ 仅查询 → 运行脚本 → 选择菜单 1 → 展示实例列表
│
├─ 关机/停止 → 运行脚本 → 选择菜单 2 或 4 → 选择目标 → 确认模式 → 执行
│   ├─ 单个实例 → 菜单 2
│   └─ 批量实例 → 菜单 4
│
├─ 销毁/删除 → 运行脚本 → 选择菜单 3 或 5 → 选择目标 → 二次确认 → 执行
│   ├─ 单个实例 → 菜单 3
│   ├─ 批量实例 → 菜单 5
│   └─ 一键完成 → 菜单 6 (智能模式: 先关机再销毁)
│
└─ 需要编程调用 → 导入模块函数直接使用 (见 Core Capabilities 各节)
```

## Error Handling

脚本内置了完善的错误处理机制：

| 错误信息 | 可能原因 | 解决方案 |
|----------|----------|----------|
| `InvalidInstanceState` | 实例状态不允许当前操作 | 检查实例是否在正确的状态(Running可停止，Stopped可释放) |
| `InstanceNotFound` / `not found` | 实例不存在或已被删除 | 确认实例ID正确，或该实例已被他人删除 |
| 包含 `prepaid` / `Prepaid` | 预付费实例无法直接释放 | 转为按量付费或等待合约到期 |
| 连接超时/网络错误 | 网络问题或端点错误 | 检查网络连接，确认HOST与实例地域一致 |
| 权限不足(AK/SK错误) | AK/SK无效或权限不够 | 在IAM控制台确认权限策略含 BCC FullAccess |

## Safety Guidelines

⚠️ **关键安全提醒：**

1. **数据备份** — 销毁前务必将重要数据备份到 BOS 对象存储或其他位置
2. **二次确认** — 所有危险操作（关机/销毁）均需输入 `YES` 大写确认
3. **环境区分** — 操作前仔细核对实例ID和名称，避免误删生产环境实例
4. **预付费注意** — 包年包月实例有合约限制，提前了解违约规则
5. **凭证安全** — AK/SK 属于敏感信息，不要提交到版本控制系统中

## Resources

### 根目录

| 文件 | 用途 |
|------|------|
| `SKILL.md` | Skill 定义文件（required） |
| `requirements.txt` | Python 依赖清单（bce-python-sdk>=0.8.27） |
| `.env` | 凭证配置文件（用户自建，填入 AK/SK） |

**安装依赖：**
```bash
pip install -r <skill-path>/requirements.txt
```

**配置凭证：**
```bash
# 方式A: 创建 .env 文件（脚本会自动查找）
cat > <skill-path>/.env << 'EOF'
BCE_AK=your-access-key-id
BCE_SK=your-secret-access-key
EOF

# 方式B: 设置环境变量(优先级更高)
export BCE_AK="your-ak" BCE_SK="your-sk"
```

### scripts/

| 文件 | 用途 |
|------|------|
| `bcc_manager.py` | 核心交互式管理工具，包含所有功能的完整实现（~460行）|

**运行脚本：**
```bash
python <skill-path>/scripts/bcc_manager.py
```

也可作为模块导入使用：
```python
import sys
sys.path.insert(0, '<skill-path>/scripts')
from bcc_manager import create_bcc_client, list_all_instances, stop_instance, release_instance
```
