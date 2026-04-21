#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import requests


REGION_API = "https://cloud.baidu.com/api/region/region_list"
FLAVOR_API = "https://cloud.baidu.com/api/calculator/bccFlavor"
PRICE_API = "https://cloud.baidu.com/api/calculator/bcc/instance/priceV2"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://cloud.baidu.com/price/calculator?product=bcc",
    "Content-Type": "application/json;charset=UTF-8",
}

DEFAULT_RETRY_DISKS = ["enhanced_ssd_pl1", "premium_ssd", "ssd"]


@dataclass
class Flavor:
    group_name: str
    spec: str
    spec_id: str
    instance_type: int
    cpu: int
    memory_gib: int
    category: str
    arch: str
    gpu_card: str
    gpu_count: int
    fpga_card: str
    fpga_count: int
    ephemeral_gb: int
    product_type: str


def to_decimal(v: Any) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = requests.post(url, headers=HEADERS, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("success") is not True:
        raise RuntimeError(f"API failed: {url}, response={data}")
    return data


def fetch_regions() -> list[dict[str, str]]:
    data = post_json(REGION_API, {"serviceType": "BCC"})
    rows = data.get("result") or []
    return [r for r in rows if isinstance(r, dict) and r.get("value") and r.get("name")]


def fetch_flavors_and_disks(region: str) -> tuple[list[Flavor], list[str]]:
    data = post_json(FLAVOR_API, {"region": region, "ignoreReservedInstanceProductType": True})
    zone_resources = (data.get("result") or {}).get("zoneResources") or []
    if not zone_resources:
        raise RuntimeError("No zoneResources returned")

    zone = zone_resources[0]
    bcc_resources = zone.get("bccResources") or {}
    flavor_groups = bcc_resources.get("flavorGroups") or []
    cds_resources = zone.get("cdsResources") or []

    disk_types: list[str] = []
    for d in cds_resources:
        storage_type = (d.get("storageType") or "").strip().lower()
        if storage_type and storage_type not in disk_types and storage_type != "elastic_ephemeral_disk":
            disk_types.append(storage_type)

    flavors: list[Flavor] = []
    for group in flavor_groups:
        group_name = str(group.get("groupName") or group.get("groupId") or "unknown")
        for f in group.get("flavors") or []:
            spec = str(f.get("spec") or "").strip()
            if not spec:
                continue
            flavors.append(
                Flavor(
                    group_name=group_name,
                    spec=spec,
                    spec_id=str(f.get("specId") or ""),
                    instance_type=int(f.get("instanceType") or 0),
                    cpu=int(f.get("cpuCount") or 0),
                    memory_gib=int(f.get("memoryCapacityInGB") or 0),
                    category=str(f.get("category") or ""),
                    arch=str(f.get("structure") or "x86"),
                    gpu_card=str(f.get("gpuCardType") or ""),
                    gpu_count=int(f.get("gpuCardCount") or 0),
                    fpga_card=str(f.get("fpgaCardType") or ""),
                    fpga_count=int(f.get("fpgaCardCount") or 0),
                    ephemeral_gb=int(f.get("ephemeralDiskInGb") or 0),
                    product_type=str(f.get("productType") or ""),
                )
            )

    uniq: dict[str, Flavor] = {}
    for f in flavors:
        key = f"{f.spec}::{f.product_type}"
        if key not in uniq:
            uniq[key] = f

    return sorted(uniq.values(), key=lambda x: (x.group_name, x.cpu, x.memory_gib, x.spec)), (disk_types or DEFAULT_RETRY_DISKS.copy())


def pick_flavor_by_spec(flavors: list[Flavor], flavor_spec: str, billing_mode: str = "postpay") -> Flavor | None:
    for f in flavors:
        if f.spec == flavor_spec and f.product_type == billing_mode:
            return f
    return None


def pick_flavor_by_name(flavors: list[Flavor], flavor_name: str, billing_mode: str = "postpay") -> Flavor | None:
    mode_rows = [f for f in flavors if f.product_type == billing_mode]
    if not mode_rows:
        return None
    name = (flavor_name or "").strip().lower()
    candidates = [
        f
        for f in mode_rows
        if name in f.spec.lower() or name in f.group_name.lower() or name in f.category.lower()
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: (x.cpu, x.memory_gib, x.spec))[0]


def quote_price(
    *,
    region: str,
    flavor: Flavor,
    root_disk_type: str,
    root_disk_size_gb: int,
    eip_charge_mode: str,
    bandwidth_mbps: int,
) -> dict[str, Any]:
    eip_payload: dict[str, Any] = {
        "productType": "postpay",
        "purchaseType": "BGP",
        "subProductType": "",
        "bandwidthInMbps": bandwidth_mbps,
        "netChargeType": "ByTraffic" if eip_charge_mode == "traffic" else "ByBandwidth",
    }

    payload: dict[str, Any] = {
        "bcc": {
            "cpu": flavor.cpu,
            "gpuCard": flavor.gpu_card,
            "gpuCount": flavor.gpu_count,
            "memory": flavor.memory_gib,
            "productType": "postpay",
            "rootDiskSizeInGb": root_disk_size_gb,
            "rootDiskStorageType": root_disk_type,
            "spec": flavor.spec,
            "specId": flavor.spec_id,
            "instanceType": flavor.instance_type,
            "kunlunCard": "",
            "kunlunCount": 0,
            "fpgaCard": flavor.fpga_card,
            "fpgaCount": flavor.fpga_count,
            "containsFpga": True,
            "ephemeralSizeGb": flavor.ephemeral_gb,
        },
        "cds": {"diskConfigs": [], "productType": "postpay"},
        "purchaseLength": 1,
        "purchaseNum": 1,
        "region": region,
        "eip": eip_payload,
    }

    data = post_json(PRICE_API, payload)
    return data.get("result") or {}


def quote_with_disk_retry(
    *,
    region: str,
    flavor: Flavor,
    disk_size_gb: int,
    eip_charge_mode: str,
    bandwidth_mbps: int,
    disk_candidates: list[str],
) -> tuple[dict[str, Any] | None, str]:
    retry_order: list[str] = []
    for d in DEFAULT_RETRY_DISKS + disk_candidates:
        if d not in retry_order:
            retry_order.append(d)

    used_disk = retry_order[0]
    for disk_type in retry_order:
        result = quote_price(
            region=region,
            flavor=flavor,
            root_disk_type=disk_type,
            root_disk_size_gb=disk_size_gb,
            eip_charge_mode=eip_charge_mode,
            bandwidth_mbps=bandwidth_mbps,
        )
        if result.get("money") not in (None, "", "null"):
            return result, disk_type
    return None, used_disk


def disk_label(storage_type: str, size_gib: int) -> str:
    mapping = {
        "enhanced_ssd_pl1": "增强型SSD_PL1",
        "premium_ssd": "高性能云盘SSD",
        "ssd": "SSD",
    }
    base = mapping.get(storage_type.lower(), storage_type)
    return f"{base}: {size_gib}GiB"


def extract_price_value(item: dict[str, Any]) -> Decimal:
    prices = item.get("price") or []
    if isinstance(prices, list) and prices:
        return to_decimal(prices[0])
    return Decimal("0")


def build_detail_result(
    *,
    region_code: str,
    flavor_spec: str,
    disk_size_gb: int,
    eip_charge_mode: str,
    bandwidth_mbps: int,
) -> dict[str, Any]:
    flavors, disks = fetch_flavors_and_disks(region_code)
    flavor = pick_flavor_by_spec(flavors, flavor_spec, "postpay")
    if flavor is None:
        raise RuntimeError(f"地域 {region_code} 未找到实例 {flavor_spec}")

    result, used_disk = quote_with_disk_retry(
        region=region_code,
        flavor=flavor,
        disk_size_gb=disk_size_gb,
        eip_charge_mode=eip_charge_mode,
        bandwidth_mbps=bandwidth_mbps,
        disk_candidates=disks,
    )
    if not result:
        raise RuntimeError(f"地域 {region_code} 无可用报价")

    detail_map: dict[str, dict[str, Any]] = {}
    for item in result.get("priceDetail") or []:
        service_type = str(item.get("servicetype") or "")
        if service_type:
            detail_map[service_type] = item

    bcc_price = extract_price_value(detail_map.get("BCC", {}))
    cds_price = extract_price_value(detail_map.get("SYS-CDS", {}))
    eip_price = extract_price_value(detail_map.get("EIP", {}))

    per_minute_total = bcc_price + cds_price
    per_hour_total = per_minute_total * Decimal("60")
    per_month_total = per_hour_total * Decimal("24") * Decimal("30")

    region_name = next((r["name"] for r in fetch_regions() if r["value"] == region_code), region_code)
    eip_unit = "GB" if eip_charge_mode == "traffic" else "MINUTE"

    return {
        "region": {"code": region_code, "name": region_name},
        "instance": {
            "spec": flavor.spec,
            "group_name": flavor.group_name,
            "cpu": flavor.cpu,
            "memory_gib": flavor.memory_gib,
            "description": f"{flavor.cpu}核/{flavor.memory_gib}GB内存",
        },
        "system_disk": {
            "type": used_disk,
            "size_gb": disk_size_gb,
            "label": disk_label(used_disk, disk_size_gb),
            "description": disk_label(used_disk, disk_size_gb),
        },
        "eip": {
            "charge_mode": eip_charge_mode,
            "bandwidth_mbps": bandwidth_mbps,
            "description": f"按流量计费 {bandwidth_mbps}Mbps" if eip_charge_mode == "traffic" else f"按带宽计费 {bandwidth_mbps}Mbps",
        },
        "price_breakdown": {
            "bcc": {
                "name": "云服务器BCC",
                "config": f"{flavor.cpu}核/{flavor.memory_gib}GB内存 ({flavor.spec})",
                "price_per_minute": str(bcc_price),
                "price_per_hour": str(bcc_price * Decimal('60')),
                "price_per_month_30d": str(bcc_price * Decimal('60') * Decimal('24') * Decimal('30')),
            },
            "system_disk": {
                "name": "系统盘",
                "config": disk_label(used_disk, disk_size_gb),
                "price_per_minute": str(cds_price),
                "price_per_hour": str(cds_price * Decimal('60')),
                "price_per_month_30d": str(cds_price * Decimal('60') * Decimal('24') * Decimal('30')),
            },
            "eip": {
                "name": "弹性公网IP",
                "config": f"按流量计费 {bandwidth_mbps}Mbps" if eip_charge_mode == "traffic" else f"按带宽计费 {bandwidth_mbps}Mbps",
                "price_per_unit": str(eip_price),
                "unit": eip_unit,
            },
        },
        "total_prices": {
            "per_minute_excluding_eip": str(per_minute_total),
            "per_hour_excluding_eip": str(per_hour_total),
            "per_month_30d_excluding_eip": str(per_month_total),
        },
        "raw_result": result,
    }


def query_single_region_price(
    region_code: str,
    region_name: str,
    flavor_spec: str,
    disk_size_gb: int,
    eip_charge_mode: str = "traffic",
    bandwidth_mbps: int = 100,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        detail = build_detail_result(
            region_code=region_code,
            flavor_spec=flavor_spec,
            disk_size_gb=disk_size_gb,
            eip_charge_mode=eip_charge_mode,
            bandwidth_mbps=bandwidth_mbps,
        )
        bcc_price = to_decimal(detail["price_breakdown"]["bcc"]["price_per_minute"])
        cds_price = to_decimal(detail["price_breakdown"]["system_disk"]["price_per_minute"])
        money = bcc_price + cds_price
        per_hour = money * Decimal("60")
        per_month = per_hour * Decimal("24") * Decimal("30")

        return {
            "region_code": region_code,
            "region_name": region_name,
            "spec": detail["instance"]["spec"],
            "group_name": detail["instance"]["group_name"],
            "cpu": detail["instance"]["cpu"],
            "memory_gib": detail["instance"]["memory_gib"],
            "disk_type": detail["system_disk"]["type"],
            "disk_size_gb": disk_size_gb,
            "eip_charge_mode": eip_charge_mode,
            "bandwidth_mbps": bandwidth_mbps,
            "price_per_minute": str(money),
            "price_per_hour": str(per_hour),
            "price_per_month_30d": str(per_month),
            "raw_price": str(money),
        }, None
    except Exception as exc:
        return None, f"地域 {region_name} 查询失败: {exc}"


def render_simple_price_table(
    *,
    flavor_name: str,
    disk_size: int,
    eip_charge_mode: str,
    region: str,
    bandwidth: int,
    disk_type: str,
) -> None:
    regions = fetch_regions()
    region_codes = {r["value"] for r in regions}
    if region not in region_codes:
        raise ValueError(f"无效 region: {region}")

    flavors, disks = fetch_flavors_and_disks(region)
    flavor = pick_flavor_by_name(flavors, flavor_name, "postpay")
    if not flavor:
        raise RuntimeError(f"未找到匹配实例规格: {flavor_name}")

    result = quote_price(
        region=region,
        flavor=flavor,
        root_disk_type=disk_type,
        root_disk_size_gb=disk_size,
        eip_charge_mode=eip_charge_mode,
        bandwidth_mbps=max(1, bandwidth),
    )
    if result.get("money") in (None, "", "null"):
        result, used_disk = quote_with_disk_retry(
            region=region,
            flavor=flavor,
            disk_size_gb=disk_size,
            eip_charge_mode=eip_charge_mode,
            bandwidth_mbps=max(1, bandwidth),
            disk_candidates=disks,
        )
        if not result:
            raise RuntimeError("报价为空，请尝试更换磁盘类型或实例规格")
    else:
        used_disk = disk_type

    detail_map: dict[str, dict[str, Any]] = {}
    for item in result.get("priceDetail") or []:
        service_type = str(item.get("servicetype") or "")
        if service_type:
            detail_map[service_type] = item

    bcc_price = extract_price_value(detail_map.get("BCC", {}))
    cds_price = extract_price_value(detail_map.get("SYS-CDS", {}))
    eip_price = extract_price_value(detail_map.get("EIP", {}))

    eip_text = f"{eip_price:.6f}元/GB" if eip_charge_mode == "traffic" else f"{eip_price:.7f}元/分钟"

    print("\n计费项         配置详情                       价格")
    print("-" * 60)
    print(f"{'云服务器BCC':<12} {flavor.spec:<28} {bcc_price:.7f}元/分钟")
    print(f"{'系统盘':<12} {disk_label(used_disk, disk_size):<28} {cds_price:.7f}元/分钟")
    print(f"{'弹性公网IP':<12} {'流量费用' if eip_charge_mode == 'traffic' else '带宽费用':<28} {eip_text}")


def handle_top(args: argparse.Namespace) -> None:
    flavor_spec = args.flavor_spec
    disk_size_gb = args.disk_size
    eip_charge_mode = args.eip_charge_mode
    bandwidth_mbps = args.bandwidth

    print("查询百度云BCC实例价格")
    print(f"实例规格: {flavor_spec}")
    print(f"系统盘大小: {disk_size_gb} GiB")
    print("计费模式: 按量付费 (postpay)")
    print(f"公网IP计费方式: {eip_charge_mode} (带宽: {bandwidth_mbps}Mbps)")
    print("-" * 80)

    all_regions = fetch_regions()
    if args.region == "all":
        regions = all_regions
    else:
        regions = [r for r in all_regions if r.get("value") == args.region]
        if not regions:
            print(f"未找到地域: {args.region}")
            return

    print(f"本次查询地域数: {len(regions)}")

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for i, region in enumerate(regions, 1):
        region_code = region.get("value", "")
        region_name = region.get("name", "")
        if not region_code or not region_name:
            continue

        print(f"[{i}/{len(regions)}] 查询 {region_name} ({region_code})...")
        result, error = query_single_region_price(
            region_code,
            region_name,
            flavor_spec,
            disk_size_gb,
            eip_charge_mode=eip_charge_mode,
            bandwidth_mbps=bandwidth_mbps,
        )
        if result:
            results.append(result)
            print(f"  成功: 价格 {result['price_per_minute']} 元/分钟")
        elif error:
            errors.append({"region": region_name, "error": error})
            print(f"  失败: {error}")

    print("\n" + "=" * 80)
    print(f"查询完成: 成功 {len(results)} 个地域, 失败 {len(errors)} 个地域")

    if not results:
        print("未找到任何可用的价格信息")
        return

    results.sort(key=lambda x: Decimal(x["price_per_minute"]))

    show_top = max(1, args.top)
    print(f"\n价格最低的地域 (按每分钟价格排序, 前{show_top}个):")
    print("序号 | 地域 | 地域代码 | 规格 | CPU/内存 | 系统盘 | 公网IP | 每分钟价 | 每小时价 | 每月价(30天)")
    print("-" * 140)

    for i, r in enumerate(results[:show_top], 1):
        price_min = Decimal(r["price_per_minute"])
        price_hour = Decimal(r["price_per_hour"])
        price_month = Decimal(r["price_per_month_30d"])
        print(
            f"{i:>3} | {r['region_name']:<12} | {r['region_code']:<8} | {r['spec']:<15} | "
            f"{r['cpu']}C/{r['memory_gib']}G | {r['disk_type']} {r['disk_size_gb']}G | "
            f"{r['eip_charge_mode']}/{r['bandwidth_mbps']}Mbps | "
            f"RMB {price_min:.6f} | RMB {price_hour:.6f} | RMB {price_month:.4f}"
        )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(
            {
                "query": {
                    "flavor_spec": flavor_spec,
                    "disk_size_gb": disk_size_gb,
                    "billing_mode": "postpay",
                    "eip_charge_mode": eip_charge_mode,
                    "bandwidth_mbps": bandwidth_mbps,
                },
                "success_count": len(results),
                "error_count": len(errors),
                "results": results,
                "errors": errors,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\n详细结果已保存到: {args.output}")


def format_price_table(detailed_result: dict[str, Any]) -> None:
    print("\n" + "=" * 100)
    print("百度云 BCC 实例详细计费项明细")
    print("=" * 100)

    print(f"\n地域: {detailed_result['region']['name']} ({detailed_result['region']['code']})")
    print(f"实例规格: {detailed_result['instance']['spec']} ({detailed_result['instance']['description']})")
    print(f"系统盘: {detailed_result['system_disk']['description']}")
    print(f"公网IP: {detailed_result['eip']['description']}")
    print("\n" + "-" * 100)
    print("计费项明细:")
    print("-" * 100)

    bcc = detailed_result["price_breakdown"]["bcc"]
    print(f"\n1. {bcc['name']}:")
    print(f"   配置: {bcc['config']}")
    print(f"   每分钟价格: RMB {Decimal(bcc['price_per_minute']):.6f}")
    print(f"   每小时价格: RMB {Decimal(bcc['price_per_hour']):.6f}")
    print(f"   每月价格(30天): RMB {Decimal(bcc['price_per_month_30d']):.4f}")

    disk = detailed_result["price_breakdown"]["system_disk"]
    print(f"\n2. {disk['name']}:")
    print(f"   配置: {disk['config']}")
    print(f"   每分钟价格: RMB {Decimal(disk['price_per_minute']):.6f}")
    print(f"   每小时价格: RMB {Decimal(disk['price_per_hour']):.6f}")
    print(f"   每月价格(30天): RMB {Decimal(disk['price_per_month_30d']):.4f}")

    eip = detailed_result["price_breakdown"]["eip"]
    print(f"\n3. {eip['name']}:")
    print(f"   配置: {eip['config']}")
    print(f"   每{eip['unit']}价格: RMB {Decimal(eip['price_per_unit']):.6f}")

    total = detailed_result["total_prices"]
    print("\n" + "-" * 100)
    print("总计(云服务器 + 系统盘，不含公网IP流量费用):")
    print(f"   每分钟总计: RMB {Decimal(total['per_minute_excluding_eip']):.6f}")
    print(f"   每小时总计: RMB {Decimal(total['per_hour_excluding_eip']):.6f}")
    print(f"   每月总计(30天): RMB {Decimal(total['per_month_30d_excluding_eip']):.4f}")

    print("\n" + "=" * 100)
    print("说明:")
    print("- 公网IP流量费用按实际使用量计费，价格如上所示")
    print("- 每月价格按30天计算，仅供参考")
    print("- 实际费用请以百度云控制台为准")
    print("=" * 100)


def format_required_output(detailed_result: dict[str, Any]) -> None:
    """按用户要求输出: 地区 + 实例/系统盘分钟小时每天价格 + 按流量计费单价。"""
    region_name = detailed_result["region"]["name"]
    region_code = detailed_result["region"]["code"]

    instance_spec = detailed_result["instance"]["spec"]
    instance_group = detailed_result["instance"]["group_name"]
    disk_desc = detailed_result["system_disk"]["description"]

    bcc_min = Decimal(detailed_result["price_breakdown"]["bcc"]["price_per_minute"])
    bcc_hour = Decimal(detailed_result["price_breakdown"]["bcc"]["price_per_hour"])
    bcc_day = bcc_hour * Decimal("24")

    disk_min = Decimal(detailed_result["price_breakdown"]["system_disk"]["price_per_minute"])
    disk_hour = Decimal(detailed_result["price_breakdown"]["system_disk"]["price_per_hour"])
    disk_day = disk_hour * Decimal("24")

    eip = detailed_result["price_breakdown"]["eip"]
    eip_mode = detailed_result["eip"]["charge_mode"]
    eip_unit_price = Decimal(eip["price_per_unit"])
    eip_unit = eip["unit"]

    print("\n" + "=" * 88)
    print("百度云BCC价格格式化输出")
    print("=" * 88)
    print(f"地区: {region_name} ({region_code})")
    print("-" * 88)
    print("项目         名称/配置                              每分钟           每小时            每天")
    print("-" * 88)
    print(
        f"实例         {instance_group} ({instance_spec})"
        f"    {bcc_min:>10.6f}元"
        f"    {bcc_hour:>10.6f}元"
        f"    {bcc_day:>10.6f}元"
    )
    print(
        f"系统盘       {disk_desc:<34}"
        f"    {disk_min:>10.6f}元"
        f"    {disk_hour:>10.6f}元"
        f"    {disk_day:>10.6f}元"
    )
    print("-" * 88)
    if eip_mode == "traffic" and eip_unit == "GB":
        print(f"按流量计费单价: {eip_unit_price:.6f} 元/GB")
    else:
        print(f"按流量计费单价: 当前为 {eip_mode} 模式，返回单价 {eip_unit_price:.6f} / {eip_unit}")
    print("=" * 88)


def handle_detail(args: argparse.Namespace) -> None:
    print("查询百度云BCC实例详细计费项")
    print(f"实例规格: {args.flavor_spec}")
    print(f"系统盘大小: {args.disk_size} GiB")
    print("计费模式: 按量付费")
    print(f"公网IP计费方式: {args.eip_charge_mode} (带宽: {args.bandwidth}Mbps)")
    print(f"地域: {args.region}")

    result = build_detail_result(
        region_code=args.region,
        flavor_spec=args.flavor_spec,
        disk_size_gb=args.disk_size,
        eip_charge_mode=args.eip_charge_mode,
        bandwidth_mbps=args.bandwidth,
    )

    format_required_output(result)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {args.output}")


def handle_simple(args: argparse.Namespace) -> None:
    flavors, _ = fetch_flavors_and_disks(args.region)
    flavor = pick_flavor_by_name(flavors, args.flavor_name, "postpay")
    if not flavor:
        raise RuntimeError(f"未找到匹配实例规格: {args.flavor_name}")

    result = build_detail_result(
        region_code=args.region,
        flavor_spec=flavor.spec,
        disk_size_gb=args.disk_size,
        eip_charge_mode=args.eip_charge_mode,
        bandwidth_mbps=args.bandwidth,
    )
    format_required_output(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="统一版百度云 BCC 价格查询程序")
    sub = parser.add_subparsers(dest="command", required=True)

    top = sub.add_parser("top", help="对应原 query_bcc_price.py 跨地域排序功能")
    top.add_argument("--flavor-spec", default="bcc.ga4.c8m32")
    top.add_argument("--disk-size", type=int, default=240)
    top.add_argument("--eip-charge-mode", choices=["traffic", "bandwidth"], default="traffic")
    top.add_argument("--bandwidth", type=int, default=100)
    top.add_argument("--region", default="all")
    top.add_argument("--top", type=int, default=20)
    top.add_argument("--output", default="bcc_price_results.json")

    detail = sub.add_parser("detail", help="对应原 detailed_price_output.py 详细明细功能")
    detail.add_argument("--flavor-spec", default="bcc.ga4.c8m32")
    detail.add_argument("--disk-size", type=int, default=240)
    detail.add_argument("--eip-charge-mode", choices=["traffic", "bandwidth"], default="traffic")
    detail.add_argument("--bandwidth", type=int, default=100)
    detail.add_argument("--region", default="bj")
    detail.add_argument("--output", default="detailed_price_breakdown.json")

    simple = sub.add_parser("simple", help="对应原 baidu_bcc_price_top20.py 简表输出功能")
    simple.add_argument("--flavor-name", required=True)
    simple.add_argument("--disk-size", type=int, required=True)
    simple.add_argument("--eip-charge-mode", choices=["traffic", "bandwidth"], required=True)
    simple.add_argument("--region", default="bj")
    simple.add_argument("--bandwidth", type=int, default=1)
    simple.add_argument("--disk-type", default="enhanced_ssd_pl1")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if getattr(args, "disk_size", 20) < 20:
        raise ValueError("disk-size 最小为20GiB")

    if args.command == "top":
        handle_top(args)
        return
    if args.command == "detail":
        handle_detail(args)
        return
    if args.command == "simple":
        handle_simple(args)
        return


if __name__ == "__main__":
    main()
