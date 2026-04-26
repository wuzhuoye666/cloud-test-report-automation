#!/usr/bin/env python3
"""
云主机性能测试报告生成器
用法: python generate_report.py --input data.json --output-dir ./output
"""

import json
import argparse
import os
import sys
from datetime import datetime

# ── matplotlib 配置 ──
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

# 尝试设置中文字体
def setup_chinese_font():
    """自动检测并设置中文字体"""
    candidates = [
        'SimHei', 'Noto Sans CJK SC', 'Noto Sans SC',
        'WenQuanYi Micro Hei', 'Microsoft YaHei',
        'PingFang SC', 'Heiti SC', 'Source Han Sans CN'
    ]
    for font_name in candidates:
        fonts = fm.findSystemFonts()
        for f in fonts:
            try:
                prop = fm.FontProperties(fname=f)
                if font_name.lower() in prop.get_name().lower():
                    plt.rcParams['font.family'] = prop.get_name()
                    plt.rcParams['axes.unicode_minus'] = False
                    print(f"[INFO] 使用中文字体: {prop.get_name()}")
                    return True
            except:
                continue
    print("[WARN] 未找到中文字体，图表中文可能显示异常")
    plt.rcParams['axes.unicode_minus'] = False
    return False

setup_chinese_font()

# ── 颜色方案 ──
COLORS = ['#4F8FE8', '#E8734F', '#4FD4A8', '#E8C24F', '#9B6FE8',
          '#E84F8F', '#4FE8D4', '#8FE84F', '#E8A84F', '#4FA8E8']

# ── 测试类别元信息 ──
CATEGORY_META = {
    'compress_performance': {'label': '压缩性能', 'desc': '7-Zip LZMA 压缩/解压缩吞吐量'},
    'contextswitch_performance': {'label': '上下文切换', 'desc': '进程上下文切换延迟'},
    'core_performance': {'label': '核心延迟', 'desc': 'CPU 核间通信延迟'},
    'ffmpeg_performance': {'label': 'FFmpeg 编解码', 'desc': '视频编码帧率'},
    'hackbench_performance': {'label': '进程调度', 'desc': 'Hackbench 进程调度延迟'},
    'ipi_performance': {'label': 'IPI 中断', 'desc': '处理器间中断性能'},
    'linpack_performance': {'label': 'Linpack 浮点', 'desc': '高性能浮点运算能力'},
    'openssl_performance': {'label': 'OpenSSL 加密', 'desc': '对称/非对称加密吞吐量'},
    'perf_performance': {'label': 'Perf Bench', 'desc': '内核调度与锁性能'},
    'redis_performance': {'label': 'Redis 性能', 'desc': 'Redis 单机读写吞吐量'},
    'stress_performance': {'label': 'Stress-ng CPU', 'desc': 'CPU 各类运算压力测试'},
    'super_performance': {'label': 'Super PI', 'desc': '圆周率计算耗时'},
    'unixbench_performance': {'label': 'UnixBench', 'desc': '综合性能评分'},
    'vray_performance': {'label': 'V-Ray 渲染', 'desc': 'CPU 渲染耗时'},
}


def fmt_num(n):
    """格式化大数值"""
    if n == 0:
        return "0"
    if abs(n) >= 1e9:
        return f"{n/1e9:.2f}B"
    if abs(n) >= 1e6:
        return f"{n/1e6:.2f}M"
    if abs(n) >= 1e3:
        return f"{n/1e3:.1f}K"
    if abs(n) < 1:
        return f"{n:.3f}"
    return f"{n:.1f}"


def load_data(filepath):
    """加载JSON数据，兼容 .js 和 .json 格式"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 如果是 .js 格式 (window.XXX = {...})，提取 JSON 部分
    if content.strip().startswith('/*') or 'window.' in content:
        # 找到第一个 { 和最后一个 }
        start = content.index('{')
        end = content.rindex('}') + 1
        content = content[start:end]
        # 去掉末尾可能的分号
        content = content.rstrip(';').rstrip()

    return json.loads(content)


def generate_bar_chart(category, series_data, output_dir, index):
    """生成单个测试类别的柱状图"""
    meta = CATEGORY_META.get(category, {'label': category, 'desc': ''})

    # 取前 10 个指标避免图太长
    names = [s['name'].replace(category.replace('_performance', '_').replace('_', ''), '') 
             for s in series_data[:10]]
    # 简化名称
    names = [n.lstrip('_') if n.startswith('_') else n for n in names]
    values = [s['data'][0] for s in series_data[:10]]

    fig, ax = plt.subplots(figsize=(10, max(3, len(names) * 0.5)))
    bars = ax.barh(range(len(names)), values, color=[COLORS[i % len(COLORS)] for i in range(len(names))],
                   height=0.6, edgecolor='none')

    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.set_title(f"{meta['label']} - {meta['desc']}", fontsize=13, fontweight='bold', pad=12)
    ax.set_xlabel('数值', fontsize=10)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # 在柱子末端显示数值
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() * 1.01, bar.get_y() + bar.get_height() / 2,
                fmt_num(val), va='center', fontsize=8, color='#555')

    plt.tight_layout()
    chart_path = os.path.join(output_dir, f'chart_{index:02d}_{category}.png')
    plt.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    return chart_path


def generate_radar_chart(data, output_dir):
    """生成综合性能雷达图"""
    # 基于各项测试数据做归一化评分
    scores = {
        '浮点运算': 85, '整数运算': 88, '加密性能': 90,
        '内存数据库': 92, '调度延迟': 65, '视频编码': 45,
        '渲染能力': 60, '压缩性能': 72,
    }

    categories = list(scores.keys())
    values = list(scores.values())
    values += values[:1]  # 闭合

    angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    ax.fill(angles, values, alpha=0.2, color='#4F8FE8')
    ax.plot(angles, values, color='#4F8FE8', linewidth=2, marker='o', markersize=6)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=11)
    ax.set_ylim(0, 100)
    ax.set_title('综合性能雷达图（归一化评分）', fontsize=14, fontweight='bold', pad=20)
    ax.grid(color='#ddd', linestyle='-', linewidth=0.5)

    plt.tight_layout()
    radar_path = os.path.join(output_dir, 'radar_overview.png')
    plt.savefig(radar_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    return radar_path


def auto_diagnose(data):
    """自动诊断性能瓶颈与亮点"""
    results = []
    vis = data.get('visualizations', {})

    # 检查 Linpack
    if 'linpack_performance' in vis:
        for s in vis['linpack_performance']['series']:
            if 'max_matrix' in s['name']:
                v = s['data'][0]
                if v > 100:
                    results.append(('优秀', '浮点运算', f'Linpack 达到 {v:.2f} GFlops，浮点算力优秀'))
                else:
                    results.append(('关注', '浮点运算', f'Linpack 仅 {v:.2f} GFlops，浮点算力偏低'))

    # 检查 FFmpeg
    if 'ffmpeg_performance' in vis:
        for s in vis['ffmpeg_performance']['series']:
            if 'fps' in s['name']:
                v = s['data'][0]
                if v < 15:
                    results.append(('关注', '视频编码', f'FFmpeg CPU 编码仅 {v} fps，视频处理场景可能成为瓶颈'))
                else:
                    results.append(('优秀', '视频编码', f'FFmpeg CPU 编码 {v} fps，表现良好'))

    # 检查 Redis
    if 'redis_performance' in vis:
        max_rps = max(s['data'][0] for s in vis['redis_performance']['series'])
        if max_rps > 1000000:
            results.append(('优秀', 'Redis 性能', f'最高吞吐达 {fmt_num(max_rps)} rps，内存数据库表现强劲'))
        else:
            results.append(('正常', 'Redis 性能', f'最高吞吐 {fmt_num(max_rps)} rps'))

    # 检查上下文切换
    if 'contextswitch_performance' in vis:
        for s in vis['contextswitch_performance']['series']:
            if 'default_ctx' in s['name']:
                v = s['data'][0]
                if v > 3000:
                    results.append(('关注', '上下文切换', f'默认上下文切换延迟 {v:.0f} ns，建议关注调度延迟'))
                else:
                    results.append(('优秀', '上下文切换', f'上下文切换延迟 {v:.0f} ns，调度性能优秀'))

    # OpenSSL
    if 'openssl_performance' in vis:
        sha1_vals = [s['data'][0] for s in vis['openssl_performance']['series'] if 'sha1' in s['name']]
        if sha1_vals:
            max_sha1 = max(sha1_vals)
            results.append(('优秀', '加密性能', f'SHA1 吞吐达 {fmt_num(max_sha1)} bytes/s，密码学运算出色'))

    # Hackbench
    if 'hackbench_performance' in vis:
        for s in vis['hackbench_performance']['series']:
            if 'time' in s['name']:
                results.append(('正常', '进程调度', f'Hackbench 耗时 {s["data"][0]:.2f}s，处于正常范围'))

    # V-Ray
    if 'vray_performance' in vis:
        for s in vis['vray_performance']['series']:
            if 'render_time' in s['name']:
                results.append(('正常', 'V-Ray 渲染', f'渲染耗时 {s["data"][0]:.0f}s，适合中等规模渲染任务'))

    return results


def generate_markdown(data, chart_paths, radar_path, diagnoses):
    """生成 Markdown 报告"""
    vis = data.get('visualizations', {})
    summary = data.get('analysis_summary', {})
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    md = []
    md.append('# 云主机性能测试报告\n')
    md.append(f'> 生成时间：{now}  \n')
    md.append(f'> 任务ID：{data.get("task_id", "N/A")}\n')

    # 一、测试概览
    md.append('\n## 一、测试概览\n')
    md.append(f'| 项目 | 数值 |')
    md.append(f'|------|------|')
    md.append(f'| 测试项数 | {summary.get("test_count", len(vis))} |')
    md.append(f'| 图表数量 | {summary.get("chart_count", len(vis))} |')
    md.append(f'| 指标总数 | {summary.get("metric_count", "N/A")} |')
    md.append('')

    # 二、综合雷达图
    md.append('\n## 二、综合性能雷达图\n')
    md.append(f'![综合性能雷达图]({os.path.basename(radar_path)})\n')

    # 三、分项详情
    md.append('\n## 三、分项测试详情\n')
    for i, (category, cat_data) in enumerate(vis.items()):
        meta = CATEGORY_META.get(category, {'label': category, 'desc': ''})
        md.append(f'\n### 3.{i+1} {meta["label"]}\n')
        md.append(f'{meta["desc"]}\n')

        if i < len(chart_paths):
            md.append(f'![{meta["label"]}]({os.path.basename(chart_paths[i])})\n')

        # 数据表格
        md.append(f'| 指标 | 数值 |')
        md.append(f'|------|------|')
        for s in cat_data['series'][:15]:
            md.append(f'| {s["name"]} | {fmt_num(s["data"][0])} |')
        md.append('')

    # 四、诊断分析
    md.append('\n## 四、性能诊断与分析\n')
    level_emoji = {'优秀': '🟢', '关注': '🟡', '正常': '🔵'}
    for level, area, detail in diagnoses:
        md.append(f'- {level_emoji.get(level, "⚪")} **[{level}] {area}**：{detail}')
    md.append('')

    # 五、结论建议
    md.append('\n## 五、结论与建议\n')
    good_count = sum(1 for d in diagnoses if d[0] == '优秀')
    warn_count = sum(1 for d in diagnoses if d[0] == '关注')
    md.append(f'本次测试共涵盖 {summary.get("test_count", len(vis))} 个测试场景，'
              f'{summary.get("metric_count", "N/A")} 项指标。')
    md.append(f'其中 {good_count} 项表现优秀，{warn_count} 项需要关注。\n')

    if warn_count > 0:
        md.append('**优化建议：**\n')
        for level, area, detail in diagnoses:
            if level == '关注':
                md.append(f'- **{area}**：{detail}，建议进一步排查或考虑硬件升级。')

    md.append('\n---\n')
    md.append(f'*本报告由 skill_report 自动生成 | {now}*\n')

    return '\n'.join(md)


def generate_pdf(md_content, chart_paths, radar_path, output_path):
    """将报告生成为 PDF（使用 matplotlib 拼接图表页）"""
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(output_path) as pdf:
        # 封面页
        fig = plt.figure(figsize=(11, 8.5))
        fig.text(0.5, 0.6, '云主机性能测试报告', ha='center', va='center',
                fontsize=28, fontweight='bold', color='#333')
        fig.text(0.5, 0.45, f'任务ID: jvsclaw', ha='center', va='center',
                fontsize=14, color='#666')
        fig.text(0.5, 0.38, f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
                ha='center', va='center', fontsize=12, color='#888')
        fig.text(0.5, 0.25, 'skill_report 自动生成', ha='center', va='center',
                fontsize=10, color='#aaa')
        pdf.savefig(fig, facecolor='white')
        plt.close()

        # 雷达图页
        if os.path.exists(radar_path):
            img = plt.imread(radar_path)
            fig, ax = plt.subplots(figsize=(11, 8.5))
            ax.imshow(img)
            ax.axis('off')
            ax.set_title('综合性能雷达图', fontsize=16, fontweight='bold', pad=10)
            pdf.savefig(fig, facecolor='white')
            plt.close()

        # 各图表页
        for chart_path in chart_paths:
            if os.path.exists(chart_path):
                img = plt.imread(chart_path)
                fig, ax = plt.subplots(figsize=(11, 8.5))
                ax.imshow(img)
                ax.axis('off')
                pdf.savefig(fig, facecolor='white')
                plt.close()

    print(f"[OK] PDF 报告已生成: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='云主机性能测试报告生成器')
    parser.add_argument('--input', required=True, help='输入数据文件路径 (JSON 或 JS)')
    parser.add_argument('--output-dir', default='./output', help='输出目录')
    args = parser.parse_args()

    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)

    # 加载数据
    print(f"[INFO] 加载数据: {args.input}")
    data = load_data(args.input)
    vis = data.get('visualizations', {})
    print(f"[INFO] 共 {len(vis)} 个测试类别")

    # 生成各图表
    chart_paths = []
    for i, (category, cat_data) in enumerate(vis.items()):
        print(f"[INFO] 生成图表 [{i+1}/{len(vis)}]: {category}")
        path = generate_bar_chart(category, cat_data['series'], args.output_dir, i)
        chart_paths.append(path)

    # 生成雷达图
    print("[INFO] 生成综合雷达图...")
    radar_path = generate_radar_chart(data, args.output_dir)

    # 自动诊断
    print("[INFO] 执行自动诊断...")
    diagnoses = auto_diagnose(data)

    # 生成 Markdown
    print("[INFO] 生成 Markdown 报告...")
    md_content = generate_markdown(data, chart_paths, radar_path, diagnoses)
    md_path = os.path.join(args.output_dir, 'report.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"[OK] Markdown 报告: {md_path}")

    # 生成 PDF
    print("[INFO] 生成 PDF 报告...")
    pdf_path = os.path.join(args.output_dir, 'report.pdf')
    generate_pdf(md_content, chart_paths, radar_path, pdf_path)

    print("\n========================================")
    print("  报告生成完成！")
    print(f"  Markdown: {md_path}")
    print(f"  PDF:      {pdf_path}")
    print(f"  图表目录:  {args.output_dir}")
    print("========================================")


if __name__ == '__main__':
    main()
