---
name: skill-info
description: 云端测试结果下载器。自动从云服务器下载测试生成的原始数据包，完好无损保存到本地供其他项目调用。
allowed-tools: Read, Write, Bash, Edit
---

# Skill-Info 测试结果下载器

## 功能

从云服务器下载 TencentBench 测试结果文件，原样保存到本地。

## 本地存储位置

```
skill_info/
└── data/
    └── downloads/
        └── {vendor}_{spec}_{machine_id}_{date}.tar.gz
```

**文件名格式：**
```
{厂商}_{规格}_{机器ID}_{日期}.tar.gz

示例：
qcloud_SA5_test-001_20260115.tar.gz
aliyun_ecs.g8a.8xlarge_srv-01_20260115.tar.gz
```

## 输入参数

```json
{
  "ip": "服务器IP",
  "username": "SSH用户名",
  "password": "SSH密码",
  "vendor": "厂商(qcloud/aliyun等)",
  "spec": "子机规格",
  "machine_id": "机器标识",
  "remote_date": "测试日期(如20260115)",
  "result_dir": "远程结果目录名"
}
```

## 工作流程

1. **连接服务器**：SSH 登录目标机器
2. **定位文件**：查找 `/tmp/TENCENTBENCH/{日期}/` 下的结果
3. **创建本地目录**：`skill_info/data/downloads/`
4. **下载文件**：使用 SCP 原样下载 `.tar.gz` 文件
5. **重命名**：按规范命名并保存

## 下载命令

**CentOS（已自动压缩）：**
```bash
scp {username}@{ip}:/tmp/TENCENTBENCH/{date}/{result}.tar.gz \
  skill_info/data/downloads/{vendor}_{spec}_{id}_{date}.tar.gz
```

**Ubuntu（需先手动压缩）：**
```bash
# 远程压缩
ssh {username}@{ip} "cd /tmp/TENCENTBENCH/{date}/tb_result && sudo tar -czvf {result}.tar.gz {result}"

# 下载
scp {username}@{ip}:/tmp/TENCENTBENCH/{date}/tb_result/{result}.tar.gz \
  skill_info/data/downloads/{vendor}_{spec}_{id}_{date}.tar.gz
```

## 输出

- **本地路径**：`skill_info/data/downloads/{文件名}.tar.gz`
- **文件大小**：下载完成后显示
- **状态**：成功/失败

## 供其他项目调用

下载完成后，其他项目可以直接读取：
```
skill_info/data/downloads/qcloud_SA5_test-001_20260115.tar.gz
```

## 使用示例

> "下载这台腾讯云 SA5 机器的测试结果，IP是1.2.3.4，日期是20260115"

执行：
1. SSH 连接 1.2.3.4
2. 找到 `/tmp/TENCENTBENCH/20260115/` 下的结果
3. 下载到 `skill_info/data/downloads/qcloud_SA5_xxx_20260115.tar.gz`
4. 返回本地路径
