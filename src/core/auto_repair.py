# -*- coding: utf-8 -*-
"""
QC 自修复模块 — 分析 QC 失败并自动调整参数

核心函数:
- analyze_and_fix(): 单轮分析+修复，返回修复后参数和日志

设计原则:
1. 不修改用户指定的核心尺寸 (height_mm, body_od_mm, neck_od_mm)
2. HARD 级失败优先修复
3. 每轮产生参数调整，由调用方重建验证
4. 无状态，安全多轮迭代
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional, Tuple

# 不可修改的用户核心尺寸
_USER_LOCKED = {
    "bottle": frozenset({"height_mm", "body_od_mm", "neck_od_mm"}),
}

# BRep 干涉体积 → 参数调整量 (mm³ → mm)
_BREP_ADJ = [(10, 0.5), (100, 1.0), (500, 1.5), (2000, 2.5), (float("inf"), 3.0)]

# 最小有效调整量
_MIN_ADJ = 0.1


# ═══════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════

def _g(params: dict, comp: str, key: str, default: float = 0.0) -> float:
    """安全获取嵌套参数值"""
    parts = key.split(".")
    cur = params.get(comp, {})
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p, default)
        else:
            return default
    try:
        return float(cur)
    except (TypeError, ValueError):
        return default


def _s(params: dict, comp: str, key: str, value: Any,
       log: list, reason: str) -> bool:
    """设置参数并记录。返回 True 表示已修改。"""
    if key in _USER_LOCKED.get(comp, frozenset()):
        return False

    old = _g(params, comp, key)
    if isinstance(value, (int, float)) and isinstance(old, (int, float)):
        if abs(float(old) - float(value)) < _MIN_ADJ:
            return False

    parts = key.split(".")
    target = params.setdefault(comp, {})
    for p in parts[:-1]:
        if not isinstance(target.get(p), dict):
            target[p] = {}
        target = target[p]
    target[parts[-1]] = value

    log.append({
        "component": comp,
        "param": key,
        "old": round(old, 2) if isinstance(old, float) else old,
        "new": round(value, 2) if isinstance(value, float) else value,
        "reason": reason,
    })
    return True


def _brep_adj(vol: float) -> float:
    for thr, adj in _BREP_ADJ:
        if vol < thr:
            return adj
    return 2.0


def _tag(name: str) -> str:
    """提取检查名称中的标签号"""
    for ch in name:
        if ch in "①②③④⑤⑥⑦⑧⑨⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕":
            return ch
    return ""


# ═══════════════════════════════════════════════════════════════════
# 核心 API
# ═══════════════════════════════════════════════════════════════════

def analyze_and_fix(
    all_params: Dict[str, Dict[str, Any]],
    assembly_report: Dict[str, Any],
    brep_report: Optional[Dict[str, Any]] = None,
    protected_comps: Optional[set] = None,
) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]], set]:
    """
    单轮 QC 分析 + 参数修复。

    Args:
        all_params: 4 组件归一化参数
        assembly_report: compute_assembly_report() 结果
        brep_report: check_brep_assembly() 结果（可选）
        protected_comps: 跨轮次 BRep 保护的组件集合

    Returns:
        (fixed_params, repair_log, updated_protected_comps)
    """
    params = copy.deepcopy(all_params)
    log: List[Dict[str, Any]] = []

    # 继承跨轮次保护
    brep_fixed_comps: set = set(protected_comps) if protected_comps else set()

    # Phase 1: BRep 干涉修复（最高优先级 — 物理不可能）
    if brep_report and not brep_report.get("ok", True):
        for pr in brep_report.get("pairs", []):
            if not pr.get("ok", True):
                _dispatch_brep_fix(params, pr, log)
                pair = pr.get("pair", "")
                for comp in ("cap", "wand", "bottle", "wiper"):
                    if comp in pair:
                        brep_fixed_comps.add(comp)

    # 对存在边际干涉（>1mm³ 但低于阈值）的组件也施加保护
    # 防止外观修复（如⑮锥度）将边际干涉恶化为真干涉
    if brep_report:
        for pr in brep_report.get("pairs", []):
            vol = pr.get("volume_mm3", 0)
            if vol > 1.0:
                pair = pr.get("pair", "")
                for comp in ("cap", "wand", "bottle", "wiper"):
                    if comp in pair:
                        brep_fixed_comps.add(comp)

    # Phase 2: 参数级修复（跳过与 BRep 修复冲突的外观检查）
    checks = (assembly_report or {}).get("quality", {}).get("checks", [])
    for check in checks:
        if check.get("pass", True):
            continue
        tag = _tag(check.get("name", ""))
        if "cap" in brep_fixed_comps:
            if tag == "①":
                continue  # 齐平检查会缩 cap → 跳过
            if tag == "⑯":
                continue  # 比例检查会缩 cap → 跳过
            if tag == "⑮":
                # 锥度修复：只跳过「增加锥度」（收窄内腔），允许「移除锥度」
                bt = _g(params, "bottle", "taper_deg", 0)
                ct = _g(params, "cap", "taper_deg", 0)
                if bt >= ct:
                    continue  # 会增加或保持cap锥度 → 跳过
                # bt < ct 意味着会减小cap锥度 → 放行（有助BRep）
        _dispatch_param_fix(params, check, log)

    return params, log, brep_fixed_comps


# ═══════════════════════════════════════════════════════════════════
# 参数级修复分发
# ═══════════════════════════════════════════════════════════════════

def _dispatch_param_fix(params: dict, check: dict, log: list):
    name = check.get("name", "")
    tag = _tag(name)

    neck_od = _g(params, "bottle", "neck_od_mm", 18)
    neck_h = _g(params, "bottle", "neck_height_mm", 10)
    lip_t = _g(params, "bottle", "lip_thickness_mm", 1.0)
    neck_id = neck_od - 2 * lip_t

    if tag == "⑱":
        _fix_cap_cavity_depth(params, neck_h, log)
    elif tag == "⑲":
        _fix_cap_inner_id(params, neck_od, log)
    elif tag == "⑳":
        _fix_stem_length(params, log)
    elif tag == "㉑":
        _fix_wiper_height(params, neck_h, log)
    elif tag == "㉒":
        _fix_thread_sync(params, log)
    elif tag == "㉓":
        _fix_thread_crest(params, neck_od, log)
    elif tag == "①":
        _fix_cap_od_flush(params, log)
    elif tag == "⑤":
        _fix_wiper_fit(params, neck_id, name, log)
    elif tag == "⑥":
        _fix_stem_orifice(params, log)
    elif tag == "⑫":
        _fix_wand_ceiling(params, log)
    elif tag == "⑬":
        _fix_cross_section(params, log)
    elif tag == "⑮":
        _fix_taper_continuity(params, log)
    elif tag == "⑯":
        _fix_proportion(params, log)


# ═══════════════════════════════════════════════════════════════════
# 个体修复函数
# ═══════════════════════════════════════════════════════════════════

def _fix_cap_cavity_depth(params, neck_h, log):
    """⑱ Cap腔深覆盖瓶颈"""
    cap_cav = _g(params, "cap", "cavity_depth_mm", 23.5)
    if cap_cav >= neck_h:
        return
    new_cav = neck_h + 2.0
    cap_h = _g(params, "cap", "height_mm", 25)
    if new_cav > cap_h - 1.5:
        _s(params, "cap", "height_mm", round(new_cav + 1.5, 1), log,
           f"⑱ 盖高增至 {new_cav + 1.5:.1f}mm（容纳腔深）")
    _s(params, "cap", "cavity_depth_mm", round(new_cav, 1), log,
       f"⑱ 腔深 {cap_cav:.1f}→{new_cav:.1f}mm（≥颈高{neck_h:.1f}）")


def _fix_cap_inner_id(params, neck_od, log):
    """⑲ Cap内径>颈外径"""
    cap_id = _g(params, "cap", "inner_id_mm", 22.4)
    if cap_id > neck_od:
        return
    new_id = neck_od + 2.0
    cap_od = _g(params, "cap", "outer_od_mm", 24)
    if new_id > cap_od - 1.6:
        new_od = round(new_id + 1.6, 1)
        _s(params, "cap", "outer_od_mm", new_od, log,
           f"⑲ 盖外径增至 {new_od:.1f}mm（确保壁厚）")
    _s(params, "cap", "inner_id_mm", round(new_id, 1), log,
       f"⑲ 内径 {cap_id:.1f}→{new_id:.1f}mm（>颈外径{neck_od:.1f}）")


def _fix_stem_length(params, log):
    """⑳ 杆+刷≤瓶内深"""
    inner_depth = _g(params, "bottle", "inner_depth_mm", 55)
    stem_len = _g(params, "wand", "stem_length_mm", 55)
    brush = params.get("wand", {}).get("brush", {})
    brush_len = float(brush.get("length_mm", 12)) if isinstance(brush, dict) else 12
    if stem_len + brush_len <= inner_depth + 3:
        return
    new_stem = max(inner_depth - brush_len, 10)
    _s(params, "wand", "stem_length_mm", round(new_stem, 1), log,
       f"⑳ 杆长 {stem_len:.1f}→{new_stem:.1f}mm（不戳瓶底）")


def _fix_wiper_height(params, neck_h, log):
    """㉑ 内塞高≤颈高"""
    wiper_h = _g(params, "wiper", "height_mm", 12)
    if wiper_h <= neck_h:
        return
    new_h = max(neck_h - 0.5, 3)
    _s(params, "wiper", "height_mm", round(new_h, 1), log,
       f"㉑ 内塞高 {wiper_h:.1f}→{new_h:.1f}mm（≤颈高{neck_h:.1f}）")


def _fix_thread_sync(params, log):
    """㉒ 螺纹全参数同步 (bottle → wand)"""
    b_thr = params.get("bottle", {}).get("thread", {}) or {}
    w_thr = params.get("wand", {}).get("thread", {}) or {}
    if not (bool(b_thr.get("enabled", False)) and bool(w_thr.get("enabled", True))):
        return
    for key in ("turns", "depth_mm", "lead_angle_deg", "segmented", "gap_angle_deg"):
        bv = b_thr.get(key)
        wv = w_thr.get(key)
        if bv is not None and wv is not None and bv != wv:
            _s(params, "wand", f"thread.{key}", bv, log,
               f"㉒ 螺纹{key}: wand={wv}→{bv}（同步bottle）")


def _fix_thread_crest(params, neck_od, log):
    """㉓ 螺纹峰径≈颈外径"""
    w_crest = _g(params, "wand", "thread.crest_dia_mm", 18)
    if abs(w_crest - neck_od) <= 1.0:
        return
    _s(params, "wand", "thread.crest_dia_mm", neck_od, log,
       f"㉓ 峰径 {w_crest:.1f}→{neck_od:.1f}mm（=颈外径）")


def _fix_cap_od_flush(params, log):
    """① 外观齐平"""
    body_od = _g(params, "bottle", "body_od_mm", 24)
    cap_od = _g(params, "cap", "outer_od_mm", 24)
    taper = _g(params, "bottle", "taper_deg", 0)

    if taper > 0:
        H = _g(params, "bottle", "height_mm", 70)
        nh = _g(params, "bottle", "neck_height_mm", 10)
        sh = _g(params, "bottle", "shoulder_height_mm", 6)
        body_h = H - nh - sh
        if body_h > 0:
            delta = 2 * math.tan(math.radians(taper)) * body_h
            target = body_od - delta
        else:
            target = body_od
    else:
        target = body_od

    if abs(cap_od - target) <= 1.0:
        return
    _s(params, "cap", "outer_od_mm", round(target, 1), log,
       f"① 盖外径 {cap_od:.1f}→{target:.1f}mm（齐平）")
    new_id = round(target - 1.6, 1)
    _s(params, "cap", "inner_id_mm", new_id, log,
       f"① 内径联动→{new_id:.1f}mm")


def _fix_wiper_fit(params, neck_id, name, log):
    """⑤/⑤b Wiper或凸环装入瓶颈"""
    if "凸环" in name:
        flange_od = _g(params, "wiper", "flange_od_mm", 17)
        if flange_od <= neck_id:
            return
        new_od = round(neck_id - 0.5, 1)
        _s(params, "wiper", "flange_od_mm", max(new_od, 8), log,
           f"⑤b 凸环外径 {flange_od:.1f}→{new_od:.1f}mm")
    else:
        wiper_od = _g(params, "wiper", "outer_od_mm", 15.5)
        if wiper_od <= neck_id:
            return
        new_od = round(neck_id - 0.5, 1)
        _s(params, "wiper", "outer_od_mm", max(new_od, 8), log,
           f"⑤ 内塞外径 {wiper_od:.1f}→{new_od:.1f}mm（<颈内径{neck_id:.1f}）")


def _fix_stem_orifice(params, log):
    """⑥ Stem穿过Wiper孔口"""
    stem_d = _g(params, "wand", "stem_diameter_mm", 4)
    orifice = _g(params, "wiper", "orifice_mm", 7)
    if orifice > stem_d:
        return
    new_o = round(stem_d + 1.5, 1)
    _s(params, "wiper", "orifice_mm", new_o, log,
       f"⑥ 孔口 {orifice:.1f}→{new_o:.1f}mm（>杆径{stem_d:.1f}）")


def _fix_wand_ceiling(params, log):
    """⑫ Wand顶不超Cap腔顶"""
    cap_cav = _g(params, "cap", "cavity_depth_mm", 23.5)
    wand_cap_h = _g(params, "wand", "cap_height_mm", 18)
    if wand_cap_h <= cap_cav:
        return
    new_cav = round(wand_cap_h + 1.0, 1)
    cap_h = _g(params, "cap", "height_mm", 25)
    if new_cav > cap_h - 1.5:
        _s(params, "cap", "height_mm", round(new_cav + 1.5, 1), log,
           f"⑫ 盖高增至 {new_cav + 1.5:.1f}mm")
    _s(params, "cap", "cavity_depth_mm", new_cav, log,
       f"⑫ 腔深 {cap_cav:.1f}→{new_cav:.1f}mm（容纳wand帽{wand_cap_h:.1f}）")


def _fix_cross_section(params, log):
    """⑬ 截面一致性"""
    cs = params.get("bottle", {}).get("cross_section", "round")
    cr = params.get("bottle", {}).get("corner_radius_mm", 0)
    for comp in ("cap", "wand"):
        cur = params.get(comp, {}).get("cross_section", "round")
        if cur != cs:
            _s(params, comp, "cross_section", cs, log,
               f"⑬ {comp}截面 {cur}→{cs}（同步bottle）")
            _s(params, comp, "corner_radius_mm", cr, log,
               f"⑬ {comp}圆角同步→{cr}mm")


def _fix_taper_continuity(params, log):
    """⑮ 锥度连续性"""
    bt = _g(params, "bottle", "taper_deg", 0)
    ct = _g(params, "cap", "taper_deg", 0)
    if abs(ct - bt) <= 2.0:
        return
    _s(params, "cap", "taper_deg", bt, log,
       f"⑮ 盖锥度 {ct:.1f}→{bt:.1f}°（同步bottle）")


def _fix_proportion(params, log):
    """⑯ 比例合理性"""
    bh = _g(params, "bottle", "height_mm", 70)
    ch = _g(params, "cap", "height_mm", 30)
    if ch <= bh or bh <= 0:
        return
    new_ch = round(bh * 0.9, 1)
    _s(params, "cap", "height_mm", new_ch, log,
       f"⑯ 盖高 {ch:.1f}→{new_ch:.1f}mm（≤瓶高{bh:.1f}）")


# ═══════════════════════════════════════════════════════════════════
# BRep 干涉修复
# ═══════════════════════════════════════════════════════════════════

def _dispatch_brep_fix(params: dict, pair_result: dict, log: list):
    pair = pair_result.get("pair", "")
    vol = pair_result.get("volume_mm3", 0)

    if vol > 50000:
        log.append({
            "component": "assembly", "param": pair,
            "old": vol, "new": None,
            "reason": f"L7 {pair}: 干涉{vol:.0f}mm³过大，需人工检查",
        })
        return

    adj = _brep_adj(vol)

    if "cap" in pair and "wand" in pair:
        _fix_brep_cap_wand(params, vol, adj, log)
    elif "cap" in pair and "bottle" in pair:
        _fix_brep_cap_bottle(params, vol, adj, log)
    elif "wand" in pair and "bottle" in pair:
        wand_od = _g(params, "wand", "outer_od_mm", 21.5)
        new_od = round(max(wand_od - adj * 0.5, 10), 1)
        _s(params, "wand", "outer_od_mm", new_od, log,
           f"L7 wand<->bottle ({vol:.1f}mm³): 外径 {wand_od:.1f}→{new_od:.1f}mm")
    elif "wiper" in pair and "bottle" in pair:
        wiper_od = _g(params, "wiper", "outer_od_mm", 15.5)
        new_od = round(max(wiper_od - adj, 8), 1)
        _s(params, "wiper", "outer_od_mm", new_od, log,
           f"L7 wiper<->bottle ({vol:.1f}mm³): 外径 {wiper_od:.1f}→{new_od:.1f}mm")
    elif "wiper" in pair and "wand" in pair:
        wiper_od = _g(params, "wiper", "outer_od_mm", 15.5)
        new_od = round(max(wiper_od - adj, 8), 1)
        _s(params, "wiper", "outer_od_mm", new_od, log,
           f"L7 wiper<->wand ({vol:.1f}mm³): 外径 {wiper_od:.1f}→{new_od:.1f}mm")


def _fix_brep_cap_wand(params, vol, adj, log):
    """cap<->wand: 建模器感知 + 锥形 Z 位置感知修复

    策略优先级:
    1. 增大 cap 内径/外径（不会被 reconcile 撤销）
    2. 锥形 cap 增大腔深（wand 下沉到更宽处）

    视觉约束: cap_od 上限 body_od + MAX_VISUAL_DEVIATION，
    超出时削减修复量（尽力修但不破坏外观）。
    """
    MAX_VISUAL_DEVIATION = 4.0  # cap 最多比 body 宽 4mm

    # ---- 读取当前参数 ----
    cap_od = _g(params, "cap", "outer_od_mm", 24)
    cap_id = _g(params, "cap", "inner_id_mm", 22.4)
    cap_cav = _g(params, "cap", "cavity_depth_mm", 23.5)
    cap_h = _g(params, "cap", "height_mm", 25)
    cap_taper = _g(params, "cap", "taper_deg", 0)
    body_od = _g(params, "bottle", "body_od_mm", 24)

    wand_od = _g(params, "wand", "outer_od_mm", 21.5)
    wand_cap_h = _g(params, "wand", "cap_height_mm", 18)
    thr = params.get("wand", {}).get("thread", {}) or {}
    thr_on = bool(thr.get("enabled", True))
    thr_crest = float(thr.get("crest_dia_mm", 18.0))
    thr_depth = float(thr.get("depth_mm", 0.5))

    # ---- 计算建模器实际 wand outer_od（含 auto-adjust）----
    actual_wand_od = wand_od
    if thr_on:
        min_wall = thr_depth + 0.5 + 1.0
        modeler_min_od = thr_crest + 2 * min_wall
        actual_wand_od = max(wand_od, modeler_min_od)

    # 每侧目标间隙：干涉量越大需越宽间隙（建模器几何偏差）
    if vol > 2000:
        RADIAL_GAP = 1.5
    elif vol > 100:
        RADIAL_GAP = 1.0
    else:
        RADIAL_GAP = 0.5

    # ---- 锥形 cap 在 wand Z 位置的内径收窄量 ----
    wand_offset = max(cap_cav - wand_cap_h, 0)
    taper_compensation = 0.0
    if cap_taper > 0 and cap_cav > 0:
        taper_shrink = math.tan(math.radians(cap_taper)) * cap_h
        # 1.5x 安全系数：BRep 几何在锥面边缘有非线性偏差（倒角、公差等）
        taper_compensation = taper_shrink * (wand_offset / cap_cav) * 1.5

    # ---- 视觉偏差约束：将 required_cap_id 削减到视觉上限内 ----
    required_cap_id = actual_wand_od + 2 * RADIAL_GAP + 2 * taper_compensation
    max_cap_od = body_od + MAX_VISUAL_DEVIATION
    max_cap_id = max_cap_od - 1.6  # 最小壁厚

    if required_cap_id > max_cap_id:
        # 理想修复超出视觉上限 → 削减到上限（尽力修但不破坏外观）
        log.append({
            "component": "cap", "param": "outer_od_mm",
            "old": cap_od, "new": None,
            "reason": (f"L7 cap<->wand ({vol:.0f}mm³): 理想cap_id={required_cap_id:.1f}"
                       f" 超出视觉上限{max_cap_id:.1f}mm → 削减"),
        })
        required_cap_id = max_cap_id

    # ---- 策略1（核心）: 增大 cap 内径以容纳 wand + 锥形补偿 ----
    if cap_id < required_cap_id:
        new_cap_id = round(required_cap_id, 1)
        reason = (f"L7 cap<->wand ({vol:.1f}mm³): cap内径 {cap_id:.1f}→{new_cap_id:.1f}mm"
                  f" (wand实际OD={actual_wand_od:.1f}+间隙{2*RADIAL_GAP:.1f}")
        if taper_compensation > 0.05:
            reason += f"+锥形补偿{2*taper_compensation:.1f}"
        reason += ")"
        _s(params, "cap", "inner_id_mm", new_cap_id, log, reason)
        cap_id = new_cap_id
        # 增大 cap 外径以保持壁厚
        min_cap_od = cap_id + 1.6
        if cap_od < min_cap_od:
            new_cap_od = round(min_cap_od, 1)
            _s(params, "cap", "outer_od_mm", new_cap_od, log,
               f"L7 cap<->wand: cap外径 {cap_od:.1f}→{new_cap_od:.1f}mm (保壁厚≥0.8)")
            cap_od = new_cap_od

    # ---- 策略2: 锥形 cap 增大腔深 → wand 下沉到更宽处 ----
    if cap_taper > 0:
        cav_adj = min(adj * 0.5, 2.0)
        new_cav = round(cap_cav + cav_adj, 1)
        if new_cav > cap_h - 1.5:
            _s(params, "cap", "height_mm", round(new_cav + 1.5, 1), log,
               f"L7 cap<->wand: 盖高增至 {new_cav + 1.5:.1f}mm (容纳深腔)")
        _s(params, "cap", "cavity_depth_mm", new_cav, log,
           f"L7 cap<->wand: 腔深 {cap_cav:.1f}→{new_cav:.1f}mm (锥形轴向避让)")


def _fix_brep_cap_bottle(params, vol, adj, log):
    """cap<->bottle: 多边形优先扩内径，圆形优先缩颈径。

    策略优先级:
      0. 多边形盖扩内径 — 内切圆不足时扩大内径（避免破坏性缩颈）
      1. 缩小 bottle.neck_od_mm — 圆形盖颈部越界的根因修复
      2. 增大 inner_id（减薄壁厚）— 肩部/导入角区域干涉
      3. 减小 cavity_depth — 最后手段
    """
    cap_od = _g(params, "cap", "outer_od_mm", 24)
    cap_id = _g(params, "cap", "inner_id_mm", 22.4)
    cap_cav = _g(params, "cap", "cavity_depth_mm", 23.5)
    cap_h = _g(params, "cap", "height_mm", 25)
    neck_od = _g(params, "bottle", "neck_od_mm", 18)
    cap_cs = str(params.get("cap", {}).get("cross_section", "round"))

    # ---- 计算 cap 内腔有效通过直径 ----
    # 多边形内腔：圆形颈部需通过最窄处（边中点），即内切圆直径
    effective_cap_id = cap_id
    _n_map = {"triangle": 3, "square": 4, "hexagon": 6, "octagon": 8}
    _n = _n_map.get(cap_cs, 0)
    if _n >= 3:
        effective_cap_id = cap_id * math.cos(math.pi / _n)

    # ---- 多边形盖优先扩内径 ----
    # 多边形盖的干涉根因通常是内切圆太小，而非颈径太大，
    # 优先扩大内径（让内切圆 ≥ 颈径），避免破坏性缩颈
    if _n >= 3 and neck_od >= effective_cap_id:
        cos_factor = math.cos(math.pi / _n)
        # 目标: inner_id * cos(π/n) ≥ neck_od + 间隙
        needed_id = (neck_od + 1.0) / cos_factor
        max_id = cap_od - 0.6  # 最小壁厚 0.3mm/侧
        new_id = round(min(needed_id, max_id), 1)
        if new_id > cap_id:
            _s(params, "cap", "inner_id_mm", new_id, log,
               f"L7 cap<->bottle ({vol:.1f}mm³): "
               f"多边形内径 {cap_id:.1f}->{new_id:.1f}mm "
               f"(内切圆{new_id * cos_factor:.1f}mm ≥ 颈径{neck_od:.1f}mm)")
            return

    # ---- 策略1: 缩颈径（根因修复）+ 级联内塞 ----
    if neck_od >= effective_cap_id:
        new_neck = round(max(effective_cap_id - adj, 8.0), 1)
        # BRep 干涉最高优先级，直接修改（覆盖 _USER_LOCKED）
        old = neck_od
        params.setdefault("bottle", {})["neck_od_mm"] = new_neck
        log.append({
            "component": "bottle", "param": "neck_od_mm",
            "old": round(old, 2), "new": new_neck,
            "reason": (f"L7 cap<->bottle ({vol:.1f}mm³): "
                       f"颈径 {old:.1f}->{new_neck:.1f}mm "
                       f"(缩颈: 盖内腔有效通过={effective_cap_id:.1f}mm)"),
        })

        # 级联：缩颈后内塞可能塞不进新颈部，同步调整
        lip_t = _g(params, "bottle", "lip_thickness_mm", 1.0)
        new_neck_id = new_neck - 2 * lip_t
        wiper = params.get("wiper", {})
        if wiper:
            wiper_od = float(wiper.get("outer_od_mm", 0))
            if wiper_od > new_neck_id:
                new_wiper_od = round(new_neck_id - 0.3, 1)
                wiper["outer_od_mm"] = new_wiper_od
                wiper["inner_id_mm"] = round(new_wiper_od - 2.0, 1)
                log.append({
                    "component": "wiper", "param": "outer_od_mm",
                    "old": round(wiper_od, 2), "new": new_wiper_od,
                    "reason": (f"级联: 颈内径{new_neck_id:.1f}mm "
                               f"→ 内塞外径 {wiper_od:.1f}->{new_wiper_od:.1f}mm"),
                })
            flange_od = float(wiper.get("flange_od_mm", 0))
            if flange_od > new_neck_id:
                new_flange = round(new_neck_id - 0.2, 1)
                wiper["flange_od_mm"] = new_flange
                log.append({
                    "component": "wiper", "param": "flange_od_mm",
                    "old": round(flange_od, 2), "new": new_flange,
                    "reason": (f"级联: 颈内径{new_neck_id:.1f}mm "
                               f"→ 凸环外径 {flange_od:.1f}->{new_flange:.1f}mm"),
                })
                # 同步凸环内径（必须 < 凸环外径，否则 flange_valid 硬规则失败）
                flange_id = float(wiper.get("flange_id_mm", 0))
                if flange_id >= new_flange:
                    new_flange_id = round(new_flange - 1.0, 1)
                    wiper["flange_id_mm"] = new_flange_id
        return

    # ---- 策略2: 增大 inner_id（减薄壁厚）----
    max_id = cap_od - 0.6
    if cap_id < max_id:
        id_increase = min(adj, max_id - cap_id)
        new_id = round(cap_id + id_increase, 1)
        if _s(params, "cap", "inner_id_mm", new_id, log,
              f"L7 cap<->bottle ({vol:.1f}mm³): 内径 {cap_id:.1f}->{new_id:.1f}mm (减薄壁厚避让)"):
            return

    # ---- 策略3: 减小腔深 ----
    cav_reduce = max(adj, min(vol * 0.02, 5.0))
    new_cav = round(max(cap_cav - cav_reduce, cap_h * 0.5), 1)
    if new_cav < cap_cav:
        _s(params, "cap", "cavity_depth_mm", new_cav, log,
           f"L7 cap<->bottle ({vol:.1f}mm³): 腔深 {cap_cav:.1f}->{new_cav:.1f}mm (加厚底部避肩)")
