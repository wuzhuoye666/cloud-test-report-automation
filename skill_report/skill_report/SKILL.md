---
name: skill_report
description: 云主机性能测试报告生成工具。当用户需要根据性能测试数据（如 UnixBench、stress-ng、Redis、OpenSSL、FFmpeg、Linpack 等跑分数据）生成可视化的性能对比报告时，使用此 skill。支持输入 JSON 格式测试数据，自动生成包含图表、诊断分析、结论建议的 PDF 和 Markdown 报告。即使用户只是说"帮我出一份报告"、"把测试结果整理一下"、"生成性能分析"，也应触发此 skill。
---

# 云主机性能测试报告生成 Skill

## 功能概述

接收上游测试模块产出的 JSON 格式性能数据，自动完成以下工作：
1. 数据解析与清洗
2. 可视化图表生成（柱状图、雷达图）
3. 自动诊断与性能评级
4. 输出完整的性能对比报告（PDF + Markdown）

## 输入格式

输入为 JSON 文件，结构如下：

```json
{
  "task_id": "任务ID",
  "visualizations": {
    "测试类别名": {
      "chart_type": "bar",
      "series": [
        { "name": "指标名", "data": [数值] }
      ]
    }
  },
  "diagnosis_hints": {
    "测试路径/指标名": { "value": 数值, "unit": "单位" }
  },
  "analysis_summary": {
    "chart_count": 图表数,
    "test_count": 测试数,
    "metric_count": 指标总数
  }
}
```

## 输出

- `report.pdf` — 完整的可视化性能报告（含图表、表格、结论）
- `report.md` — Markdown 版本，方便集成到其他系统

## 执行步骤

1. 读取 `references/` 目录下的测试数据 JSON 文件
2. 运行 `scripts/generate_report.py`，传入数据文件路径
3. 脚本会在当前目录生成 `report.pdf` 和 `report.md`

```bash
cd .codebuddy/skills/skill_report
python scripts/generate_report.py --input references/test-data.json --output-dir ./output
```

## 报告结构模板

生成的报告 ALWAYS 使用以下结构：

```
# 云主机性能测试报告
## 一、测试概览
  - 任务ID、测试时间、测试项数、指标总数
## 二、综合性能雷达图
  - 各维度归一化评分雷达图
## 三、分项测试详情
  - 每个测试类别一个小节，含柱状图 + 数据表格
## 四、性能诊断与分析
  - 自动诊断结果：优秀/关注/正常
## 五、结论与建议
  - 综合评价 + 优化建议
```

## 依赖

- Python 3.8+
- matplotlib
- markdown（可选，用于 MD 转换）

## 注意事项

- 图表中文字体需要使用系统中文字体（如 SimHei、Noto Sans CJK），脚本中已做自动检测
- 大数值自动格式化（如 241435650 → 241.4M）
- 颜色方案已预设，无需手动配置
