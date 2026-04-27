"""
CVM MCP Server
AutoPerf-Agent 的底层虚拟机执行接口，基于 FastMCP 框架暴露三个诊断工具。
"""

import subprocess
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("cvm-tools")


@mcp.tool()
def get_env_fingerprint(vm_name: str) -> str:
    """
    获取目标虚拟机的内核版本和 Spectre v2 漏洞缓解策略。

    Args:
        vm_name: Multipass 虚拟机名称（如 "clawbot" 或 "jvsclaw"）。

    Returns:
        包含内核版本和 Spectre v2 缓解状态的字符串，格式：
            <uname -r 输出>
            <spectre_v2 文件内容>
        或错误信息字符串。
    """
    cmd = (
        f"multipass exec {vm_name} -- bash -c "
        f"'uname -r && cat /sys/devices/system/cpu/vulnerabilities/spectre_v2'"
    )
    try:
        output = subprocess.check_output(
            cmd, shell=True, stderr=subprocess.STDOUT, timeout=15
        )
        return output.decode("utf-8", errors="replace").strip()
    except subprocess.CalledProcessError as e:
        return f"[ERROR] 命令执行失败 (exit {e.returncode}):\n{e.output.decode('utf-8', errors='replace').strip()}"
    except subprocess.TimeoutExpired:
        return f"[ERROR] 命令超时（15s），请检查虚拟机 {vm_name!r} 是否运行正常。"
    except Exception as e:
        return f"[ERROR] 未预期异常: {e}"


@mcp.tool()
def trigger_tencent_bench(
    vm_name: str,
    plan_name: str = "cvm.net_baseline.redis_cluster_baseline",
) -> str:
    """
    在目标虚拟机后台触发 TencentBench 压测任务（非阻塞，立即返回 PID）。

    Args:
        vm_name:   Multipass 虚拟机名称。
        plan_name: TencentBench 内置测试计划名称，默认为 Redis 集群网络基准。
                   示例：
                     - "cvm.baseline.super_pi_baseline"
                     - "cvm.net_baseline.redis_cluster_baseline"
                     - "cvm.baseline.linpack_baseline"

    Returns:
        后台进程的 PID 字符串，或错误信息字符串。
    """
    cmd = (
        f"multipass exec {vm_name} -- bash -c "
        f"'cd /home/ubuntu/TencentBench-2.2.1a24 && "
        f"tb --built_in_plan {plan_name} --collect_env=False --publish=False'"
    )
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return (
            f"[OK] TencentBench 已在 {vm_name!r} 后台启动。\n"
            f"plan={plan_name}\npid={proc.pid}"
        )
    except FileNotFoundError:
        return "[ERROR] 未找到 multipass 可执行文件，请确认 Multipass 已安装并在 PATH 中。"
    except Exception as e:
        return f"[ERROR] 启动压测失败: {e}"


@mcp.tool()
def run_ebpf_trace(vm_name: str, duration: int = 5) -> str:
    """
    在目标虚拟机上执行 runqlat（eBPF 调度延迟探针），采集 CPU 运行队列等待时间分布。

    Args:
        vm_name:  Multipass 虚拟机名称。
        duration: 采集持续时间（秒），默认 5 秒，建议范围 5-60 秒。

    Returns:
        runqlat 的直方图输出文本（µs 级延迟分布），或错误信息字符串。
        结果可直接用于判断调度器 Regression：
          - P99 < 100µs：调度延迟正常
          - P99 100-500µs：存在调度抖动，建议结合 perf sched 深入排查
          - P99 > 500µs：调度延迟严重，高度怀疑 Regression 或资源争抢
    """
    if duration < 1 or duration > 300:
        return "[ERROR] duration 参数超出合法范围（1-300 秒）。"

    cmd = (
        f"multipass exec {vm_name} -- "
        f"sudo /usr/sbin/runqlat-bpfcc {duration}"
    )
    try:
        output = subprocess.check_output(
            cmd,
            shell=True,
            stderr=subprocess.STDOUT,
            timeout=duration + 15,
        )
        return output.decode("utf-8", errors="replace").strip()
    except subprocess.CalledProcessError as e:
        return (
            f"[ERROR] runqlat 执行失败 (exit {e.returncode}):\n"
            f"{e.output.decode('utf-8', errors='replace').strip()}\n"
            f"提示：请确认目标机已安装 bpfcc-tools，命令：sudo apt install bpfcc-tools"
        )
    except subprocess.TimeoutExpired:
        return f"[ERROR] eBPF 采集超时（{duration + 15}s），请检查虚拟机 {vm_name!r} 状态。"
    except Exception as e:
        return f"[ERROR] 未预期异常: {e}"


if __name__ == "__main__":
    mcp.run()
