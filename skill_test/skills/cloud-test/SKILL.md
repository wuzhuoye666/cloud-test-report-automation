---
name: cloud-test
description: 云服务器自动化测试平台，支持多厂商云服务器性能测试。通过SSH远程连接执行TencentBench测试，自动完成配置、安装、执行、监控和结果收集全流程。当用户需要进行服务器性能测试、竞品对比测试、自动化测试部署时使用此skill。
allowed-tools: Read, Write, Bash, Edit
---

# 云服务器自动化测试平台

## 概述

本 Skill 用于自动化执行云服务器性能测试，基于 TencentBench 工具包实现多维度性能验证。

**核心能力：**
- 从本地 assets 上传 TB 安装包和配置文件
- SSH 远程部署测试环境
- 自动修改配置文件参数
- 自动化执行 TB 测试流程
- 实时监控测试进度
- 自动收集和整理测试结果

## 前置资源

本 Skill 依赖以下文件（已存放在 `assets/` 目录）：

| 文件 | 说明 |
|------|------|
| `TencentBench-2.2.1a24.tar.gz` | TB 测试工具安装包 |
| `default.cfg` | 默认配置文件模板 |

## 厂商配置对照表

| 厂商 | 标识 | 规格格式示例 |
|------|------|-------------|
| 腾讯云 | qcloud | SA4, SA5, ITA4, S8, M8 |
| 火山云 | volcengine | ecs.g3i.xlarge |
| 百度云 | bdcloud | bc.g5.xlarge |
| 金山云 | jscloud | km.gn6i.xlarge |
| 阿里云 | aliyun | ecs.g8a.8xlarge |
| 华为云 | huaweiyun | c7.xlarge.2 |
| 微软云 | azure | Standard_D4s_v5 |
| 亚马逊云 | aws | m6i.xlarge |
| 谷歌云 | gcp | n2-standard-4 |

## 系统类型与测试用例对照

| 操作系统 | 测试用例组 | 执行用户 | 配置路径 |
|---------|-----------|---------|---------|
| CentOS | benchmark.compet_single_centos | root | /root/default.cfg |
| Ubuntu | benchmark.compet_single | ubuntu | /home/ubuntu/default.cfg |

## 标准输入格式

用户提供以下机器信息：

```json
{
  "machines": [
    {
      "id": "服务器ID或标识",
      "vendor": "厂商标识(qcloud/volcengine等)",
      "spec": "子机规格(SA4/ecs.g8a.8xlarge等)",
      "ip": "服务器IP地址",
      "username": "SSH用户名(root/ubuntu)",
      "password": "SSH密码",
      "os": "操作系统类型(centos/ubuntu)",
      "area": "地域标识(如gz/sh/bj)"
    }
  ]
}
```

## 工作流程

### Phase 1: 文件上传

1. **连接服务器**：使用提供的 IP、用户名、密码 SSH 连接
2. **上传文件**：
   - 上传 `assets/TencentBench-2.2.1a24.tar.gz` 到服务器
   - 上传 `assets/default.cfg` 到服务器
3. **放置位置**：
   - CentOS: `/root/`
   - Ubuntu: `/home/ubuntu/`

### Phase 2: 配置修改

修改 `default.cfg` 关键字段（实际配置结构）：

```ini
[product]
name = "CVM"

[role]
area = "{地域代码}"        ← 修改为 gz/sh/bj 等
sold_type = "{规格名称}"   ← 腾讯云用 SA4/SA5 等，其他厂商用完整规格如 bc.g5.xlarge
username = "{SSH用户名}"   ← root 或 ubuntu
port = 22
password = "{密码}"
vendor = "{厂商标识}"      ← qcloud, volcengine, aliyun, huaweiyun, bdcloud, jscloud, azure, aws, gcp

[role.client]
ip = "127.0.0.1"

[role.server]
ip = ""

[role.other]
ip = ""
```

**sed 修改命令示例：**
```bash
sed -i 's/^sold_type = .*/sold_type = "SA5"/' default.cfg
sed -i 's/^vendor = .*/vendor = "bdcloud"/' default.cfg
sed -i 's/^area = .*/area = "bj"/' default.cfg
```

### Phase 3: 环境部署

解压并安装 TB：

```bash
tar -xzvf TencentBench-2.2.1a24.tar.gz
cd TencentBench-2.2.1a24/
sudo ./install.sh
```

### Phase 4: 测试执行

**CentOS 系统：**
```bash
cd ~
setsid tb-runner --cfg /root/default.cfg --no-color --run benchmark.compet_single_centos > runtb.log 2>&1 &
```

**Ubuntu 系统：**
```bash
cd ~
sudo setsid tb-runner --cfg /home/ubuntu/default.cfg --no-color --run benchmark.compet_single > runtb.log 2>&1 &
```

### Phase 5: 监控测试

1. **查看实时进度**：
   ```bash
   sudo tail -f runtb.log
   ```

2. **错误定位**：
   ```bash
   sudo cat runtb.log | grep log
   sudo cat runtb.log | grep -i error
   ```

3. **检查测试状态**：
   ```bash
   ps aux | grep tb-runner
   ```

### Phase 6: 结果收集

1. **测试结果路径**：`/tmp/TENCENTBENCH/{测试日期}/`
2. **下载结果**：
   - 直接下载 `.tar.gz` 文件（CentOS 通常自动压缩）
   - Ubuntu 可能需要手动压缩：
     ```bash
     cd /tmp/TENCENTBENCH/{日期}/tb_result
     sudo tar -czvf {规格名}.tar.gz {结果目录}
     ```
3. **本地重命名**：将结果文件重命名为 `{规格名}.tar.gz`

## 输出规范

测试完成后提供：

### 1. 结构化运行信息

```json
{
  "test_summary": {
    "machine_id": "机器标识",
    "spec": "子机规格",
    "vendor": "厂商",
    "status": "completed/failed/running",
    "start_time": "2024-01-01 10:00:00",
    "end_time": "2024-01-01 12:00:00",
    "duration": "2h"
  },
  "test_cases": [
    {"name": "cpu_test", "status": "passed"},
    {"name": "memory_test", "status": "passed"}
  ]
}
```

### 2. 服务器原始测试数据
- 文件路径：本地保存的 `.tar.gz` 文件路径
- 文件大小
- 包含的测试项

### 3. 测试日志摘要
- `runtb.log` 最后 50 行关键信息
- 错误汇总（如有）
- 性能指标预览

## 使用示例

**典型请求：**
> "帮我测试这台腾讯云 SA5 机器，IP是1.2.3.4，账号密码是root/xxx，CentOS系统，广州地域"

**执行流程：**
1. SSH 连接到 1.2.3.4
2. 上传 `TencentBench-2.2.1a24.tar.gz` 和 `default.cfg` 到 /root/
3. 修改 default.cfg：
   - tag = 机器ID
   - area = gz
   - sold_type = SA5
   - vendor = qcloud
4. 解压安装 TB
5. 执行 compet_single_centos 测试
6. 监控进度并收集结果

## 注意事项

1. **AlexNet 工具**：若测试用例包含 alexnet，`default.cfg` 中的 username 和 password 字段必须正确配置
2. **权限问题**：确保 SSH 用户有 sudo 权限执行安装和测试
3. **网络连接**：测试执行期间保持网络稳定，避免 SSH 断开
4. **结果保留**：测试结果务必保存到本地，路径格式：`{vendor}_{spec}_{date}.tar.gz`
5. **存储空间**：确保服务器有足够磁盘空间（建议 50GB+）

## 依赖文件

- `assets/TencentBench-2.2.1a24.tar.gz` - TB 安装包
- `assets/default.cfg` - 默认配置模板
- `references/vendor-configs.md` - 各厂商详细配置参数
- `scripts/deploy_and_run.py` - 自动化部署执行脚本

---

## 长时间测试托管模式（12小时+）

TencentBench 全维度测试通常需要 **10-12小时**。本 Skill 支持**全托管异步执行**模式，无需人工值守。

### 托管模式特点

- **后台执行**：使用 `setsid` + `nohup` 确保 SSH 断开后测试继续
- **定时检查**：每30分钟自动检查测试状态
- **故障恢复**：安装失败、进程崩溃自动重试（最多3次）
- **完成通知**：测试完成后自动通知并收集结果

### 托管模式执行流程

在 Phase 4 测试执行时，使用后台执行命令：

**CentOS：**
```bash
cd ~ && setsid tb-runner --cfg /root/default.cfg --no-color --run benchmark.compet_single_centos > runtb.log 2>&1 &
```

**Ubuntu：**
```bash
cd ~ && sudo setsid tb-runner --cfg /home/ubuntu/default.cfg --no-color --run benchmark.compet_single > runtb.log 2>&1 &
```

**关键特性**：
- `setsid`：创建新会话，脱离终端控制
- `&`：后台执行
- SSH 断开后，`tb-runner` 进程继续在服务器运行

### 状态跟踪机制

**状态文件**：`./test_jobs/{job_id}/status.json`

```json
{
  "job_id": "qcloud-sa5-test001-20260115-143022",
  "machine_id": "test-001",
  "status": "running",
  "progress": "65%",
  "stage": "memory_test",
  "start_time": "2026-01-15T14:30:22",
  "last_check": "2026-01-15T15:00:00",
  "check_count": 3,
  "result_path": "/tmp/TENCENTBENCH/20260115/"
}
```

### 定时检查流程

**检查频率**：每30分钟

**检查命令**：
```bash
# 1. 检查进程是否存在
ps aux | grep tb-runner

# 2. 读取最新进度
tail -50 runtb.log | grep -E "Progress|completed|运行中"

# 3. 检查错误
grep -i "error\|fail\|失败" runtb.log
```

**状态判断**：
- `ps` 找到进程 → 更新 `progress`，`status=running`
- `ps` 找不到进程 + 日志显示完成 → `status=completed`，触发结果收集
- `ps` 找不到进程 + 日志显示错误 → `status=failed`，触发故障恢复
- SSH 连接失败 → 记录警告，下次再试

### 故障自动恢复

| 故障类型 | 检测方式 | AI 分析决策 |
|---------|---------|------------|
| 安装失败 | `install.sh` 返回非0 | 分析错误日志，判断是网络/依赖/权限问题，针对性修复后重试 |
| 配置错误 | 启动时 TB 报错 | 分析错误信息，自动修正配置参数后重启 |
| 进程崩溃 | `ps` 找不到 tb-runner | 查看日志分析崩溃原因（内存/磁盘/工具错误），修复后重启 |
| 网络中断 | SSH 连接超时 | 标记为"等待网络"，稍后自动重试检查 |
| 磁盘满 | `df` 显示空间不足 | 清理临时日志文件，释放空间后重启 |
| AlexNet 错误 | 日志中出现 alexnet 失败 | 检查 default.cfg 中的 username/password 是否正确 |

**AI 故障恢复流程**：
```
1. 检测故障 → 读取错误日志
2. AI 分析 → 判断故障类型和原因
3. 决策修复 → 选择修复策略：
   - 配置错误 → 自动修正配置
   - 依赖缺失 → 安装依赖后重试
   - 权限不足 → 检查 sudo 配置
   - 资源不足 → 清理空间或扩容
   - 无法自动修复 → 通知人工介入
4. 执行修复 → 应用修复措施
5. 重启测试 → 重新启动 tb-runner
6. 持续监控 → 继续定时检查
```

**不重试的情况**：
- 连续相同错误超过阈值（怀疑是系统性问题）
- 错误日志显示需要人工介入（如硬件故障）
- 用户明确标记暂停修复

### 完成检测与通知

**完成标志**（满足任一）：
1. 日志中出现 "Test completed" 或 "全部测试完成"
2. 结果文件生成：`/tmp/TENCENTBENCH/{日期}/{结果}.tar.gz`
3. `tb-runner` 进程正常退出

**自动执行结果收集（Phase 6）**：
```bash
# 下载结果到本地
scp {user}@{ip}:/tmp/TENCENTBENCH/{date}/{result}.tar.gz \
  ./test_results/{vendor}_{spec}_{machine_id}_{date}.tar.gz

# 生成本地路径记录
echo "结果已保存: ./test_results/{filename}.tar.gz"
```

### 使用方式

**启动托管测试：**
> "帮我后台测试这台腾讯云 SA5 机器，IP是1.2.3.4..."

Skill 执行：
1. 生成 Job ID
2. 执行 Phase 1-4（上传、配置、安装、后台启动）
3. 创建状态文件
4. 返回：
   ```
   ✓ 测试已在后台启动（预计12小时）
   ✓ Job ID: qcloud-sa5-test001-20260115-143022
   ✓ 每30分钟自动检查状态
   
   查看状态: ./scripts/check.py --job {job_id}
   ```

**查看进度：**
> "查看测试进度 {job_id}"

Skill 读取 `status.json`，显示：
```
任务: qcloud-sa5-test001-20260115-143022
状态: 运行中 (65%)
当前阶段: memory_test
已运行: 8小时
上次检查: 10分钟前
```

**测试完成：**
```
✓ 测试已完成！
结果: ./test_results/qcloud_SA5_test-001_20260115.tar.gz
大小: 15.2MB
总耗时: 11小时45分钟
```

### 托管模式目录结构

```
skill_test/
├── test_jobs/                      # 任务状态目录
│   └── {job_id}/
│       ├── config.json             # 任务配置
│       ├── status.json             # 实时状态
│       └── runtb.log               # 同步的远程日志
├── test_results/                   # 测试结果目录
│   └── {vendor}_{spec}_{id}_{date}.tar.gz
└── .codebuddy/skills/cloud-test/
    └── scripts/
        └── check.py                # 状态检查脚本
```

### 故障处理指南

**如果测试失败（已重试3次）：**
```
✗ 测试失败

最后错误: tb-runner 进程异常退出
日志片段: [显示最后20行]

建议操作:
1. 手动登录检查: ssh {user}@{ip}
2. 查看完整日志: tail -100 ~/runtb.log
3. 检查磁盘空间: df -h
4. 检查内存使用: free -h
```

**如果需要人工重启：**
```bash
# 进入任务目录
cd test_jobs/{job_id}

# 手动检查
ssh {user}@{ip} "tail -50 runtb.log"

# 手动重启测试
ssh {user}@{ip} "cd ~ && setsid tb-runner --cfg {cfg} --run {case} > runtb.log 2>&1 &"

# 重置状态
./scripts/check.py --job {job_id} --reset
```
