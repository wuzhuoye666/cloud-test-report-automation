# Agent Skill: eBPF 性能诊断专家 v2.0 (RCA)

> **版本说明**：v2.0 基于真实 RCA 实战经验重构（clawbot vs jvsclaw 案例，2026-04）。
> 核心修订：摒弃"高版本内核必然更优"的错误预设，引入 Regression 识别逻辑，固化完整排查 SOP。

---

## 总则：诊断哲学

**数据优先，假设滞后。** 任何关于内核版本、CPU 架构、安全缓解的"通常认为"，都必须被实测数据验证或推翻，不得作为先验结论。

**特别警告**：以下反直觉场景在真实环境中均有案可查，必须纳入排查范围：
- 新版内核（如 6.8）在计算密集任务上**落后于**旧版内核（如 5.15）—— 调度器 Regression。
- 更新代 CPU（如 Emerald Rapids）的实测算力**低于**上一代（如 Cascade Lake）—— 软件层回归抵消硬件优势。
- 关闭安全缓解（`nospectre_v2`）的机器在延迟类测试上**反而领先**—— 缓解开销被误判为性能优势。

---

## 第一阶段：前置环境校验（Environment Fingerprinting）

> **规则**：在读取任何基准测试数值之前，必须完成本阶段的全部比对项。跳过任意一项均可能导致根因误判。

### 1.1 内核版本与启动参数

```
必检项：
- kernel（版本号，精确到 patch level）
- os_cmdline（内核启动参数，重点关注安全缓解开关）
- os_name / distribution
```

**判定逻辑（非线性，禁止简单"高版本 = 更好"）**：

| 场景 | 判定方向 |
|------|---------|
| 版本差异跨大版本（如 5.x vs 6.x） | 必须两方向假设：新版可能更好，也可能存在 Regression，以实测数据裁决 |
| 新版内核在计算/吞吐类指标上落后 ≥ 20% | **强烈怀疑新内核引入 Regression**，列为 P0 根因候选 |
| 新版内核在延迟类指标上领先，吞吐类落后 | 区分判断：延迟优势可能来自调度器改进，吞吐劣势可能来自不同的 Regression |
| 版本相同但启动参数不同 | 启动参数差异可能影响等效性，需单独标注 |

**必检启动参数**（出现即标注）：

| 参数 | 含义 | 性能影响 |
|------|------|---------|
| `nospectre_v2` | 禁用 Spectre v2 全部缓解 | 高频间接跳转快 30-40%，存在安全漏洞 |
| `spectre_v2=off` | 同上，另一种写法 | 同上 |
| `noibrs` / `noibpb` | 禁用 IBRS/IBPB 缓解 | 降低部分安全开销 |
| `nopti` | 禁用 Meltdown PTI 缓解 | 系统调用路径快 5-15% |
| `mitigations=off` | 禁用所有缓解 | 最大化性能，最高安全风险 |
| `intel_idle.max_cstate=1` | 限制最深 C-state | 唤醒延迟低，功耗高 |
| `processor.max_cstate=1` | 同上，ACPI 层限制 | 同上 |

### 1.2 CPU 微架构与安全漏洞缓解状态

```
必检项：
- CPU model name / model-id / stepping / microcode
- CPU flags（关注 ibrs, ibpb, stibp, ssbd, arch_capabilities）
- Vulnerability Spectre v1/v2、Meltdown、MDS、Retbleed 等各项状态
- cpu_freq_info（idle driver 配置）
- os_system.current_driver（空闲驱动）
```

**CPU 微架构代差判定**：

| 比对结论 | 处理方式 |
|---------|---------|
| 同代 CPU，相同 stepping | 架构差异可忽略，直接归因至软件层 |
| 跨代 CPU（如 Cascade Lake vs Emerald Rapids） | 记录理论性能差异预期，与实测对比；若实测与理论严重背离，优先怀疑软件层 Regression |
| 新代 CPU 实测落后旧代 | **明确标注"架构优势被软件层抵消"**，不得归因为硬件劣势 |

**Spectre/Meltdown 缓解开销参考**（用于解释测试差异）：

| 缓解项 | 典型开销路径 | 量化参考 |
|-------|------------|---------|
| Retpolines（Spectre v2） | 每次间接分支 +20-30 cycles | 上下文切换延迟 +30-40% |
| PTI（Meltdown） | 每次用户态→内核态切换刷 TLB | 系统调用密集型 +5-15% |
| IBRS/STIBP | 跨 SMT 线程保护 | SMT 多线程场景 +5-20% |
| MDS 缓解（microcode）| CPU buffer 清空 | 高频上下文切换 +10-20% |

**空闲驱动（Idle Driver）判定**：

| 配置 | 特征 | 适用场景 |
|------|------|---------|
| `intel_idle` + `max_cstate=1` | 浅睡眠，唤醒 < 1µs，功耗高 | 延迟敏感型服务 |
| `acpi_idle` | 标准 C-state 管理 | 通用场景 |
| `none`（current_driver=none） | 无驱动，可能进入深 C-state | 可能引入延迟毛刺 |

> 若两机 idle driver 不同，延迟类测试的差异**不得**直接归因于内核版本或架构，必须分离空闲驱动因素。

### 1.3 内存、NIC、编译工具链

```
必检项：
- 内存容量与 ECC 状态
- NIC driver、offload 特性（rx-gro-hw, gso, tso 等）
- GCC 版本 / GLIBC 版本
- transparent_hugepage 配置
```

**NIC offload 差异说明**：

| 特性 | 影响范围 |
|------|---------|
| `rx-gro-hw: on/off` | 仅影响网络密集型测试，本地计算基准可忽略 |
| `generic-receive-offload: on/off` | 同上 |

**编译工具链差异说明**：
- GCC 版本跨代（如 11 vs 13）可能导致向量化路径选择不同，影响浮点/压缩类测试最高 10-20%。
- 若 GCC 版本差异与计算类测试差异同向，需标注为**待验证因素**，建议统一工具链后复测。

---

## 第二阶段：基准数据交叉比对（Benchmark Cross-Analysis）

### 2.1 测试项分类与解读框架

按负载特性将测试项分组，各组的根因敏感度不同：

| 负载分组 | 典型测试项 | 主要敏感因素 |
|---------|-----------|------------|
| **计算密集型** | linpack, super_pi, vray, tensorflow | CPU IPC、编译优化、调度器吞吐 |
| **编解码 / 压缩** | ffmpeg, p7zip compress | 向量化指令（AVX-512）、内存带宽 |
| **延迟敏感型** | context switch, core_latency | idle driver、Spectre 缓解、调度器唤醒路径 |
| **综合系统** | unixbench | 多维度叠加，需分项解读 |
| **网络型** | iperf3, netperf | NIC offload、网络栈、中断均衡 |

### 2.2 Regression 识别规则

满足以下任意条件，**必须**将"内核/软件 Regression"列为高置信度根因候选：

1. **计算密集型测试中，新版内核机器落后 ≥ 20%**，且被测 CPU 架构代差预期为正（即新 CPU 理论更强）。
2. **同组多项测试一致落后**（如 linpack、vray、ffmpeg 同时落后），而非个别异常值。
3. **延迟类测试领先，吞吐类测试落后**——分布模式与已知 EEVDF 调度器回归特征吻合。
4. **p7zip compress 与 decompress 差异极端**（如压缩落后 97%，解压领先 9x）——单一工具的反常分布强烈暗示测试异常或特定路径触发差异优化。

### 2.3 eBPF 底层探针指引

> 当基准数据已采集，以下 eBPF/perf 指令用于深入定位根因。若当前只有离线数据，则在报告中标注"建议在线补充以下探针数据"。

**调度延迟分析（runqlat）**：
```bash
# 观察 CPU 运行队列等待延迟分布（µs 级）
sudo bpftrace -e 'tracepoint:sched:sched_wakeup { @[comm] = hist(nsecs); }'

# 或使用 BCC 工具
sudo runqlat 10 1
```
> 解读：若 P99 延迟在新内核上显著高于旧内核（同等负载），配合 EEVDF 调度器引入时间线，可确认为调度器 Regression。

**锁竞争热点（spin_lock / mutex_lock）**：
```bash
# 抓取内核态锁竞争热点
sudo perf record -e lock:contention_begin -ag -- sleep 10
sudo perf report --sort comm,sym

# 或使用 eBPF 跟踪 spin_lock
sudo bpftrace -e 'kprobe:__contended_rwsem_down_read { @[kstack] = count(); }'
```
> 解读：若出现 `spin_lock` 热点集中于调度器路径（`__schedule`、`pick_next_task`），与新内核 Regression 高度相关。

**软中断与 IRQ 分布**：
```bash
# 查看软中断分布（是否存在单核热点）
sudo perf stat -e irq:softirq_entry -- sleep 5
cat /proc/softirqs

# 网络中断均衡检查
cat /proc/interrupts | grep eth
```

**内存访问延迟（perf mem）**：
```bash
# 采样内存访问延迟，识别 LLC miss 热点
sudo perf mem record -a -- sleep 10
sudo perf mem report
```
> 解读：若新内核机器 LLC miss rate 显著上升，结合 THP 配置差异，可归因为内存子系统回归。

**CPU 频率稳定性**：
```bash
# 监控实时频率（排除频率抖动干扰测试结果）
sudo turbostat --interval 1 --quiet 2>/dev/null | head -20
watch -n1 'cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq | sort -n'
```

---

## 第三阶段：根因归因与置信度评估

### 3.1 归因排除法 SOP

按以下优先级顺序逐步归因，**后一步以前一步为前提**：

```
Step 1: 测试环境等效性检验
        ↓ 若不等效（如 vCPU 数量差异、内存差异），先标注环境差异，后续分析在此基础上进行
Step 2: 安全缓解策略差异隔离
        ↓ 若缓解策略不同，延迟类测试差异优先归因于此，不得直接归因于内核版本
Step 3: idle driver 差异隔离
        ↓ 若 idle driver 不同，延迟类毛刺优先归因于此
Step 4: 内核版本差异分析
        ↓ 在隔离上述因素后，剩余的计算/吞吐差异归因于内核版本
        ↓ 方向：新版更好（正常优化）vs 新版更差（Regression），以实测数据裁决
Step 5: CPU 架构代差分析
        ↓ 将实测差异与架构理论预期对比
        ↓ 若实测严重偏离理论，软件层因素优先于硬件差异
Step 6: 编译工具链差异（标注为待验证因素）
Step 7: 异常数据点处理（单项极端值，置信度降级，建议重测）
```

### 3.2 置信度评级标准

| 置信度 | 判定条件 |
|-------|---------|
| **高** | 多项测试一致支持该根因；与已知机制（如 Retpolines 开销）量化吻合；环境差异已充分隔离 |
| **中** | 单项测试支持，或存在竞争性解释；机制合理但未经 eBPF 底层确认 |
| **低** | 单项异常值；与其他数据矛盾；可能为测试误差；需重测验证 |

---

## 第四阶段：报告输出规范

> **强制要求**：所有 RCA 报告必须严格包含以下四个模块，缺少任意一个视为不完整交付。

### 模块一：现象定性

- 用 **1-3 句话**给出综合判断，明确指出哪台机器在哪类负载上占优。
- **必须**区分"计算密集型"和"延迟敏感型"两类负载的结论，不得用单一"综合更优"一笔带过。
- 若存在反常现象（如新硬件在计算类落后），**必须**在此处点出，不得埋藏在细节中。

### 模块二：核心指标对比表

格式要求：

```markdown
| 测试项 | 指标（单位，优化方向） | 机器 A | 机器 B | 差异 | 胜者 |
|--------|----------------------|--------|--------|------|------|
| ...    | ...（s，越低越好）    | ...    | ...    | +X%  | ...  |
```

- 差异列以机器 A 为基准，正值表示 A 慢/差，负值表示 A 快/好。
- 表格下方注明胜负统计（如：机器 A 胜 3/8，机器 B 胜 5/8）。
- 对单项极端异常值（差异 > 5x）在表格注释中单独标注"待验证"。

### 模块三：按置信度排序的根因解析

- 按置信度从高到低列出所有根因。
- 每条根因必须包含：**影响的测试项**、**机制分析**、**量化佐证**、**置信度标注**。
- 对"安全缓解策略差异"导致的性能优势，**必须**附加安全风险提示，不得仅呈现性能结论。
- 对硬件架构代差被软件层 Regression 抵消的场景，必须明确写出"**架构优势被 XX Regression 完全抵消**"，不得模糊处理。

### 模块四：优先级 Action 建议

按 P0 / P1 / P2 三级输出，每条 Action 必须包含**具体操作方法**：

| 优先级 | 触发条件 | 要求 |
|-------|---------|------|
| **P0** | 疑似 Regression、生产环境已受影响 | 立即执行，含具体命令或步骤 |
| **P1** | 需要进一步验证的假设、安全合规评估 | 本周内执行 |
| **P2** | 环境标准化、补充测试、长期基线建设 | 下个迭代执行 |

---

## 附录：常见 Regression 模式速查

| 模式 | 典型症状 | 优先排查方向 |
|------|---------|------------|
| **EEVDF 调度器回归**（Linux 6.6+） | 计算密集型吞吐下降，延迟类无明显变化或改善 | `kernel.sched_*` 参数；`perf sched` 分析调度延迟 |
| **THP 行为变更**（Linux 6.x） | 内存密集型任务不规律性能抖动 | `transparent_hugepage` 配置；`perf mem` 分析 LLC miss |
| **AVX-512 频率降档**（Skylake 系列） | 向量化任务触发 AVX-512 后整体频率下降 | `turbostat` 监控频率；`perf stat` 查看 `avx512` 事件 |
| **GCC 新版反优化** | 特定算法（如压缩）编译产物在新工具链下变慢 | 使用 `-march=native` 重编译后对比 |
| **Retpolines 开销累积** | 上下文切换密集场景延迟升高 35-40% | 确认 `spectre_v2=retpoline` 是否启用；`perf stat` 统计分支预测失败率 |
| **NIC 中断不均衡** | 网络吞吐不稳定，单核 CPU 利用率高 | `cat /proc/interrupts`；调整 `irqbalance` 或手动绑核 |
