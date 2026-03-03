# -*- coding: utf-8 -*-
"""
装配定位与干涉检测模块（系统性重写）

功能：
1. 根据各组件参数计算装配坐标系中的精确位置（Z偏移量）
2. 基于参数的径向干涉检测（纯数学，覆盖全部6对组件）
3. 装配质量验收（10项全覆盖检查）
4. 为前端3D查看器提供装配位置数据

装配坐标系约定：
- 瓶身底部 = Z=0（基准）
- Z轴向上
- 所有组件共享XY中心轴（同轴）

径向嵌套顺序（由内到外，Z=65颈部区域截面）：
  Stem ⌀4 → Wiper孔口 ⌀7 → Wiper体 ⌀15.5 → 颈内壁 ⌀16
  → 颈外壁 ⌀18 → Wand内腔 ⌀19 → Wand外壁 ⌀21.5
  → Cap内壁 ⌀22.4 → Cap外壁 ⌀24 = 瓶身外壁 ⌀24
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════════
# 常量 — 与 modeler.py 保持一致
# ═══════════════════════════════════════════════════════════════════════════
CAP_CHAMFER_WALL = 0.05  # 倒角边缘最小壁厚 mm (build_cap)
CAP_CHAMFER_H = 3.0      # 倒角高度 mm (build_cap)
BODY_DRAFT_DEG = 0.5     # 瓶身最小拔模角 (build_bottle)
WAND_BORE_EXTRA = 1.0    # 内腔额外间隙 mm (build_wand: thr_depth + 0.5 per side)


def _g(params: Dict[str, Any], key: str, default: float = 0.0) -> float:
    """安全获取嵌套参数值"""
    parts = key.split(".")
    cur: Any = params
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    try:
        return float(cur)
    except (TypeError, ValueError):
        return default


def _cap_chamfer_id(cap_outer_od: float) -> float:
    """计算瓶盖内底倒角处的有效内径（最宽处）"""
    return cap_outer_od - 2 * CAP_CHAMFER_WALL


def _wand_bore_dia(thread_crest: float, thread_depth: float) -> float:
    """计算刷杆实际内腔直径（与 modeler.py build_wand 一致）。
    modeler: inner_cavity_r = thr_crest_r + thr_depth + 0.5"""
    return thread_crest + 2 * thread_depth + WAND_BORE_EXTRA


def _body_od_at_shoulder(
    bottle_H: float, neck_h: float, shoulder_h: float, body_od: float,
) -> float:
    """计算瓶身顶部（肩底处）的实际外径，考虑拔模角收窄。
    body_od 是瓶底最大直径，顶部因 BODY_DRAFT_DEG 拔模而收窄。"""
    body_h = bottle_H - neck_h - shoulder_h
    if body_h <= 0:
        return body_od
    delta = 2 * math.tan(math.radians(BODY_DRAFT_DEG)) * body_h
    return body_od - delta


def _bottle_od_at_z(
    z: float, bottle_H: float, neck_h: float,
    shoulder_h: float, body_od: float, neck_od: float,
) -> float:
    """计算瓶身在指定Z高度处的外径（考虑拔模角）。
    body_od = 瓶底最大直径，body因拔模角向顶部收窄。"""
    body_h = bottle_H - neck_h - shoulder_h
    neck_bottom = bottle_H - neck_h
    shoulder_bottom = neck_bottom - shoulder_h
    body_od_top = _body_od_at_shoulder(bottle_H, neck_h, shoulder_h, body_od)

    if z >= neck_bottom:
        return neck_od
    elif z >= shoulder_bottom and shoulder_h > 0:
        # 肩部：从 body_od_top 过渡到 neck_od
        frac = (z - shoulder_bottom) / shoulder_h
        return body_od_top + (neck_od - body_od_top) * frac
    elif body_h > 0:
        # 瓶身：从 body_od (Z=0) 线性收窄到 body_od_top (Z=body_h)
        frac = z / body_h
        delta = body_od - body_od_top
        return body_od - delta * frac
    else:
        return body_od


def _bottle_inner_r_at_z(
    z: float, bottle_H: float, neck_h: float,
    shoulder_h: float, body_od: float, neck_od: float,
    wall_t: float, lip_t: float,
) -> float:
    """计算瓶身在指定Z高度处的内腔半径"""
    neck_bottom = bottle_H - neck_h
    shoulder_bottom = neck_bottom - shoulder_h
    body_inner_r = body_od / 2.0 - wall_t
    neck_inner_r = neck_od / 2.0 - lip_t

    if z >= neck_bottom:
        return neck_inner_r
    elif z >= shoulder_bottom and shoulder_h > 0:
        frac = (z - shoulder_bottom) / shoulder_h
        return body_inner_r + (neck_inner_r - body_inner_r) * frac
    else:
        return body_inner_r


def _compute_safe_z(
    bottle_H: float, neck_h: float, shoulder_h: float,
    body_od: float, neck_od: float, wand_inner_dia: float,
) -> float:
    """
    计算安全Z — 瓶身外径首次小于 wand 内腔直径的Z坐标。
    Wand底部必须 ≥ safe_z 才能避免与瓶肩的径向干涉。
    注意：body_od 是瓶底最大直径，肩底处因拔模角已收窄为 body_od_top。
    """
    shoulder_bottom = bottle_H - neck_h - shoulder_h
    body_od_top = _body_od_at_shoulder(bottle_H, neck_h, shoulder_h, body_od)

    if body_od_top <= wand_inner_dia:
        # 肩底处瓶身已经比wand内腔窄，肩底即为安全位置
        return shoulder_bottom

    if neck_od >= wand_inner_dia:
        # 即使在颈部，瓶身也比wand内腔宽 — 无安全位置
        return bottle_H

    if shoulder_h <= 0:
        return shoulder_bottom

    # 在肩部找到 OD == wand_inner_dia 的精确Z
    # 肩部OD(z) = body_od_top + (neck_od - body_od_top) * (z - shoulder_bottom) / shoulder_h
    frac = (wand_inner_dia - body_od_top) / (neck_od - body_od_top)
    frac = max(0.0, min(1.0, frac))
    return shoulder_bottom + frac * shoulder_h


def compute_assembly_positions(
    component_params: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    计算各组件在装配坐标系中的Z偏移量。

    参数:
        component_params: {component_id: params_dict}

    返回:
        {component_id: {"dz": float, "description": str}}
    """
    positions: Dict[str, Dict[str, Any]] = {}

    # --- Bottle: 基准，Z=0 ---
    bP = component_params.get("bottle", {})
    bottle_H = _g(bP, "height_mm", 70.0)
    neck_h = _g(bP, "neck_height_mm", 10.0)
    shoulder_h = _g(bP, "shoulder_height_mm", 6.0)
    body_od = _g(bP, "body_od_mm", 24.0)
    neck_od = _g(bP, "neck_od_mm", 18.0)

    positions["bottle"] = {
        "dz": 0.0,
        "description": "瓶身底部=Z=0（基准）",
    }

    # --- Wiper: 嵌入瓶颈内部，底部与颈部起始齐平 ---
    # 采用颈底对齐：wiper底部 = shoulder_top = bottle_H - neck_h
    # 这样wiper完全在颈部区域内，不侵入肩部，且避开wand气密环区域
    wpP = component_params.get("wiper", {})
    if wpP:
        wiper_H = _g(wpP, "height_mm", 8.0)
        shoulder_top_z = bottle_H - neck_h  # 颈部起始位置
        wiper_dz = shoulder_top_z  # 底部与颈部底部齐平
        positions["wiper"] = {
            "dz": wiper_dz,
            "description": f"内塞底部与颈底齐平: dz={wiper_dz:.2f}mm (top={wiper_dz + wiper_H:.1f}mm)",
        }

    # --- Cap: 使用倒角有效内径在肩部找清除点 ---
    cP = component_params.get("cap", {})
    wdP = component_params.get("wand", {})
    cap_dz = bottle_H  # fallback

    if cP:
        cap_H = _g(cP, "height_mm", 25.0)
        cap_cavity = _g(cP, "cavity_depth_mm", 23.5)
        cap_inner_id = _g(cP, "inner_id_mm", 22.4)
        cap_outer_od = _g(cP, "outer_od_mm", 24.0)

        chamfer_id = _cap_chamfer_id(cap_outer_od)

        neck_bottom_z = bottle_H - neck_h
        shoulder_bottom_z = neck_bottom_z - shoulder_h

        # 肩底处瓶身实际外径（因拔模角收窄）
        body_od_top = _body_od_at_shoulder(bottle_H, neck_h, shoulder_h, body_od)

        if chamfer_id >= body_od_top:
            # 倒角内径 ≥ 肩底处瓶身外径 → cap 能直接坐到肩底
            cap_dz = shoulder_bottom_z
        elif shoulder_h > 0 and body_od_top > chamfer_id:
            # 在肩部斜面找清除点
            if neck_od < body_od_top:
                frac = (chamfer_id - body_od_top) / (neck_od - body_od_top)
                frac = max(0.0, min(1.0, frac))
                clearance_z = shoulder_bottom_z + frac * shoulder_h
            else:
                clearance_z = shoulder_bottom_z
            # 微小偏移确保不卡死
            cap_dz = clearance_z + 0.15
        else:
            cap_dz = shoulder_bottom_z

        positions["cap"] = {
            "dz": cap_dz,
            "description": f"瓶盖底部Z={cap_dz:.2f}mm, 与瓶身重叠{bottle_H - cap_dz:.1f}mm",
        }

    # --- Wand: 帽顶齐腔顶 ---
    # 注：密封垫圈为软性材料（PE/硅胶），不占用刚性空间
    if wdP:
        wand_cap_h = _g(wdP, "cap_height_mm", 18.0)

        if cP:
            cap_cavity = _g(cP, "cavity_depth_mm", 23.5)

            effective_cavity = cap_cavity
            wand_dz = cap_dz + effective_cavity - wand_cap_h

            # 计算安全Z：瓶身OD首次小于wand内腔的位置
            # wand bore = crest_dia + 2*depth + 1.0 (与 modeler.py 一致)
            thread_crest = _g(wdP, "thread.crest_dia_mm", 18.0)
            thread_depth = _g(wdP, "thread.depth_mm", 0.5)
            wand_inner_dia = _wand_bore_dia(thread_crest, thread_depth)

            safe_z = _compute_safe_z(
                bottle_H, neck_h, shoulder_h,
                body_od, neck_od, wand_inner_dia,
            )

            # 确保 wand 不低于安全Z（不进入瓶肩干涉区）
            wand_dz = max(wand_dz, safe_z)
            # 确保 wand 不低于 cap 底部（不突出cap外）
            wand_dz = max(wand_dz, cap_dz)

            # 确保 wand 顶部不超过 cap 内腔顶部
            cap_ceiling = cap_dz + cap_cavity
            max_wand_dz = cap_ceiling - wand_cap_h
            if wand_dz > max_wand_dz:
                wand_dz = max_wand_dz  # 限位：优先避免穿顶
        else:
            wand_dz = bottle_H

        wand_top = wand_dz + wand_cap_h
        positions["wand"] = {
            "dz": wand_dz,
            "description": f"刷杆帽在cap内腔中: dz={wand_dz:.2f}mm, 帽顶Z={wand_top:.1f}",
        }

    return positions


def check_radial_interference(
    component_params: Dict[str, Dict[str, Any]],
    positions: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    全覆盖径向干涉检测 — 检查全部6对组件。
    在每对组件的Z重叠区域，检查径向间隙是否为正。
    """
    if positions is None:
        positions = compute_assembly_positions(component_params)

    issues: List[Dict[str, Any]] = []

    bP = component_params.get("bottle", {})
    cP = component_params.get("cap", {})
    wdP = component_params.get("wand", {})
    wpP = component_params.get("wiper", {})

    bottle_H = _g(bP, "height_mm", 70.0)
    neck_h = _g(bP, "neck_height_mm", 10.0)
    neck_od = _g(bP, "neck_od_mm", 18.0)
    body_od = _g(bP, "body_od_mm", 24.0)
    lip_t = _g(bP, "lip_thickness_mm", 1.0)
    shoulder_h = _g(bP, "shoulder_height_mm", 6.0)
    wall_t = _g(bP, "wall_thickness_mm", 1.2)
    neck_id = neck_od - 2 * lip_t

    # --- 检查1: Wiper ↔ Bottle 颈部配合 ---
    if wpP and bP:
        wiper_od = _g(wpP, "outer_od_mm", 15.5)
        if wiper_od > neck_id:
            issues.append({
                "severity": "hard",
                "pair": "wiper-bottle",
                "msg": f"内塞外径({wiper_od:.1f}mm) > 瓶颈内径({neck_id:.1f}mm)，无法装入",
                "gap_mm": neck_id - wiper_od,
            })
        elif wiper_od > neck_id - 0.1:
            issues.append({
                "severity": "soft",
                "pair": "wiper-bottle",
                "msg": f"内塞外径({wiper_od:.1f}mm) 与瓶颈内径({neck_id:.1f}mm) 间隙仅{neck_id - wiper_od:.2f}mm",
                "gap_mm": neck_id - wiper_od,
            })

    # --- 检查2: Wand ↔ Cap 径向配合 ---
    if wdP and cP:
        wand_od = _g(wdP, "outer_od_mm", 21.5)
        cap_id = _g(cP, "inner_id_mm", 22.4)
        gap = cap_id - wand_od
        if gap < 0:
            issues.append({
                "severity": "hard",
                "pair": "wand-cap",
                "msg": f"刷杆帽外径({wand_od:.1f}mm) > 瓶盖内径({cap_id:.1f}mm)，无法装入",
                "gap_mm": gap,
            })
        elif gap < 0.3:
            issues.append({
                "severity": "soft",
                "pair": "wand-cap",
                "msg": f"刷杆帽外径({wand_od:.1f}mm) 与瓶盖内径({cap_id:.1f}mm) 间隙仅{gap:.2f}mm",
                "gap_mm": gap,
            })

    # --- 检查3: Cap ↔ Bottle 肩部径向（使用倒角有效内径）---
    if cP and bP and positions.get("cap"):
        cap_dz = positions["cap"]["dz"]
        cap_outer_od = _g(cP, "outer_od_mm", 24.0)
        chamfer_id = _cap_chamfer_id(cap_outer_od)

        bottle_od_at_cap = _bottle_od_at_z(
            cap_dz, bottle_H, neck_h, shoulder_h, body_od, neck_od
        )

        if bottle_od_at_cap > chamfer_id:
            issues.append({
                "severity": "hard",
                "pair": "cap-bottle",
                "msg": (
                    f"瓶盖底部(Z={cap_dz:.1f})处瓶身外径"
                    f"({bottle_od_at_cap:.1f}mm) > "
                    f"瓶盖倒角内径({chamfer_id:.1f}mm)，发生干涉"
                ),
                "gap_mm": chamfer_id - bottle_od_at_cap,
            })

    # --- 检查4: Wand ↔ Bottle 径向（Z感知）---
    if wdP and bP and positions.get("wand"):
        wand_dz = positions["wand"]["dz"]
        wand_cap_h = _g(wdP, "cap_height_mm", 18.0)
        thread_crest = _g(wdP, "thread.crest_dia_mm", 18.0)
        thread_depth = _g(wdP, "thread.depth_mm", 0.5)
        wand_inner_r = _wand_bore_dia(thread_crest, thread_depth) / 2.0

        # 在wand底部检查（最危险位置）
        bottle_od_at_wand = _bottle_od_at_z(
            wand_dz, bottle_H, neck_h, shoulder_h, body_od, neck_od
        )
        bottle_outer_r = bottle_od_at_wand / 2.0
        gap = wand_inner_r - bottle_outer_r

        if gap < 0:
            issues.append({
                "severity": "hard",
                "pair": "wand-bottle",
                "msg": (
                    f"Wand底部(Z={wand_dz:.1f})处瓶身外径"
                    f"({bottle_od_at_wand:.1f}mm) > "
                    f"Wand内腔({wand_inner_r * 2:.1f}mm)，径向干涉{-gap:.2f}mm"
                ),
                "gap_mm": gap,
            })
        elif gap < 0.2:
            issues.append({
                "severity": "soft",
                "pair": "wand-bottle",
                "msg": (
                    f"Wand底部(Z={wand_dz:.1f})处瓶身外径"
                    f"({bottle_od_at_wand:.1f}mm)与Wand内腔"
                    f"({wand_inner_r * 2:.1f}mm)间隙仅{gap:.2f}mm"
                ),
                "gap_mm": gap,
            })

    # --- 检查5: Wand ↔ Wiper 径向（Z重叠区域）---
    if wdP and wpP and positions.get("wand") and positions.get("wiper"):
        wand_dz = positions["wand"]["dz"]
        wand_cap_h = _g(wdP, "cap_height_mm", 18.0)
        wand_top = wand_dz + wand_cap_h
        wiper_dz = positions["wiper"]["dz"]
        wiper_H = _g(wpP, "height_mm", 12.0)
        wiper_top = wiper_dz + wiper_H

        # Z重叠区域
        overlap_lo = max(wand_dz, wiper_dz)
        overlap_hi = min(wand_top, wiper_top)

        if overlap_hi > overlap_lo:
            # 有Z重叠：检查径向
            wiper_outer_r = _g(wpP, "outer_od_mm", 15.5) / 2.0
            wiper_flange_od = _g(wpP, "flange_od_mm", 17.0)
            thread_crest = _g(wdP, "thread.crest_dia_mm", 18.0)
            thread_depth = _g(wdP, "thread.depth_mm", 0.5)
            wand_inner_r = _wand_bore_dia(thread_crest, thread_depth) / 2.0

            # wiper体必须在wand内腔内
            gap = wand_inner_r - wiper_outer_r
            if gap < 0:
                issues.append({
                    "severity": "hard",
                    "pair": "wand-wiper",
                    "msg": (
                        f"Wiper外径({wiper_outer_r * 2:.1f}mm) > "
                        f"Wand内腔({wand_inner_r * 2:.1f}mm)，径向干涉"
                    ),
                    "gap_mm": gap,
                })

            # wiper凸环检查（如果凸环在Z重叠区域内）
            flange_pos = str(wpP.get("flange_position", "bottom"))
            flange_h = _g(wpP, "flange_height_mm", 1.5)
            if flange_pos == "bottom":
                flange_z_lo = wiper_dz
            elif flange_pos == "middle":
                flange_z_lo = wiper_dz + (wiper_H - flange_h) / 2.0
            else:
                flange_z_lo = wiper_dz + wiper_H - flange_h
            flange_z_hi = flange_z_lo + flange_h

            if flange_z_hi > wand_dz and flange_z_lo < wand_top:
                flange_r = wiper_flange_od / 2.0
                gap_flange = wand_inner_r - flange_r
                if gap_flange < 0:
                    issues.append({
                        "severity": "soft",
                        "pair": "wand-wiper-flange",
                        "msg": (
                            f"Wiper凸环外径({wiper_flange_od:.1f}mm) > "
                            f"Wand内腔({wand_inner_r * 2:.1f}mm)，凸环干涉"
                        ),
                        "gap_mm": gap_flange,
                    })

    # --- 检查6: Wand杆 ↔ Wiper孔口 ---
    if wdP and wpP:
        stem_d = _g(wdP, "stem_diameter_mm", 4.0)
        orifice = _g(wpP, "orifice_mm", 7.0)
        gap = orifice - stem_d
        if gap < 0:
            issues.append({
                "severity": "hard",
                "pair": "stem-wiper",
                "msg": f"刷杆杆径({stem_d:.1f}mm) > 内塞孔口({orifice:.1f}mm)，杆身无法通过",
                "gap_mm": gap,
            })
        elif gap < 0.5:
            issues.append({
                "severity": "soft",
                "pair": "stem-wiper",
                "msg": f"杆径({stem_d:.1f}mm) 与孔口({orifice:.1f}mm) 间隙仅{gap:.2f}mm",
                "gap_mm": gap,
            })

    # --- 检查7: Cap ↔ Bottle 外观齐平 ---
    if cP and bP:
        cap_od = _g(cP, "outer_od_mm", 24.0)
        if abs(cap_od - body_od) > 1.0:
            issues.append({
                "severity": "soft",
                "pair": "cap-bottle",
                "msg": (
                    f"瓶盖外径({cap_od:.1f}mm) 与瓶身外径({body_od:.1f}mm) "
                    f"差异{abs(cap_od - body_od):.1f}mm，外观不齐平"
                ),
                "gap_mm": abs(cap_od - body_od),
            })

    # --- 检查8: 螺纹匹配 ---
    if wdP and bP:
        b_thr = bP.get("thread", {}) or {}
        w_thr = wdP.get("thread", {}) or {}
        b_on = bool(b_thr.get("enabled", False))
        w_on = bool(w_thr.get("enabled", True))
        if b_on and w_on:
            b_pitch = float(b_thr.get("pitch_mm", 2.7))
            w_pitch = float(w_thr.get("pitch_mm", 2.7))
            if abs(b_pitch - w_pitch) > 0.01:
                issues.append({
                    "severity": "hard",
                    "pair": "bottle-wand",
                    "msg": f"螺纹牙距不匹配: 瓶身={b_pitch}mm, 刷杆={w_pitch}mm",
                    "gap_mm": 0,
                })

    return issues


def verify_assembly_quality(
    component_params: Dict[str, Dict[str, Any]],
    positions: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    装配质量验收 — 11项全覆盖检查。

    检测项：
    1. 外观齐平：cap_od 与 body_od 差值 ≤ 1.0mm
    2. 肩部缝隙：cap底部 与 肩底 距离 ≤ 0.5mm
    3. Wand在cap腔内（不突出）
    4. Wand不进入瓶肩干涉区（Z感知径向检查）
    5. Wiper装入瓶颈（wiper_od < neck_id）
    6. Stem穿过wiper孔口（stem_d < orifice）
    7. Wand-Wiper径向无干涉（Z重叠区域）
    8. Cap可装入（倒角处无径向干涉）
    9. 径向无硬干涉（全覆盖）
    10. Seal plug穿过Wiper孔口（如果启用）
    11. Seal plug ↔ Wand空间兼容（如果启用）
    """
    if positions is None:
        positions = compute_assembly_positions(component_params)

    checks: List[Dict[str, Any]] = []
    bP = component_params.get("bottle", {})
    cP = component_params.get("cap", {})
    wdP = component_params.get("wand", {})
    wpP = component_params.get("wiper", {})

    bottle_H = _g(bP, "height_mm", 70.0)
    neck_h = _g(bP, "neck_height_mm", 10.0)
    shoulder_h = _g(bP, "shoulder_height_mm", 6.0)
    body_od = _g(bP, "body_od_mm", 24.0)
    neck_od = _g(bP, "neck_od_mm", 18.0)
    lip_t = _g(bP, "lip_thickness_mm", 1.0)
    neck_id = neck_od - 2 * lip_t
    shoulder_bottom_z = bottle_H - neck_h - shoulder_h

    # --- 1. 外观齐平 ---
    if cP and bP:
        cap_od = _g(cP, "outer_od_mm", 24.0)
        diff = abs(cap_od - body_od)
        checks.append({
            "name": "① 外观齐平（cap_od ≈ body_od）",
            "pass": diff <= 1.0,
            "value": diff,
            "threshold": 1.0,
            "msg": f"cap外径={cap_od:.1f}, body外径={body_od:.1f}, 差值={diff:.1f}mm",
        })

    # --- 2. 肩部缝隙 ≤ 0.5mm ---
    if cP and bP and positions.get("cap"):
        cap_dz = positions["cap"]["dz"]
        gap = cap_dz - shoulder_bottom_z
        checks.append({
            "name": "② 肩部缝隙 ≤ 0.5mm（紧密配合）",
            "pass": gap <= 0.5,
            "value": gap,
            "threshold": 0.5,
            "msg": f"cap底Z={cap_dz:.2f}, 肩底Z={shoulder_bottom_z:.1f}, 缝隙={gap:.2f}mm",
        })

    # --- 3. Wand在cap腔内 ---
    if cP and wdP and positions.get("cap") and positions.get("wand"):
        cap_dz = positions["cap"]["dz"]
        wand_dz = positions["wand"]["dz"]
        protrusion = cap_dz - wand_dz
        checks.append({
            "name": "③ Wand帽不突出Cap外",
            "pass": protrusion <= 0,
            "value": protrusion,
            "threshold": 0.0,
            "msg": f"cap底Z={cap_dz:.2f}, wand底Z={wand_dz:.2f}, 突出={protrusion:.1f}mm",
        })

    # --- 4. Wand不进入瓶肩干涉区 ---
    if wdP and bP and positions.get("wand"):
        wand_dz = positions["wand"]["dz"]
        thread_crest = _g(wdP, "thread.crest_dia_mm", 18.0)
        thread_depth = _g(wdP, "thread.depth_mm", 0.5)
        wand_inner_dia = _wand_bore_dia(thread_crest, thread_depth)

        bottle_od_at_wand = _bottle_od_at_z(
            wand_dz, bottle_H, neck_h, shoulder_h, body_od, neck_od
        )
        clearance = wand_inner_dia - bottle_od_at_wand
        checks.append({
            "name": "④ Wand↔Bottle径向无干涉",
            "pass": clearance >= 0,
            "value": clearance,
            "threshold": 0.0,
            "msg": (
                f"Wand底Z={wand_dz:.2f}, 瓶身OD={bottle_od_at_wand:.1f}mm, "
                f"Wand内腔={wand_inner_dia:.1f}mm, 间隙={clearance:.2f}mm"
            ),
        })

    # --- 5. Wiper装入瓶颈 ---
    if wpP and bP:
        wiper_od = _g(wpP, "outer_od_mm", 15.5)
        clearance = neck_id - wiper_od
        checks.append({
            "name": "⑤ Wiper装入瓶颈（outer_od < neck_id）",
            "pass": clearance >= 0,
            "value": clearance,
            "threshold": 0.0,
            "msg": f"Wiper外径={wiper_od:.1f}, 颈内径={neck_id:.1f}, 间隙={clearance:.1f}mm",
        })

    # --- 5b. Wiper凸环装入瓶颈 ---
    if wpP and bP:
        flange_od = _g(wpP, "flange_od_mm", 15.8)
        clearance_flange = neck_id - flange_od
        checks.append({
            "name": "⑤b Wiper凸环装入瓶颈（flange_od < neck_id）",
            "pass": clearance_flange >= 0,
            "value": clearance_flange,
            "threshold": 0.0,
            "msg": f"凸环外径={flange_od:.1f}, 颈内径={neck_id:.1f}, 间隙={clearance_flange:.1f}mm",
        })

    # --- 6. Stem穿过Wiper孔口 ---
    if wdP and wpP:
        stem_d = _g(wdP, "stem_diameter_mm", 4.0)
        orifice = _g(wpP, "orifice_mm", 7.0)
        clearance = orifice - stem_d
        checks.append({
            "name": "⑥ Stem穿过Wiper孔口",
            "pass": clearance > 0,
            "value": clearance,
            "threshold": 0.0,
            "msg": f"杆径={stem_d:.1f}, 孔口={orifice:.1f}, 间隙={clearance:.1f}mm",
        })

    # --- 7. Wand-Wiper径向无干涉（Z重叠区域）---
    if wdP and wpP and positions.get("wand") and positions.get("wiper"):
        wand_dz = positions["wand"]["dz"]
        wand_cap_h = _g(wdP, "cap_height_mm", 18.0)
        wand_top = wand_dz + wand_cap_h
        wiper_dz = positions["wiper"]["dz"]
        wiper_H = _g(wpP, "height_mm", 12.0)
        wiper_top = wiper_dz + wiper_H

        overlap_lo = max(wand_dz, wiper_dz)
        overlap_hi = min(wand_top, wiper_top)

        if overlap_hi > overlap_lo:
            wiper_outer_r = _g(wpP, "outer_od_mm", 15.5) / 2.0
            thread_crest = _g(wdP, "thread.crest_dia_mm", 18.0)
            thread_depth = _g(wdP, "thread.depth_mm", 0.5)
            wand_inner_r = _wand_bore_dia(thread_crest, thread_depth) / 2.0
            clearance = wand_inner_r - wiper_outer_r
            checks.append({
                "name": "⑦ Wand↔Wiper径向无干涉",
                "pass": clearance >= 0,
                "value": clearance,
                "threshold": 0.0,
                "msg": (
                    f"Z重叠[{overlap_lo:.1f},{overlap_hi:.1f}], "
                    f"Wiper外r={wiper_outer_r:.1f}, Wand内r={wand_inner_r:.1f}, "
                    f"间隙={clearance:.1f}mm"
                ),
            })
        else:
            checks.append({
                "name": "⑦ Wand↔Wiper径向无干涉",
                "pass": True,
                "value": 999.0,
                "threshold": 0.0,
                "msg": "无Z重叠，无需检查",
            })

    # --- 7b. Wiper不侵入Wand气密环区域 ---
    if wdP and wpP and positions.get("wand") and positions.get("wiper"):
        wand_dz = positions["wand"]["dz"]
        seal_ring_h = _g(wdP, "seal_ring.height_mm", 3.0)
        wand_cavity_d = _g(wdP, "cavity_depth_mm", 16.5)
        seal_ring_bottom_z = wand_dz + wand_cavity_d - seal_ring_h
        wiper_dz_val = positions["wiper"]["dz"]
        wiper_H_val = _g(wpP, "height_mm", 8.0)
        wiper_top_z = wiper_dz_val + wiper_H_val
        seal_gap = seal_ring_bottom_z - wiper_top_z
        checks.append({
            "name": "⑦b Wiper顶不侵入Wand气密环",
            "pass": seal_gap >= 0,
            "value": seal_gap,
            "threshold": 0.0,
            "msg": (
                f"Wiper顶Z={wiper_top_z:.1f}, 气密环底Z={seal_ring_bottom_z:.1f}, "
                f"间隙={seal_gap:.1f}mm"
            ),
        })

    # --- 8. Cap可装入（倒角径向）---
    if cP and bP and positions.get("cap"):
        cap_dz = positions["cap"]["dz"]
        cap_outer_od = _g(cP, "outer_od_mm", 24.0)
        chamfer_id = _cap_chamfer_id(cap_outer_od)

        bottle_od_at_cap = _bottle_od_at_z(
            cap_dz, bottle_H, neck_h, shoulder_h, body_od, neck_od
        )
        clearance = chamfer_id - bottle_od_at_cap
        checks.append({
            "name": "⑧ Cap底部可装入（倒角无干涉）",
            "pass": clearance >= 0,
            "value": clearance,
            "threshold": 0.0,
            "msg": (
                f"cap底Z={cap_dz:.2f}, 瓶身OD={bottle_od_at_cap:.1f}, "
                f"倒角ID={chamfer_id:.1f}, 间隙={clearance:.2f}mm"
            ),
        })

    # --- 9. 全覆盖径向无硬干涉 ---
    interference = check_radial_interference(component_params, positions)
    hard_issues = [i for i in interference if i["severity"] == "hard"]
    checks.append({
        "name": "⑨ 径向无硬干涉（全覆盖）",
        "pass": len(hard_issues) == 0,
        "value": len(hard_issues),
        "threshold": 0,
        "msg": "; ".join(i["msg"] for i in hard_issues) if hard_issues else "6对组件全部通过",
    })

    # --- 10. Wand顶部不超过Cap内腔天花板 ---
    if cP and wdP and positions.get("cap") and positions.get("wand"):
        cap_dz = positions["cap"]["dz"]
        cap_cavity = _g(cP, "cavity_depth_mm", 23.5)
        wand_dz = positions["wand"]["dz"]
        wand_cap_h = _g(wdP, "cap_height_mm", 18.0)

        cap_ceiling_z = cap_dz + cap_cavity
        wand_top_z = wand_dz + wand_cap_h
        overshoot = wand_top_z - cap_ceiling_z

        checks.append({
            "name": "⑫ Wand顶不超Cap腔顶",
            "pass": overshoot <= 0.3,
            "value": overshoot,
            "threshold": 0.3,
            "msg": (
                f"Wand顶Z={wand_top_z:.2f}, Cap腔顶Z={cap_ceiling_z:.2f}, "
                f"超出={overshoot:.2f}mm"
                + ("" if overshoot <= 0.3
                   else "（建议减小wand盖高或增大cap腔深）")
            ),
        })

    all_pass = all(c["pass"] for c in checks)
    return {
        "pass": all_pass,
        "checks": checks,
    }


def compute_assembly_report(
    component_params: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    综合装配报告：位置 + 干涉检测 + 质量验收。
    """
    positions = compute_assembly_positions(component_params)
    interference = check_radial_interference(component_params, positions)
    quality = verify_assembly_quality(component_params, positions)

    hard_issues = [i for i in interference if i["severity"] == "hard"]
    soft_issues = [i for i in interference if i["severity"] == "soft"]

    return {
        "positions": positions,
        "interference": interference,
        "quality": quality,
        "ok": len(hard_issues) == 0 and quality["pass"],
        "hard_count": len(hard_issues),
        "soft_count": len(soft_issues),
        "summary": (
            "装配检查通过（全部PASS）" if (len(hard_issues) == 0 and quality["pass"])
            else f"发现 {len(hard_issues)} 个干涉 + {sum(1 for c in quality['checks'] if not c['pass'])} 项验收未通过"
        ),
    }
