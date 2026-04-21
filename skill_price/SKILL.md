---
name: baidu-bcc-agent-skill
description: 查询百度云BCC价格，支持跨地域排序、详细计费项和简表输出。
---

# Baidu BCC Agent Skill

## 目录
- `SKILL.md`: 技能入口与说明
- `scripts/`: 可执行脚本
- `references/`: 参考文档与依赖清单
- `assets/`: 静态资源（当前未使用）

`scripts/` 下主要文件：
- `scripts/price_agent.py`: 统一入口代理脚本
- `scripts/setup_env.py`: 全新设备环境检查与依赖安装脚本
- `scripts/unified_bcc_price.py`: BCC 价格查询核心实现

`references/` 下文件：
- `references/requirements.txt`: Python 依赖清单

## 运行环境与依赖
- Python 3.10 及以上（脚本使用了 `X | Y` 类型注解语法）
- 依赖包：
	- requests

## 进入项目目录示例
先进入当前 Skill 根目录（即本文件 `SKILL.md` 所在目录），再执行初始化与查询命令。

Windows PowerShell：

```powershell
cd D:\path\to\baidu_bcc_agent_skill
```

说明：`D:` 只是示例盘符，也可以是 `C:`、`E:` 或任意目录路径。

macOS / Linux：

```bash
cd /path/to/baidu_bcc_agent_skill
```

如果你已经在 Skill 根目录，可直接跳过 `cd`。

## 全新设备初始化（有则跳过，无则安装）
先进入当前 Skill 根目录（即本文件 `SKILL.md` 所在目录）再执行：

Windows PowerShell：

```powershell
python scripts\setup_env.py
```

macOS / Linux：

```bash
python3 scripts/setup_env.py
```

说明：
- `setup_env.py` 会自动检查 Python 版本是否满足 3.10+
- 非虚拟环境下会自动创建并使用项目内 `.venv`
- 依赖安装使用 `pip install -r references/requirements.txt`
- 若依赖已安装且版本满足，pip 会自动跳过

建议运行方式（Windows PowerShell）：

```powershell
.\.venv\Scripts\python.exe scripts\price_agent.py --help
```

建议运行方式（macOS / Linux）：

```bash
./.venv/bin/python scripts/price_agent.py --help
```

## 功能
- `top`: 跨地域价格排序
- `detail`: 单地域详细计费项
- `simple`: 简表输出

## 用法
先进入当前 Skill 根目录（即本文件 `SKILL.md` 所在目录），下面参数都是示例值，可按需替换：

Windows PowerShell：

```powershell
python scripts\price_agent.py top --flavor-spec bcc.ga4.c8m32 --disk-size 240 --eip-charge-mode traffic --region all --top 20
```

```powershell
python scripts\price_agent.py detail --flavor-spec bcc.ga4.c8m32 --disk-size 240 --eip-charge-mode traffic --region bj
```

```powershell
python scripts\price_agent.py simple --flavor-name ga4.c8m32 --disk-size 240 --eip-charge-mode traffic --region bj
```

macOS / Linux：

```bash
python3 scripts/price_agent.py top --flavor-spec bcc.ga4.c8m32 --disk-size 240 --eip-charge-mode traffic --region all --top 20
python3 scripts/price_agent.py detail --flavor-spec bcc.ga4.c8m32 --disk-size 240 --eip-charge-mode traffic --region bj
python3 scripts/price_agent.py simple --flavor-name ga4.c8m32 --disk-size 240 --eip-charge-mode traffic --region bj
```

参数说明：
- --flavor-spec: 实例规格全名，例如 bcc.ga4.c8m32、bcc.c3.c2m4
- --flavor-name: 规格关键字匹配（simple 子命令），例如 ga4.c8m32
- --region: 地域代码，例如 bj、gz、su，也可用 all（仅 top）
- --disk-size: 系统盘大小（GiB）
- --eip-charge-mode: traffic 或 bandwidth
