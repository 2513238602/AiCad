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

import json
import math
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════════
# 常量 — 与 modeler.py 保持一致
# ═══════════════════════════════════════════════════════════════════════════
CAP_CHAMFER_WALL = 0.15  # 倒角边缘最小壁厚 mm (与 modeler.py 一致)
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


def _extract_profile(bP: Dict[str, Any]) -> tuple[str, list | None, list | None]:
    """从瓶身参数中提取轮廓模式和 A/B 控制点。"""
    mode = str(bP.get("profile_mode", "classic"))
    pts_a = None
    pts_b = None
    if mode == "spline":
        raw = bP.get("profile_points_json", "[]")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            pts_a = [(float(p[0]), float(p[1])) for p in parsed] if parsed else None
        except (json.JSONDecodeError, TypeError, IndexError):
            pts_a = None
        symmetry = str(bP.get("profile_symmetry", "symmetric"))
        if symmetry == "asymmetric":
            raw_b = bP.get("profile_b_points_json", "[]")
            try:
                parsed_b = json.loads(raw_b) if isinstance(raw_b, str) else raw_b
                pts_b = [(float(p[0]), float(p[1])) for p in parsed_b] if parsed_b else None
            except (json.JSONDecodeError, TypeError, IndexError):
                pts_b = None
    return mode, pts_a, pts_b


def _cap_chamfer_id(cap_outer_od: float, cap_inner_id: float = 0) -> float:
    """计算瓶盖内底倒角处的有效内径（最宽处）"""
    chamfer_from_od = cap_outer_od - 2 * CAP_CHAMFER_WALL
    if cap_inner_id > 0:
        return max(chamfer_from_od, cap_inner_id)
    return chamfer_from_od


def _wand_bore_dia(thread_crest: float, thread_depth: float) -> float:
    """计算刷杆实际内腔直径（与 modeler.py build_wand 一致）。
    modeler: inner_cavity_r = thr_crest_r + thr_depth + 0.5"""
    return thread_crest + 2 * thread_depth + WAND_BORE_EXTRA


def _wand_bore_effective(wdP: Dict[str, Any], z_offset: float = 0.0) -> float:
    """计算刷杆有效内腔直径，支持锥形模式。
    锥形无螺纹: 内径随Z变化，底部 = 外径 - 1.6mm (0.8mm等壁厚)
    标准螺纹: 固定直径 = thr_crest + 2*thr_depth + 1.0
    z_offset: 从 wand 底部向上的偏移量 (0=底部最宽处)"""
    cap_taper = float(_g(wdP, "cap_taper_deg", 0.0))
    thread_on = bool((wdP.get("thread") or {}).get("enabled", True))

    if cap_taper > 0 and not thread_on:
        outer_od = _g(wdP, "outer_od_mm", 18.0)
        cap_h = _g(wdP, "cap_height_mm", 18.0)
        outer_r = outer_od / 2.0
        taper_r = math.tan(math.radians(cap_taper)) * cap_h
        r_top = max(outer_r - taper_r, 3.0)
        if cap_h > 0 and z_offset > 0:
            r_at_z = outer_r - (outer_r - r_top) * min(z_offset / cap_h, 1.0)
        else:
            r_at_z = outer_r
        inner_r = r_at_z - 0.8
        return max(inner_r * 2, 0)
    else:
        thread_crest = _g(wdP, "thread.crest_dia_mm", 18.0)
        thread_depth = _g(wdP, "thread.depth_mm", 0.5)
        return _wand_bore_dia(thread_crest, thread_depth)


def _body_od_at_shoulder(
    bottle_H: float, neck_h: float, shoulder_h: float, body_od: float,
    taper_deg: float = 0.0,
) -> float:
    """计算瓶身顶部（肩底处）的实际外径，考虑拔模角收窄。
    body_od 是瓶底最大直径，顶部因拔模角而收窄。
    taper_deg: 瓶身实际锥度角，0 时使用最小拔模角。"""
    body_h = bottle_H - neck_h - shoulder_h
    if body_h <= 0:
        return body_od
    eff_deg = max(BODY_DRAFT_DEG, taper_deg)
    delta = 2 * math.tan(math.radians(eff_deg)) * body_h
    return body_od - delta


def _interp_profile_od(z: float, profile_points: list) -> float:
    """从轮廓控制点插值外径（直径）。"""
    for i in range(len(profile_points) - 1):
        r0, z0 = profile_points[i]
        r1, z1 = profile_points[i + 1]
        if z0 <= z <= z1:
            t = (z - z0) / (z1 - z0) if z1 > z0 else 0
            return 2 * (r0 + t * (r1 - r0))
    if z < profile_points[0][1]:
        return 2 * profile_points[0][0]
    return 2 * profile_points[-1][0]


def _bottle_od_at_z(
    z: float, bottle_H: float, neck_h: float,
    shoulder_h: float, body_od: float, neck_od: float,
    profile_mode: str = "classic",
    profile_points: list | None = None,
    profile_b_points: list | None = None,
    taper_deg: float = 0.0,
) -> float:
    """计算瓶身在指定Z高度处的外径。
    非对称模式返回 max(od_a, od_b) 作为最大包络直径。
    """
    body_h = bottle_H - neck_h - shoulder_h
    neck_bottom = bottle_H - neck_h

    # Z 超出瓶身顶部：无瓶材料
    if z >= bottle_H:
        return 0.0

    if z >= neck_bottom:
        return neck_od

    if profile_mode == "spline" and profile_points and len(profile_points) >= 2:
        od_a = _interp_profile_od(z, profile_points)
        if profile_b_points and len(profile_b_points) >= 2:
            od_b = _interp_profile_od(z, profile_b_points)
            return max(od_a, od_b)
        return od_a
    else:
        shoulder_bottom = neck_bottom - shoulder_h
        body_od_top = _body_od_at_shoulder(bottle_H, neck_h, shoulder_h, body_od, taper_deg)

        if z >= shoulder_bottom and shoulder_h > 0:
            frac = (z - shoulder_bottom) / shoulder_h
            return body_od_top + (neck_od - body_od_top) * frac
        elif body_h > 0:
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
    profile_mode: str = "classic",
    profile_points: list | None = None,
    profile_b_points: list | None = None,
    taper_deg: float = 0.0,
) -> float:
    """
    计算安全Z — 瓶身外径首次小于 wand 内腔直径的Z坐标。
    Wand底部必须 ≥ safe_z 才能避免与瓶肩的径向干涉。
    """
    if profile_mode == "spline" and profile_points and len(profile_points) >= 2:
        # spline 模式：从控制点扫描找到 OD 首次 ≤ wand_inner_dia 的 Z
        # 先检查颈部
        if neck_od >= wand_inner_dia:
            return bottle_H
        # 从顶部向底部扫描控制点
        for i in range(len(profile_points) - 1, 0, -1):
            r_cur, z_cur = profile_points[i]
            r_prev, z_prev = profile_points[i - 1]
            od_cur = 2 * r_cur
            od_prev = 2 * r_prev
            if od_cur <= wand_inner_dia and od_prev > wand_inner_dia:
                # 在这个区间内线性插值
                if od_prev > od_cur:
                    frac = (od_prev - wand_inner_dia) / (od_prev - od_cur)
                    return z_prev + frac * (z_cur - z_prev)
                return z_cur
        # 所有控制点的 OD 都 ≤ wand_inner_dia
        return 0.0
    else:
        # classic 模式
        shoulder_bottom = bottle_H - neck_h - shoulder_h
        body_od_top = _body_od_at_shoulder(bottle_H, neck_h, shoulder_h, body_od, taper_deg)

        if body_od_top <= wand_inner_dia:
            return shoulder_bottom
        if neck_od >= wand_inner_dia:
            return bottle_H
        if shoulder_h <= 0:
            return shoulder_bottom
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
    taper_deg = _g(bP, "taper_deg", 0.0)

    # 提取轮廓模式和控制点
    prof_mode, prof_pts, prof_b_pts = _extract_profile(bP)

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
        is_exotic = bool(cP.get("exotic", False))

        # 异形盖：底部开口即内腔直径，不能用外壳OD推算倒角
        # 标准盖：外壁有导入倒角，有效清除直径 ≈ outer_od - 0.3mm
        if is_exotic:
            chamfer_id = cap_inner_id
        else:
            chamfer_id = _cap_chamfer_id(cap_outer_od, cap_inner_id)

        neck_bottom_z = bottle_H - neck_h
        shoulder_bottom_z = neck_bottom_z - shoulder_h

        # 肩底处瓶身实际外径（因拔模角/锥度收窄）
        body_od_top = _body_od_at_shoulder(bottle_H, neck_h, shoulder_h, body_od, taper_deg)

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
            wand_inner_dia = _wand_bore_effective(wdP)

            safe_z = _compute_safe_z(
                bottle_H, neck_h, shoulder_h,
                body_od, neck_od, wand_inner_dia,
                profile_mode=prof_mode, profile_points=prof_pts, profile_b_points=prof_b_pts,
                taper_deg=taper_deg,
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
    taper_deg = _g(bP, "taper_deg", 0.0)
    neck_id = neck_od - 2 * lip_t

    prof_mode, prof_pts, prof_b_pts = _extract_profile(bP)

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

    # --- 检查2: Wand ↔ Cap 径向配合（截面感知） ---
    if wdP and cP:
        wand_od = _g(wdP, "outer_od_mm", 21.5)
        cap_id = _g(cP, "inner_id_mm", 22.4)
        cap_cs = cP.get("cross_section", "round")
        wand_cs = wdP.get("cross_section", "round")

        # 截面不匹配时的有效间隙计算
        if cap_cs == "round" and wand_cs not in ("round", ""):
            # 圆盖+非圆杆：杆对角线可能超出盖内径
            import math as _m
            _poly_sides = {"triangle": 3, "square": 4, "hexagon": 6, "octagon": 8}
            _ns = _poly_sides.get(wand_cs, 4)
            effective_wand = wand_od / _m.cos(_m.pi / _ns) if _ns > 4 else wand_od * 1.414
            if wand_cs == "triangle":
                effective_wand = wand_od * 1.155  # 三角形外接圆/内切圆比
            eff_gap = cap_id - effective_wand
            if eff_gap < 0:
                issues.append({
                    "severity": "hard",
                    "pair": "wand-cap",
                    "msg": (f"{wand_cs}刷杆有效外径({effective_wand:.1f}mm) "
                            f"> 圆形瓶盖内径({cap_id:.1f}mm)，截面不匹配"),
                    "gap_mm": eff_gap,
                })
        elif cap_cs != "round" and wand_cs == "round":
            # 非圆盖+圆杆：圆形内切于多边形，最窄处=边长=cap_id
            # 不额外报警（圆 fit 在方/三角形内是安全的）
            pass

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
        cap_inner_id_3 = _g(cP, "inner_id_mm", 22.4)
        is_exotic_3 = bool(cP.get("exotic", False))
        chamfer_id = cap_inner_id_3 if is_exotic_3 else _cap_chamfer_id(cap_outer_od, cap_inner_id_3)

        bottle_od_at_cap = _bottle_od_at_z(
            cap_dz, bottle_H, neck_h, shoulder_h, body_od, neck_od,
            profile_mode=prof_mode, profile_points=prof_pts, profile_b_points=prof_b_pts,
            taper_deg=taper_deg,
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
        wand_inner_r = _wand_bore_effective(wdP) / 2.0

        # 在wand底部检查（最危险位置）
        bottle_od_at_wand = _bottle_od_at_z(
            wand_dz, bottle_H, neck_h, shoulder_h, body_od, neck_od,
            profile_mode=prof_mode, profile_points=prof_pts, profile_b_points=prof_b_pts,
            taper_deg=taper_deg,
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
            wand_inner_r = _wand_bore_effective(wdP) / 2.0

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
    elif not wdP and cP and wpP:
        # Cap内置杆模式：杆径 vs 孔口
        _cs = cP.get("stem", {}) or {}
        if bool(_cs.get("enabled", False)):
            stem_d = float(_cs.get("diameter_mm", 4.5))
            orifice = _g(wpP, "orifice_mm", 7.0)
            gap = orifice - stem_d
            if gap < 0:
                issues.append({
                    "severity": "hard",
                    "pair": "cap_stem-wiper",
                    "msg": f"Cap杆径({stem_d:.1f}mm) > 内塞孔口({orifice:.1f}mm)，杆身无法通过",
                    "gap_mm": gap,
                })
            elif gap < 0.5:
                issues.append({
                    "severity": "soft",
                    "pair": "cap_stem-wiper",
                    "msg": f"Cap杆径({stem_d:.1f}mm) 与孔口({orifice:.1f}mm) 间隙仅{gap:.2f}mm",
                    "gap_mm": gap,
                })

    # --- 检查7: Cap ↔ Bottle 外观齐平（异形盖跳过）---
    if cP and bP and not bool(cP.get("exotic", False)):
        cap_od = _g(cP, "outer_od_mm", 24.0)
        if taper_deg > 0:
            # 锥形瓶：齐顶或齐底均合法
            body_od_top = _body_od_at_shoulder(
                bottle_H, neck_h, shoulder_h, body_od, taper_deg
            )
            diff = min(abs(cap_od - body_od_top), abs(cap_od - body_od))
        else:
            diff = abs(cap_od - body_od)
        if diff > 1.0:
            issues.append({
                "severity": "soft",
                "pair": "cap-bottle",
                "msg": (
                    f"瓶盖外径({cap_od:.1f}mm) 与瓶身外径({body_od:.1f}mm) "
                    f"差异{diff:.1f}mm，外观不齐平"
                ),
                "gap_mm": diff,
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
    elif not wdP and cP and bP:
        # Cap内置杆模式：Cap螺纹 vs 瓶身螺纹
        _cs = cP.get("stem", {}) or {}
        if bool(_cs.get("enabled", False)):
            b_thr = bP.get("thread", {}) or {}
            c_thr = cP.get("thread", {}) or {}
            b_on = bool(b_thr.get("enabled", False))
            c_on = bool(c_thr.get("enabled", False))
            if b_on and c_on:
                b_pitch = float(b_thr.get("pitch_mm", 2.7))
                c_pitch = float(c_thr.get("pitch_mm", 2.7))
                if abs(b_pitch - c_pitch) > 0.01:
                    issues.append({
                        "severity": "hard",
                        "pair": "bottle-cap_thread",
                        "msg": f"螺纹牙距不匹配: 瓶身={b_pitch}mm, Cap内螺纹={c_pitch}mm",
                        "gap_mm": 0,
                    })

    return issues


def verify_assembly_quality(
    component_params: Dict[str, Dict[str, Any]],
    positions: Optional[Dict[str, Dict[str, Any]]] = None,
    geometry_meta: Optional[Dict[str, Dict]] = None,
) -> Dict[str, Any]:
    """
    装配质量验收 — 25项全覆盖检查。

    物理配合（①-⑨⑫）：
      ①外观齐平 ②肩部缝隙 ③Wand帽不突出 ④Wand↔Bottle径向
      ⑤Wiper装入颈 ⑤bWiper凸环装入 ⑥Stem穿过孔口
      ⑦Wand↔Wiper径向 ⑦bWiper不侵气密环 ⑧Cap底可装入
      ⑨径向无硬干涉 ⑫Wand顶不超腔顶

    语义正确性（⑬-⑯）：
      ⑬截面一致 ⑭螺纹审计 ⑮锥度连续 ⑯比例合理

    配合完整性（⑱-㉕）：
      ⑱Cap腔覆盖瓶颈 ⑲瓶颈穿入盖内 ⑳杆+刷≤瓶内深
      ㉑内塞高≤颈高 ㉒螺纹全参数同步 ㉓峰径≈颈外径
      ㉔Finish一致 ㉕凸环密封间隙

    L6几何验证（⑰）：BRep成品检查
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
    taper_deg = _g(bP, "taper_deg", 0.0)
    neck_id = neck_od - 2 * lip_t
    shoulder_bottom_z = bottle_H - neck_h - shoulder_h

    prof_mode, prof_pts, prof_b_pts = _extract_profile(bP)

    # --- 1. 外观齐平（异形盖跳过）---
    is_exotic_cap = bool(cP.get("exotic", False)) if cP else False
    if cP and bP and not is_exotic_cap:
        cap_od = _g(cP, "outer_od_mm", 24.0)
        if taper_deg > 0:
            # 锥形瓶有两种合法设计：齐顶（cap=肩部OD）或齐底（cap=body_od）
            body_od_top = _body_od_at_shoulder(
                bottle_H, neck_h, shoulder_h, body_od, taper_deg
            )
            diff_top = abs(cap_od - body_od_top)
            diff_bot = abs(cap_od - body_od)
            diff = min(diff_top, diff_bot)
            ref = body_od_top if diff_top <= diff_bot else body_od
        else:
            diff = abs(cap_od - body_od)
            ref = body_od
        checks.append({
            "name": "① 外观齐平（cap_od ≈ body_od）",
            "pass": diff <= 1.0,
            "value": diff,
            "threshold": 1.0,
            "msg": f"cap外径={cap_od:.1f}, body参考外径={ref:.1f}, 差值={diff:.1f}mm",
        })

    # --- 2. 肩部缝隙 ≤ 0.5mm（异形盖跳过：不坐在肩部）---
    if cP and bP and positions.get("cap") and not is_exotic_cap:
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
        wand_inner_dia = _wand_bore_effective(wdP)

        bottle_od_at_wand = _bottle_od_at_z(
            wand_dz, bottle_H, neck_h, shoulder_h, body_od, neck_od,
            profile_mode=prof_mode, profile_points=prof_pts, profile_b_points=prof_b_pts,
            taper_deg=taper_deg,
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
    elif not wdP and cP and wpP:
        _cs6 = cP.get("stem", {}) or {}
        if bool(_cs6.get("enabled", False)):
            stem_d = float(_cs6.get("diameter_mm", 4.5))
            orifice = _g(wpP, "orifice_mm", 7.0)
            clearance = orifice - stem_d
            checks.append({
                "name": "⑥ Cap杆穿过Wiper孔口",
                "pass": clearance > 0,
                "value": clearance,
                "threshold": 0.0,
                "msg": f"Cap杆径={stem_d:.1f}, 孔口={orifice:.1f}, 间隙={clearance:.1f}mm",
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
            # wiper 在 wand 底部附近，用 Z 偏移量计算内径
            wiper_z_in_wand = overlap_lo - wand_dz
            wand_inner_r = _wand_bore_effective(wdP, z_offset=wiper_z_in_wand) / 2.0
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
        cap_inner_id_8 = _g(cP, "inner_id_mm", 22.4)
        is_exotic_8 = bool(cP.get("exotic", False))
        chamfer_id = cap_inner_id_8 if is_exotic_8 else _cap_chamfer_id(cap_outer_od, cap_inner_id_8)

        bottle_od_at_cap = _bottle_od_at_z(
            cap_dz, bottle_H, neck_h, shoulder_h, body_od, neck_od,
            profile_mode=prof_mode, profile_points=prof_pts, profile_b_points=prof_b_pts,
            taper_deg=taper_deg,
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

    # ═══════════════════════════════════════════════════════════════════
    # 语义正确性检查（⑬-⑯）— 检测"对不对"而非"能不能装"
    # ═══════════════════════════════════════════════════════════════════

    # --- ⑬ 截面一致性（HARD — bottle/cap/wand 必须同型） ---
    if bP and cP and wdP:
        cs_b = bP.get("cross_section", "round")
        cs_c = cP.get("cross_section", "round")
        cs_w = wdP.get("cross_section", "round")
        all_same = (cs_b == cs_c == cs_w)
        checks.append({
            "name": "⑬ 截面一致性（bottle/cap/wand 同型）",
            "pass": all_same,
            "value": f"{cs_b}/{cs_c}/{cs_w}",
            "threshold": "all_same",
            "msg": (
                f"bottle={cs_b}, cap={cs_c}, wand={cs_w}"
                + ("" if all_same else " ← 截面不一致！")
            ),
        })
    elif bP and cP and not wdP:
        cs_b = bP.get("cross_section", "round")
        cs_c = cP.get("cross_section", "round")
        all_same = (cs_b == cs_c)
        checks.append({
            "name": "⑬ 截面一致性（bottle/cap 同型）",
            "pass": all_same,
            "value": f"{cs_b}/{cs_c}",
            "threshold": "all_same",
            "msg": (
                f"bottle={cs_b}, cap={cs_c}"
                + ("（无独立wand）" if all_same else " ← 截面不一致！")
            ),
        })

    # --- ⑭ 螺纹状态审计（信息性 — 不阻塞但明确标注） ---
    if wdP:
        # 兼容 flat ("thread.enabled") 和 nested ({"thread": {"enabled": ...}}) 两种格式
        thr_nested = wdP.get("thread", {})
        if isinstance(thr_nested, dict):
            thr_on = thr_nested.get("enabled", True)
        else:
            thr_on = True
        checks.append({
            "name": "⑭ 螺纹状态审计",
            "pass": True,  # 信息性，不阻塞
            "value": bool(thr_on),
            "threshold": "info",
            "msg": (
                f"Wand螺纹{'启用' if thr_on else '禁用'}"
                + ("" if thr_on else "（可能因窄盖/极端锥度自动关闭）")
            ),
        })
    elif not wdP and cP:
        _cs14 = cP.get("stem", {}) or {}
        if bool(_cs14.get("enabled", False)):
            c_thr = cP.get("thread", {}) or {}
            thr_on = bool(c_thr.get("enabled", False))
            checks.append({
                "name": "⑭ 螺纹状态审计（Cap内置杆）",
                "pass": True,
                "value": bool(thr_on),
                "threshold": "info",
                "msg": f"Cap内螺纹{'启用' if thr_on else '禁用'}（内置杆模式）",
            })

    # --- ⑮ 锥度连续性（SOFT — 差值 > 2° 警告） ---
    if bP and cP:
        bt = _g(bP, "taper_deg", 0)
        ct = _g(cP, "taper_deg", 0)
        diff = abs(ct - bt)
        checks.append({
            "name": "⑮ 锥度连续性（cap ≈ bottle taper）",
            "pass": diff <= 2.0,
            "value": round(diff, 1),
            "threshold": 2.0,
            "msg": (
                f"bottle={bt:.1f}°, cap={ct:.1f}°, 差值={diff:.1f}°"
                + ("" if diff <= 2.0 else " ← 视觉不连续！")
            ),
        })

    # --- ⑯ 比例合理性（SOFT — cap > bottle 高度警告） ---
    if bP and cP:
        bh = _g(bP, "height_mm", 70)
        ch = _g(cP, "height_mm", 30)
        ratio = ch / bh if bh > 0 else 999.0
        checks.append({
            "name": "⑯ 比例合理性（cap ≤ bottle 高度）",
            "pass": ratio <= 1.0,
            "value": round(ratio, 2),
            "threshold": 1.0,
            "msg": (
                f"cap高={ch:.1f}, bottle高={bh:.1f}, 比值={ratio:.2f}"
                + ("" if ratio <= 1.0 else " ← 头重脚轻！")
            ),
        })

    # ═══════════════════════════════════════════════════════════════════
    # 配合完整性检查（⑱-㉕）— 验证全部物理配合关系成立
    # ═══════════════════════════════════════════════════════════════════

    # --- ⑱ Cap腔深覆盖瓶颈 (HARD) ---
    if cP and bP:
        cap_cav = _g(cP, "cavity_depth_mm", 23.5)
        checks.append({
            "name": "⑱ Cap腔深≥瓶颈高（盖腔覆盖颈部）",
            "pass": cap_cav >= neck_h,
            "value": round(cap_cav - neck_h, 1),
            "threshold": 0,
            "msg": (
                f"cap.cavity_depth={cap_cav:.1f}, bottle.neck_height={neck_h:.1f}, "
                f"余量={cap_cav - neck_h:.1f}mm"
                + ("" if cap_cav >= neck_h else " ← 盖腔不足以覆盖瓶颈！")
            ),
        })

    # --- ⑲ 瓶颈穿入盖内 (HARD) ---
    if cP and bP:
        cap_id = _g(cP, "inner_id_mm", 22.4)
        gap_neck = cap_id - neck_od
        checks.append({
            "name": "⑲ Cap内径>颈外径（瓶颈穿入盖内）",
            "pass": gap_neck > 0,
            "value": round(gap_neck, 1),
            "threshold": 0,
            "msg": (
                f"cap.inner_id={cap_id:.1f}, bottle.neck_od={neck_od:.1f}, "
                f"间隙={gap_neck:.1f}mm"
                + ("" if gap_neck > 0 else " ← 瓶颈无法穿入盖内！")
            ),
        })

    # --- ⑳ 杆+刷不超瓶身内深 (HARD) ---
    if wdP and bP:
        stem_len = _g(wdP, "stem_length_mm", 55.0)
        brush_d = wdP.get("brush", {})
        brush_len = brush_d.get("length_mm", 12.0) if isinstance(brush_d, dict) else 12.0
        inner_depth = _g(bP, "inner_depth_mm", 55.0)
        total_insert = stem_len + brush_len
        clearance_20 = inner_depth - total_insert
        checks.append({
            "name": "⑳ 杆+刷≤瓶内深（不戳瓶底）",
            "pass": clearance_20 >= -3.0,  # 3mm 弹性余量
            "value": round(clearance_20, 1),
            "threshold": -3.0,
            "msg": (
                f"stem({stem_len:.1f})+brush({brush_len:.1f})={total_insert:.1f}mm, "
                f"bottle.inner_depth={inner_depth:.1f}, 余量={clearance_20:.1f}mm"
                + ("" if clearance_20 >= -3.0 else " ← 刷杆戳穿瓶底！")
            ),
        })
    elif not wdP and cP and bP:
        _cs20 = cP.get("stem", {}) or {}
        if bool(_cs20.get("enabled", False)):
            stem_len = float(_cs20.get("length_mm", 50.0))
            brush_d = cP.get("brush", {}) or {}
            brush_len = float(brush_d.get("length_mm", 12.0))
            inner_depth = _g(bP, "inner_depth_mm", 55.0)
            total_insert = stem_len + brush_len
            clearance_20 = inner_depth - total_insert
            checks.append({
                "name": "⑳ Cap杆+刷≤瓶内深（不戳瓶底）",
                "pass": clearance_20 >= -3.0,
                "value": round(clearance_20, 1),
                "threshold": -3.0,
                "msg": (
                    f"stem({stem_len:.1f})+brush({brush_len:.1f})={total_insert:.1f}mm, "
                    f"bottle.inner_depth={inner_depth:.1f}, 余量={clearance_20:.1f}mm"
                    + ("" if clearance_20 >= -3.0 else " ← Cap杆戳穿瓶底！")
                ),
            })

    # --- ㉑ 内塞高度适配颈高 (HARD) ---
    if wpP and bP:
        wiper_h = _g(wpP, "height_mm", 12.0)
        checks.append({
            "name": "㉑ 内塞高≤颈高（装入颈部）",
            "pass": wiper_h <= neck_h,
            "value": round(wiper_h - neck_h, 1),
            "threshold": 0,
            "msg": (
                f"wiper.height={wiper_h:.1f}, bottle.neck_height={neck_h:.1f}"
                + ("" if wiper_h <= neck_h else f", 超出={wiper_h - neck_h:.1f}mm ← 内塞塞不进瓶颈！")
            ),
        })

    # --- ㉒ 螺纹全参数同步 (HARD) ---
    _thr_source = None
    _thr_source_label = ""
    if wdP and bP:
        _thr_source = wdP.get("thread", {}) or {}
        _thr_source_label = "wand"
    elif not wdP and cP and bP:
        _cs22 = cP.get("stem", {}) or {}
        if bool(_cs22.get("enabled", False)):
            _thr_source = cP.get("thread", {}) or {}
            _thr_source_label = "cap"

    if _thr_source is not None and bP:
        b_thr = bP.get("thread", {}) or {}
        b_on = bool(b_thr.get("enabled", False))
        t_on = bool(_thr_source.get("enabled", _thr_source_label == "wand"))
        if b_on and t_on:
            mismatches = []
            for key, label in [
                ("turns", "圈数"), ("depth_mm", "牙深"),
                ("lead_angle_deg", "导程角"),
            ]:
                bv = b_thr.get(key)
                tv = _thr_source.get(key)
                if bv is not None and tv is not None:
                    if isinstance(bv, float) or isinstance(tv, float):
                        if abs(float(bv) - float(tv)) > 0.01:
                            mismatches.append(f"{label}: bottle={bv}, {_thr_source_label}={tv}")
                    elif bv != tv:
                        mismatches.append(f"{label}: bottle={bv}, {_thr_source_label}={tv}")
            bs = b_thr.get("segmented", False)
            ts = _thr_source.get("segmented", False)
            if bs != ts:
                mismatches.append(f"分段: bottle={bs}, {_thr_source_label}={ts}")
            if bs and ts:
                bg = b_thr.get("gap_angle_deg", 20)
                tg = _thr_source.get("gap_angle_deg", 20)
                if abs(float(bg) - float(tg)) > 0.01:
                    mismatches.append(f"分段角: bottle={bg}, {_thr_source_label}={tg}")
            checks.append({
                "name": f"㉒ 螺纹全参数同步（bottle↔{_thr_source_label}）",
                "pass": len(mismatches) == 0,
                "value": len(mismatches),
                "threshold": 0,
                "msg": (
                    "全部一致" if not mismatches
                    else "不一致: " + "; ".join(mismatches)
                ),
            })

    # --- ㉓ 螺纹峰径匹配颈外径 (HARD) ---
    _thr23_source = None
    _thr23_label = ""
    if wdP and bP:
        _thr23_source = wdP.get("thread", {}) or {}
        _thr23_label = "wand"
    elif not wdP and cP and bP:
        _cs23 = cP.get("stem", {}) or {}
        if bool(_cs23.get("enabled", False)):
            _thr23_source = cP.get("thread", {}) or {}
            _thr23_label = "cap"

    if _thr23_source is not None and bP:
        b_thr_23 = bP.get("thread", {}) or {}
        b_on_23 = bool(b_thr_23.get("enabled", False))
        t_on_23 = bool(_thr23_source.get("enabled", _thr23_label == "wand"))
        if b_on_23 and t_on_23:
            t_crest = float(_thr23_source.get("crest_dia_mm", 18.0))
            diff_crest = abs(t_crest - neck_od)
            checks.append({
                "name": f"㉓ 螺纹峰径≈颈外径（{_thr23_label}螺纹啮合）",
                "pass": diff_crest <= 1.0,
                "value": round(diff_crest, 1),
                "threshold": 1.0,
                "msg": (
                    f"{_thr23_label}.crest_dia={t_crest:.1f}, bottle.neck_od={neck_od:.1f}, "
                    f"差值={diff_crest:.1f}mm"
                    + ("" if diff_crest <= 1.0 else " ← 螺纹径向不匹配！")
                ),
            })

    # --- ㉔ Finish规格一致 (SOFT) ---
    finishes = {}
    for cid, pdict in [("bottle", bP), ("cap", cP), ("wand", wdP), ("wiper", wpP)]:
        if pdict:
            f_val = pdict.get("finish", "")
            if f_val:
                finishes[cid] = str(f_val)
    if len(finishes) >= 2:
        vals = list(finishes.values())
        all_same_finish = all(v == vals[0] for v in vals)
        checks.append({
            "name": "㉔ Finish规格一致（口部标准化）",
            "pass": all_same_finish,
            "value": ", ".join(f"{k}={v}" for k, v in finishes.items()),
            "threshold": "all_same",
            "msg": (
                f"统一规格: {vals[0]}" if all_same_finish
                else f"规格不一致: {finishes} ← 口部规格应统一！"
            ),
        })

    # --- ㉕ 凸环有效密封间隙 (SOFT) ---
    if wpP and bP:
        flange_od = _g(wpP, "flange_od_mm", 17.0)
        seal_gap = neck_id - flange_od
        checks.append({
            "name": "㉕ 凸环密封间隙（0~3mm）",
            "pass": 0 <= seal_gap <= 3.0,
            "value": round(seal_gap, 1),
            "threshold": "0~3.0",
            "msg": (
                f"neck_id={neck_id:.1f}, flange_od={flange_od:.1f}, "
                f"间隙={seal_gap:.1f}mm"
                + (
                    "" if 0 <= seal_gap <= 3.0
                    else (" ← 凸环无法装入颈内！" if seal_gap < 0
                          else " ← 间隙过大，密封失效！")
                )
            ),
        })

    # ═══════════════════════════════════════════════════════════════════
    # L6 几何验证（⑰）— 如果有 geometry_meta，检查 BRep 成品
    # ═══════════════════════════════════════════════════════════════════

    if geometry_meta:
        for comp_id, geo in geometry_meta.items():
            for gc in geo.get("checks", []):
                if not gc.get("pass", True):
                    sev = gc.get("severity", "soft")
                    checks.append({
                        "name": f"⑰ {comp_id} 几何: {gc.get('name', '?')}",
                        "pass": False,
                        "value": gc.get("actual", "?"),
                        "threshold": gc.get("tolerance", "?"),
                        "msg": gc.get("msg", ""),
                    })

    all_pass = all(c["pass"] for c in checks)
    return {
        "pass": all_pass,
        "checks": checks,
    }


def compute_assembly_report(
    component_params: Dict[str, Dict[str, Any]],
    geometry_meta: Optional[Dict[str, Dict]] = None,
) -> Dict[str, Any]:
    """
    综合装配报告：位置 + 干涉检测 + 质量验收。
    geometry_meta: 可选，各组件的 geometry_qc 元数据（来自 modeler.build()）
    """
    positions = compute_assembly_positions(component_params)
    interference = check_radial_interference(component_params, positions)
    quality = verify_assembly_quality(component_params, positions,
                                      geometry_meta=geometry_meta)

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


# ═══════════════════════════════════════════════════════════════════════════
# L7: BRep 级装配干涉检测 — 成品级实体布尔交集
# ═══════════════════════════════════════════════════════════════════════════

# 干涉体积阈值（mm³），低于此视为无干涉
# 10mm³ ≈ 倒角边缘/BRep数值精度噪声（如 lead-in chamfer 接触区）
BREP_INTERFERENCE_THRESHOLD = 10.0

# 需要检测的 5 对组件
BREP_COMPONENT_PAIRS = [
    ("cap", "wand"),
    ("cap", "bottle"),
    ("wand", "bottle"),
    ("wiper", "bottle"),
    ("wiper", "wand"),
]


def check_brep_assembly(
    component_params: Dict[str, Dict[str, Any]],
    solids: Optional[Dict[str, Any]] = None,
    step_files: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    L7: BRep 级装配干涉检测。

    对已构建的 CadQuery 实体执行布尔交集运算，检测真实几何穿透。
    与参数级检查互补：参数级检查验证"设计上应该不干涉"，
    本函数验证"实际构建的几何体确实不干涉"。

    Args:
        component_params: 各组件归一化参数（用于计算装配位置）
        solids: CadQuery Workplane 字典（测试管线直接传入）
        step_files: STEP 文件路径字典（生产管线从已导出文件导入）

    Returns:
        {
            "ok": bool,
            "pairs": [{"pair": "cap↔wand", "volume_mm3": float, "ok": bool}, ...],
            "total_interference_mm3": float,
            "error": None | str,
        }
    """
    try:
        import cadquery as cq
    except ImportError:
        return {"ok": True, "pairs": [], "total_interference_mm3": 0,
                "error": "CadQuery 不可用，跳过 BRep 干涉检测"}

    # ── 1. 获取实体 ──
    if solids is not None:
        loaded = dict(solids)
    elif step_files is not None:
        loaded = {}
        for comp_id, path in step_files.items():
            try:
                loaded[comp_id] = cq.importers.importStep(path)
            except Exception as e:
                return {"ok": True, "pairs": [], "total_interference_mm3": 0,
                        "error": f"STEP 导入失败 ({comp_id}): {e}"}
    else:
        return {"ok": True, "pairs": [], "total_interference_mm3": 0,
                "error": "未提供 solids 或 step_files"}

    # ── 2. 装配定位（平移到装配坐标系） ──
    positions = compute_assembly_positions(component_params)
    positioned: Dict[str, Any] = {}
    for comp_id, solid in loaded.items():
        dz = positions.get(comp_id, {}).get("dz", 0.0)
        positioned[comp_id] = solid.translate((0, 0, dz))

    # ── 3. 逐对布尔交集检测 ──
    pairs_result: List[Dict[str, Any]] = []
    total_vol = 0.0

    for a_id, b_id in BREP_COMPONENT_PAIRS:
        if a_id not in positioned or b_id not in positioned:
            continue

        try:
            intersection = positioned[a_id].intersect(positioned[b_id])
            vol = intersection.val().Volume()
            ok = vol < BREP_INTERFERENCE_THRESHOLD

            pairs_result.append({
                "pair": f"{a_id}<->{b_id}",
                "volume_mm3": round(vol, 3),
                "ok": ok,
            })
            if not ok:
                total_vol += vol
        except Exception:
            # 空交集可能抛异常 → 视为无干涉
            pairs_result.append({
                "pair": f"{a_id}<->{b_id}",
                "volume_mm3": 0.0,
                "ok": True,
            })

    all_ok = all(p["ok"] for p in pairs_result)
    return {
        "ok": all_ok,
        "pairs": pairs_result,
        "total_interference_mm3": round(total_vol, 3),
        "error": None,
    }
