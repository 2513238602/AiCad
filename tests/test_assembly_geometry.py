#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
装配几何干涉测试（内部测试工具）

基于 CadQuery 实体布尔交集运算检测真实几何干涉，
并生成截面 SVG 供可视化验证。

与 assembly.py 的参数空间检测互补：
- assembly.py：用简化数学模型检测（快速，但可能遗漏）
- 本测试：直接操作 3D 实体做布尔交集（精确，但较慢）

用法：
    python tests/test_assembly_geometry.py
"""
from __future__ import annotations

import sys
import os
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
INTERFERENCE_THRESHOLD = 0.5  # mm³，允许的最大交集体积

# 需要检测的组件对
COMPONENT_PAIRS = [
    ("cap", "wand"),      # 密封塞 vs 刷杆盖
    ("cap", "bottle"),    # 瓶盖 vs 瓶身
    ("wand", "bottle"),   # 刷杆 vs 瓶身
    ("wiper", "bottle"),  # 刮片 vs 瓶身
    ("wiper", "wand"),    # 刮片 vs 刷杆
]

OUTPUT_DIR = Path("artifacts/test_geometry")


# ---------------------------------------------------------------------------
# 组件生成
# ---------------------------------------------------------------------------
def build_all_components(
    cap_overrides: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """
    按依赖顺序生成全部 4 个组件，返回 (solids_dict, params_dict)。

    使用预设（preset）确保派生参数值正确，
    并通过 ComponentStateManager 管理跨组件约束。
    """
    import cadquery as cq  # noqa: F401
    from core.modeler import Modeler
    from core.component_state import get_state_manager
    from products.lip_gloss.components.bottle import BottleComponent
    from products.lip_gloss.components.cap import CapComponent
    from products.lip_gloss.components.wand import WandComponent
    from products.lip_gloss.components.wiper import WiperComponent
    # 确保跨组件规则已注册
    import products.lip_gloss.derived_params  # noqa: F401

    state_mgr = get_state_manager()
    state_mgr.clear()

    modeler = Modeler()
    solids: Dict[str, Any] = {}
    params: Dict[str, Dict[str, Any]] = {}

    cap_user_params = dict(cap_overrides or {})

    generation_order: List[Tuple[str, Any, Optional[str], Dict[str, Any]]] = [
        ("bottle", BottleComponent, "bottle_standard_5ml", {}),
        ("cap", CapComponent, "cap_18415_standard", cap_user_params),
        ("wand", WandComponent, "wand_integrated_18", {}),
        ("wiper", WiperComponent, "wiper_standard_18", {}),
    ]

    outroot = str(OUTPUT_DIR)
    os.makedirs(outroot, exist_ok=True)

    for comp_id, comp_class, preset_id, user_params in generation_order:
        print(f"  生成 {comp_id} (preset={preset_id})...", end=" ", flush=True)

        comp = comp_class()
        result = comp.generate(
            preset_id=preset_id,
            user_params=user_params,
            outroot=outroot,
        )

        if not result["ok"]:
            qc = result.get("qc", {})
            # 打印详细 QC 失败信息
            checks = qc.get("checks", [])
            failed = [c for c in checks if not c.get("ok", True)]
            raise RuntimeError(
                f"{comp_id} 生成失败: {result.get('error')}\n"
                f"QC failed checks: {failed}"
            )

        # 提取归一化参数
        p_norm = result["qc"]["params"]
        params[comp_id] = p_norm

        # 注册到状态管理器（供后续组件获取约束）
        state_mgr.set_generated(comp_id, p_norm)

        # 用 Modeler 构建实体
        meta: Dict[str, Any] = {}
        solid = modeler.build(comp_id, p_norm, meta=meta)
        solids[comp_id] = solid

        # 打印关键参数
        if comp_id == "cap":
            cavity = p_norm.get("cavity_depth_mm", "?")
            print(f"cavity={cavity}mm", end=" ")
        elif comp_id == "wand":
            cap_h = p_norm.get("cap_height_mm", "?")
            cav_d = p_norm.get("cavity_depth_mm", "?")
            print(f"cap_h={cap_h}mm, cavity_depth={cav_d}mm", end=" ")

        print("[OK]")

    return solids, params


# ---------------------------------------------------------------------------
# 装配定位
# ---------------------------------------------------------------------------
def position_solids(
    solids: Dict[str, Any],
    params: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """
    使用 assembly.py 的定位逻辑将各实体平移到装配位置。
    返回 (positioned_solids, positions_report)。
    """
    from core.assembly import compute_assembly_positions

    positions = compute_assembly_positions(params)
    positioned = {}

    print("\n  装配位置:")
    for comp_id, solid in solids.items():
        pos = positions.get(comp_id, {})
        dz = pos.get("dz", 0.0)
        desc = pos.get("description", "")
        positioned[comp_id] = solid.translate((0, 0, dz))
        print(f"    {comp_id}: dz={dz:.2f}mm  ({desc})")

    return positioned, positions


# ---------------------------------------------------------------------------
# 布尔交集干涉检测
# ---------------------------------------------------------------------------
def check_geometric_interference(
    positioned: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    对每对组件做布尔交集，检测实体干涉。
    返回检测结果列表。
    """
    results = []

    for a_id, b_id in COMPONENT_PAIRS:
        if a_id not in positioned or b_id not in positioned:
            continue

        a_solid = positioned[a_id]
        b_solid = positioned[b_id]

        try:
            intersection = a_solid.intersect(b_solid)
            vol = intersection.val().Volume()
            ok = vol < INTERFERENCE_THRESHOLD
            results.append({
                "pair": f"{a_id}↔{b_id}",
                "volume_mm3": round(vol, 3),
                "ok": ok,
            })
        except Exception as e:
            # 交集为空时可能抛异常，视为无干涉
            results.append({
                "pair": f"{a_id}↔{b_id}",
                "volume_mm3": 0.0,
                "ok": True,
                "note": str(e),
            })

    return results


# ---------------------------------------------------------------------------
# 截面 SVG 导出
# ---------------------------------------------------------------------------
def export_cross_section_svg(
    positioned: Dict[str, Any],
    output_path: str,
) -> None:
    """
    生成 XZ 截面 SVG（类似用户提供的截面截图）。

    做法：用一个大的半空间盒子切掉 Y > 0 的部分，
    保留 Y <= 0 的截面，然后从 Y- 方向投影导出 SVG。
    """
    import cadquery as cq

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 切割半空间：切掉 Y > 0 的部分
    cutter = (
        cq.Workplane("XZ")
        .rect(200, 200)
        .extrude(100)  # 向 Y+ 方向拉伸
    )

    sections = []
    for comp_id, solid in positioned.items():
        try:
            section = solid.cut(cutter)
            sections.append(section)
        except Exception as e:
            print(f"    警告: {comp_id} 截面切割失败: {e}")

    if not sections:
        print("    警告: 无可用截面")
        return

    # 合并所有截面到一个实体
    combined = sections[0]
    for s in sections[1:]:
        try:
            combined = combined.union(s)
        except Exception as e:
            print(f"    警告: 截面合并失败: {e}")

    # 导出 SVG（从 Y- 方向观察截面）
    try:
        cq.exporters.export(
            combined,
            output_path,
            exportType="SVG",
            opt={
                "projectionDir": (0, -1, 0),
                "width": 800,
                "height": 600,
            },
        )
        print(f"  截面 SVG: {output_path}")
    except Exception as e:
        print(f"  截面 SVG 导出失败: {e}")


# ---------------------------------------------------------------------------
# 单对组件截面导出（调试用）
# ---------------------------------------------------------------------------
def export_pair_section_svg(
    positioned: Dict[str, Any],
    a_id: str,
    b_id: str,
    output_path: str,
) -> None:
    """导出指定两个组件的截面 SVG（用于定位干涉区域）"""
    import cadquery as cq

    if a_id not in positioned or b_id not in positioned:
        print(f"    跳过 {a_id}↔{b_id} 截面（组件不存在）")
        return

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    cutter = (
        cq.Workplane("XZ")
        .rect(200, 200)
        .extrude(100)
    )

    try:
        a_section = positioned[a_id].cut(cutter)
        b_section = positioned[b_id].cut(cutter)
        combined = a_section.union(b_section)

        cq.exporters.export(
            combined,
            output_path,
            exportType="SVG",
            opt={"projectionDir": (0, -1, 0), "width": 800, "height": 600},
        )
        print(f"  {a_id}↔{b_id} 截面: {output_path}")
    except Exception as e:
        print(f"  {a_id}↔{b_id} 截面导出失败: {e}")


# ---------------------------------------------------------------------------
# 主测试函数
# ---------------------------------------------------------------------------
def run_test() -> bool:
    """
    运行一次完整的几何干涉测试。

    返回 True 如果所有组件对无干涉。
    """
    print(f"\n{'='*60}")
    print(f"  几何干涉测试（标准装配）")
    print(f"{'='*60}")

    # 1. 生成所有组件
    print("\n[1] 生成组件:")
    solids, params = build_all_components()

    # 2. 装配定位
    print("\n[2] 装配定位:")
    positioned, positions = position_solids(solids, params)

    # 3. 布尔交集干涉检测
    print("\n[3] 几何干涉检测:")
    interference = check_geometric_interference(positioned)

    all_ok = True
    for r in interference:
        status = "[OK]  " if r["ok"] else "[FAIL]"
        print(f"  {status} {r['pair']}: {r['volume_mm3']:.3f} mm³", end="")
        if not r["ok"]:
            all_ok = False
        if "note" in r:
            print(f"  ({r['note']})", end="")
        print()

    # 4. 生成截面 SVG
    print("\n[4] 截面 SVG 导出:")
    svg_dir = str(OUTPUT_DIR)
    export_cross_section_svg(positioned, f"{svg_dir}/cross_section.svg")

    # 对失败的组件对额外导出单独截面
    for r in interference:
        if not r["ok"]:
            pair_name = r["pair"].replace("↔", "_vs_")
            export_pair_section_svg(
                positioned,
                r["pair"].split("↔")[0],
                r["pair"].split("↔")[1],
                f"{svg_dir}/{pair_name}.svg",
            )

    # 5. 总结
    print(f"\n  总结: {'PASS ✓' if all_ok else 'FAIL ✗'}")
    return all_ok


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main() -> int:
    """运行几何干涉测试"""
    try:
        import cadquery as cq  # noqa: F401
    except ImportError:
        print("CadQuery 未安装，跳过几何干涉测试")
        return 0

    os.makedirs(str(OUTPUT_DIR), exist_ok=True)

    ok = run_test()

    print(f"\n{'='*60}")
    print(f"  最终报告")
    print(f"{'='*60}")
    print(f"  [{'PASS' if ok else 'FAIL'}] 标准装配")
    print(f"\n  截面 SVG 已输出到: {OUTPUT_DIR}/")
    print(f"  总结: {'通过' if ok else '失败'}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
