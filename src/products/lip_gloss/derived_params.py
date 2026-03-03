# -*- coding: utf-8 -*-
"""
唇釉瓶派生参数规则（Lip Gloss Derived Params）

本模块定义唇釉瓶各组件的派生参数计算规则。

组件：
- cap (瓶盖): inner_id_mm, cavity_depth_mm
- bottle (瓶身): shoulder_height_mm, inner_depth_mm, wall_thickness_mm, capacity_ml
- wand (刷杆): seal_ring.od_mm, cavity_depth_mm
- wiper (内塞): inner_id_mm, flange_od_mm, flange_id_mm

设计原则：
- 核心参数（is_core=True）：用户自由指定，系统不修改
- 派生参数（is_core=False）：由核心参数自动计算
- 动态范围：派生参数的 min/max 随核心参数变化

作者：AiCad
日期：2026
"""
from __future__ import annotations

import math
from typing import Any, Dict, Tuple

from typing import List

from core.param_system import CrossComponentDerived, DerivedRule, get_derived_registry
from core.component_state import get_state_manager


# ═══════════════════════════════════════════════════════════════════════════
# 常量：工艺参数
# ═══════════════════════════════════════════════════════════════════════════

# 瓶盖 (Cap)
CAP_MIN_WALL = 0.8           # 最小壁厚 mm
CAP_MIN_TOP_THICK = 1.5      # 最小顶部厚度 mm

# 瓶身 (Bottle)
BOTTLE_MIN_WALL = 1.0        # 最小壁厚 mm
BOTTLE_MIN_BOTTOM = 1.5      # 最小底厚 mm
BOTTLE_MIN_SHOULDER = 5.0    # 最小肩高 mm

# 刷杆 (Wand)
WAND_GAP_SEAL_RING = 5.5     # 外径 - 气密环外径间隙
WAND_MIN_TOP_THICK = 0.5     # 盖子最小顶厚 mm（装配时cap顶面提供结构支撑）

# 内塞 (Wiper)
WIPER_MIN_WALL = 1.0         # 最小壁厚 mm


# ═══════════════════════════════════════════════════════════════════════════
# Cap 组件派生规则
# ═══════════════════════════════════════════════════════════════════════════

def cap_inner_id_default(outer_od: float, params: Dict[str, Any]) -> float:
    """计算内径默认值：外径 - 2 * 最小壁厚"""
    return outer_od - 2 * CAP_MIN_WALL


def cap_inner_id_range(outer_od: float, params: Dict[str, Any]) -> Tuple[float, float]:
    """计算内径动态范围：最大 = 外径 - 1.6mm（最小壁厚），最小 = 8mm"""
    max_id = outer_od - 2 * CAP_MIN_WALL
    min_id = 8.0
    return (min_id, max_id)


def cap_cavity_depth_default(height: float, params: Dict[str, Any]) -> float:
    """计算内腔深默认值：总高 - 最小顶部厚度"""
    return height - CAP_MIN_TOP_THICK


def cap_cavity_depth_range(height: float, params: Dict[str, Any]) -> Tuple[float, float]:
    """计算内腔深动态范围：最大 = 总高 - 1.5mm，最小 = 5mm"""
    max_depth = height - CAP_MIN_TOP_THICK
    min_depth = 5.0
    return (min_depth, max_depth)


CAP_DERIVED_RULES: Dict[str, DerivedRule] = {
    "inner_id_mm": DerivedRule(
        master_param="outer_od_mm",
        compute_default=cap_inner_id_default,
        compute_range=cap_inner_id_range,
        description="内径 = 外径 - 1.6mm（最小壁厚0.8mm）"
    ),
    "cavity_depth_mm": DerivedRule(
        master_param="height_mm",
        compute_default=cap_cavity_depth_default,
        compute_range=cap_cavity_depth_range,
        description="内腔深 = 总高 - 1.5mm（最小顶厚）"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# Bottle 组件派生规则
# ═══════════════════════════════════════════════════════════════════════════

def bottle_shoulder_height_default(body_od: float, params: Dict[str, Any]) -> float:
    """计算肩高默认值：较短肩部确保cap紧密配合、wand不进入肩部区域"""
    neck_od = params.get("neck_od_mm", 18.0)
    diff = body_od - neck_od
    return max(BOTTLE_MIN_SHOULDER, diff * 0.5 + 3.0)


def bottle_shoulder_height_range(body_od: float, params: Dict[str, Any]) -> Tuple[float, float]:
    """计算肩高动态范围"""
    neck_od = params.get("neck_od_mm", 18.0)
    diff = body_od - neck_od
    min_h = max(BOTTLE_MIN_SHOULDER, diff * 0.3)
    height = params.get("height_mm", 70.0)
    max_h = min(height * 0.4, 30.0)
    return (min_h, max_h)


def bottle_inner_depth_default(height: float, params: Dict[str, Any]) -> float:
    """计算内深默认值：总高 - 底厚 - 余量"""
    bottom_t = params.get("bottom_thickness_mm", 2.0)
    return height - bottom_t - 3.0


def bottle_inner_depth_range(height: float, params: Dict[str, Any]) -> Tuple[float, float]:
    """计算内深动态范围"""
    bottom_t = params.get("bottom_thickness_mm", 2.0)
    neck_h = params.get("neck_height_mm", 10.0)
    min_depth = neck_h + 5.0
    max_depth = height - bottom_t - 0.5
    return (min_depth, max_depth)


def bottle_wall_thickness_default(body_od: float, params: Dict[str, Any]) -> float:
    """计算壁厚默认值：外径的 5%，但有上下限"""
    wall = body_od * 0.05
    return max(BOTTLE_MIN_WALL, min(2.0, wall))


def bottle_wall_thickness_range(body_od: float, params: Dict[str, Any]) -> Tuple[float, float]:
    """计算壁厚动态范围"""
    max_wall = min(body_od * 0.15, 3.0)
    return (BOTTLE_MIN_WALL, max_wall)


def bottle_capacity_default(body_od: float, params: Dict[str, Any]) -> float:
    """计算容量：根据尺寸自动计算"""
    wall = params.get("wall_thickness_mm", 1.2)
    inner_depth = params.get("inner_depth_mm", 55.0)
    inner_d = body_od - 2 * wall
    inner_r = inner_d / 2.0
    v_ml = math.pi * inner_r * inner_r * inner_depth / 1000.0
    return round(v_ml, 1)


BOTTLE_DERIVED_RULES: Dict[str, DerivedRule] = {
    "shoulder_height_mm": DerivedRule(
        master_param="body_od_mm",
        compute_default=bottle_shoulder_height_default,
        compute_range=bottle_shoulder_height_range,
        description="肩高随瓶身外径和颈径差距联动"
    ),
    "inner_depth_mm": DerivedRule(
        master_param="height_mm",
        compute_default=bottle_inner_depth_default,
        compute_range=bottle_inner_depth_range,
        description="内深 = 总高 - 底厚 - 余量"
    ),
    "wall_thickness_mm": DerivedRule(
        master_param="body_od_mm",
        compute_default=bottle_wall_thickness_default,
        compute_range=bottle_wall_thickness_range,
        description="壁厚随外径联动（约外径的 5%）"
    ),
    "capacity_ml": DerivedRule(
        master_param="body_od_mm",
        compute_default=bottle_capacity_default,
        compute_range=None,  # 容量只有计算值，无可调范围
        description="容量由尺寸自动计算"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# Wand 组件派生规则
# ═══════════════════════════════════════════════════════════════════════════

def wand_seal_ring_od_default(outer_od: float, params: Dict[str, Any]) -> float:
    """计算气密环外径默认值：外径 - 5.5mm"""
    return outer_od - WAND_GAP_SEAL_RING


def wand_seal_ring_od_range(outer_od: float, params: Dict[str, Any]) -> Tuple[float, float]:
    """计算气密环外径动态范围"""
    max_od = outer_od - 3.0
    min_od = 10.0
    return (min_od, max_od)


def wand_cavity_depth_default(cap_height: float, params: Dict[str, Any]) -> float:
    """计算盖子内腔深度默认值：盖高 - 2mm（顶部壁厚）"""
    return cap_height - WAND_MIN_TOP_THICK


def wand_cavity_depth_range(cap_height: float, params: Dict[str, Any]) -> Tuple[float, float]:
    """计算盖子内腔深度动态范围"""
    max_depth = cap_height - 0.3  # 最薄顶壁 0.3mm
    min_depth = 5.0
    return (min_depth, max_depth)


def wand_mouth_to_top_default(cap_height: float, params: Dict[str, Any]) -> float:
    """口部至顶距离 ≈ 盖高 × 0.63"""
    return round(cap_height * 0.63, 1)


def wand_mouth_to_top_range(cap_height: float, params: Dict[str, Any]) -> Tuple[float, float]:
    return (max(5.0, cap_height * 0.5), min(25.0, cap_height * 0.8))


def wand_stem_length_default(total_height: float, params: Dict[str, Any]) -> float:
    """杆长 = 总高 - 盖高"""
    cap_h = params.get("cap_height_mm", 19.0)
    return round(total_height - cap_h, 1)


def wand_stem_length_range(total_height: float, params: Dict[str, Any]) -> Tuple[float, float]:
    cap_h = params.get("cap_height_mm", 19.0)
    min_sl = max(20.0, total_height - cap_h - 10.0)
    max_sl = total_height - cap_h + 5.0
    return (min_sl, max_sl)


def wand_thread_crest_dia_default(outer_od: float, params: Dict[str, Any]) -> float:
    """螺纹峰径 ≈ 外径 - 5mm（壁厚 2.5mm 单侧）"""
    return round(outer_od - 5.0, 1)


def wand_thread_crest_dia_range(outer_od: float, params: Dict[str, Any]) -> Tuple[float, float]:
    max_crest = outer_od - 4.0
    min_crest = max(10.0, outer_od - 8.0)
    return (min_crest, max_crest)


WAND_DERIVED_RULES: Dict[str, DerivedRule] = {
    "seal_ring.od_mm": DerivedRule(
        master_param="outer_od_mm",
        compute_default=wand_seal_ring_od_default,
        compute_range=wand_seal_ring_od_range,
        description="气密环外径 = 刷杆外径 - 5.5mm"
    ),
    "cavity_depth_mm": DerivedRule(
        master_param="cap_height_mm",
        compute_default=wand_cavity_depth_default,
        compute_range=wand_cavity_depth_range,
        description="内腔深 = 盖高 - 2mm（顶厚）"
    ),
    "mouth_to_top_mm": DerivedRule(
        master_param="cap_height_mm",
        compute_default=wand_mouth_to_top_default,
        compute_range=wand_mouth_to_top_range,
        description="口部至顶 ≈ 盖高 × 0.63"
    ),
    "stem_length_mm": DerivedRule(
        master_param="total_height_mm",
        compute_default=wand_stem_length_default,
        compute_range=wand_stem_length_range,
        description="杆长 = 总高 - 盖高"
    ),
    "thread.crest_dia_mm": DerivedRule(
        master_param="outer_od_mm",
        compute_default=wand_thread_crest_dia_default,
        compute_range=wand_thread_crest_dia_range,
        description="螺纹峰径 ≈ 外径 - 5mm"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# Wiper 组件派生规则
# ═══════════════════════════════════════════════════════════════════════════

def wiper_inner_id_default(outer_od: float, params: Dict[str, Any]) -> float:
    """计算内径默认值：外径 - 2 * 最小壁厚"""
    return outer_od - 2 * WIPER_MIN_WALL


def wiper_inner_id_range(outer_od: float, params: Dict[str, Any]) -> Tuple[float, float]:
    """计算内径动态范围"""
    orifice = params.get("orifice_mm", 7.0)
    min_id = orifice + 1.0
    max_id = outer_od - 1.0
    return (min_id, max_id)


def wiper_flange_od_default(outer_od: float, params: Dict[str, Any]) -> float:
    """计算凸环外径默认值：外径 + 1.5mm"""
    return outer_od + 1.5


def wiper_flange_od_range(outer_od: float, params: Dict[str, Any]) -> Tuple[float, float]:
    """计算凸环外径动态范围"""
    min_od = outer_od
    max_od = outer_od + 4.0
    return (min_od, max_od)


def wiper_flange_id_default(outer_od: float, params: Dict[str, Any]) -> float:
    """计算凸环内径默认值：外径 - 1mm"""
    return outer_od - 1.0


def wiper_flange_id_range(outer_od: float, params: Dict[str, Any]) -> Tuple[float, float]:
    """计算凸环内径动态范围"""
    flange_od = params.get("flange_od_mm", outer_od + 1.5)
    min_id = 5.0
    max_id = flange_od - 1.0
    return (min_id, max_id)


WIPER_DERIVED_RULES: Dict[str, DerivedRule] = {
    "inner_id_mm": DerivedRule(
        master_param="outer_od_mm",
        compute_default=wiper_inner_id_default,
        compute_range=wiper_inner_id_range,
        description="内径 = 外径 - 2mm（壁厚1mm）"
    ),
    "flange_od_mm": DerivedRule(
        master_param="outer_od_mm",
        compute_default=wiper_flange_od_default,
        compute_range=wiper_flange_od_range,
        description="凸环外径 = 外径 + 1.5mm"
    ),
    "flange_id_mm": DerivedRule(
        master_param="outer_od_mm",
        compute_default=wiper_flange_id_default,
        compute_range=wiper_flange_id_range,
        description="凸环内径 = 外径 - 1mm"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# 注册函数
# ═══════════════════════════════════════════════════════════════════════════

def register_lip_gloss_derived_rules() -> None:
    """
    注册唇釉瓶的所有派生参数规则

    调用此函数将规则注册到全局注册表
    """
    registry = get_derived_registry()

    # 避免重复注册
    if registry.is_product_registered("lip_gloss"):
        return

    registry.register_rules("lip_gloss", "cap", CAP_DERIVED_RULES)
    registry.register_rules("lip_gloss", "bottle", BOTTLE_DERIVED_RULES)
    registry.register_rules("lip_gloss", "wand", WAND_DERIVED_RULES)
    registry.register_rules("lip_gloss", "wiper", WIPER_DERIVED_RULES)


def get_derived_rule(component_id: str, param_key: str) -> DerivedRule:
    """
    获取指定组件的派生规则（便捷函数）

    Args:
        component_id: 组件 ID（cap/bottle/wand/wiper）
        param_key: 参数键

    Returns:
        DerivedRule 对象

    Raises:
        KeyError: 如果规则不存在
    """
    rules_map = {
        "cap": CAP_DERIVED_RULES,
        "bottle": BOTTLE_DERIVED_RULES,
        "wand": WAND_DERIVED_RULES,
        "wiper": WIPER_DERIVED_RULES,
    }

    component_rules = rules_map.get(component_id)
    if component_rules is None:
        raise KeyError(f"Unknown component: {component_id}")

    rule = component_rules.get(param_key)
    if rule is None:
        raise KeyError(f"No derived rule for {component_id}.{param_key}")

    return rule


# ═══════════════════════════════════════════════════════════════════════════
# 跨组件双向派生规则（多米诺骨牌系统）
#
# 设计原则（参考 Yin & Ma "Feature Parameter Map" + Clarkson DSM）：
# - 任意组件可为首发，首发组件的核心参数成为"第一推力"
# - 每对物理包含关系产生双向约束：
#   外部先 → 内部上限锁定；内部先 → 外部下限/精确值锁定
# - 多约束冲突时取区间交集（由 component_state.py 实现）
# ═══════════════════════════════════════════════════════════════════════════

# 跨组件间隙/配合常量
GAP_CAP_WAND = 0.9            # 瓶盖内径 - 刷杆外径（紧密配合）
GAP_CAP_WAND_MIN = 0.5        # 最小间隙
GAP_CAP_WAND_MAX = 1.0        # 最大间隙
GAP_CAP_WAND_DEPTH = 6.5      # 瓶盖内腔深 - 刷杆盖高（含垫圈1.5mm + safe_z余量）
GAP_WIPER_STEM = 1.5          # 内塞孔径 - 刷杆杆径
    # （已移除 GAP_SEAL_ORIFICE：密封塞改为垫圈，无需孔口间隙）
BOTTLE_LIP_THICK = 1.0        # 瓶唇标准厚度
BOTTLE_NECK_CLEARANCE = 0.2   # 瓶颈内壁间隙

# Bottle ↔ Wand 杆长约束
BOTTLE_WAND_BRUSH_LEN = 12.0  # 刷头长度（典型值）
BOTTLE_WAND_CLEARANCE = 3.0   # 杆尖到瓶底余量
BOTTLE_WAND_MARGIN = 8.0      # 杆长→内深的余量上限

# Bottle ↔ Wiper 高度约束
BOTTLE_WIPER_NECK_GAP = 1.0   # 内塞-颈部高度间隙


CROSS_COMPONENT_RULES: List[CrossComponentDerived] = [

    # ═══════════════════════════════════════════════════════════════════
    # A 组：Cap ↔ Wand（盖⊃刷杆盖部 — 双向 6 条）
    # ═══════════════════════════════════════════════════════════════════

    # A1: Cap 外壳定 → Wand 盖部外径上限
    CrossComponentDerived(
        source_component="cap",
        source_param="inner_id_mm",
        target_component="wand",
        target_param="outer_od_mm",
        compute_range=lambda v, p: (v - GAP_CAP_WAND_MAX, v - GAP_CAP_WAND_MIN),
        compute_default=lambda v, p: round(v - GAP_CAP_WAND, 1),
        lock_when_set=True,
        description="刷杆外径 ≈ 瓶盖内径 - 0.9mm（瓶盖⊃刷杆，上限锁定）"
    ),
    # A2: Wand 盖部定 → Cap 内径下限
    # 内径 = 外径 + 间隙（0.5~1.5mm），上限收紧避免超过 cap 壁厚极限
    CrossComponentDerived(
        source_component="wand",
        source_param="outer_od_mm",
        target_component="cap",
        target_param="inner_id_mm",
        compute_range=lambda v, p: (v + GAP_CAP_WAND_MIN, v + GAP_CAP_WAND_MAX + 0.5),
        compute_default=lambda v, p: round(v + GAP_CAP_WAND, 1),
        lock_when_set=True,
        description="瓶盖内径 ≈ 刷杆外径 + 0.9mm（内部定→外部下限锁定）"
    ),

    # A3: Cap 腔深定 → Wand 盖高上限
    # 注意：wand.cap_height_mm schema min=8.0，约束下限不得低于此值
    CrossComponentDerived(
        source_component="cap",
        source_param="cavity_depth_mm",
        target_component="wand",
        target_param="cap_height_mm",
        compute_range=lambda v, p: (8.0, v - GAP_CAP_WAND_DEPTH),
        compute_default=lambda v, p: round(v - GAP_CAP_WAND_DEPTH, 1),
        lock_when_set=False,
        description="刷杆盖高 ≤ 瓶盖内腔深 - 4mm"
    ),
    # A4: Wand 盖高定 → Cap 腔深下限
    # 只设下限：cavity_depth ≥ cap_height + 4mm（wand 盖子必须能装入）
    # 上限不做限制（由 cap 自身高度约束 cavity_depth ≤ height - 1.5）
    CrossComponentDerived(
        source_component="wand",
        source_param="cap_height_mm",
        target_component="cap",
        target_param="cavity_depth_mm",
        compute_range=lambda v, p: (v + GAP_CAP_WAND_DEPTH, 70.0),
        compute_default=lambda v, p: round(v + GAP_CAP_WAND_DEPTH, 1),
        lock_when_set=False,
        description="瓶盖内腔深 ≥ 刷杆盖高 + 4mm"
    ),

    # A5: Cap 总高定 → Wand 总高范围
    # 只设下限（刷杆至少比瓶盖高 30mm），不设人为上限
    # 上限由 wand schema max 和瓶身深度决定
    CrossComponentDerived(
        source_component="cap",
        source_param="height_mm",
        target_component="wand",
        target_param="total_height_mm",
        compute_range=lambda v, p: (v + 30.0, 200.0),
        compute_default=lambda v, p: round(v + 40.0, 1),
        lock_when_set=False,
        description="刷杆总高 ≥ 瓶盖高 + 30mm（上限由瓶身深度决定）"
    ),
    # A6: Wand 总高定 → Cap 总高上限
    # 注意：cap.height 下限需 ≥ cavity_depth + 1.5（顶厚），
    # 而 cavity_depth ≥ cap_height + 4，所以 height ≥ cap_height + 5.5
    # 安全下限取 cap_height + 6 或最小 15mm
    CrossComponentDerived(
        source_component="wand",
        source_param="total_height_mm",
        target_component="cap",
        target_param="height_mm",
        compute_range=lambda v, p: (max(15.0, p.get('cap_height_mm', 19.0) + 6.0),
                                    v - 30.0),
        compute_default=lambda v, p: round(v - 40.0, 1),
        lock_when_set=False,
        description="瓶盖高 ≤ 刷杆总高 - 30mm（且 ≥ 盖高 + 6）"
    ),

    # ═══════════════════════════════════════════════════════════════════
    # B 组：Cap ↔ Bottle（外径平齐 + 颈部配合 — 双向 6 条）
    # ═══════════════════════════════════════════════════════════════════

    # B1: Cap 外径定 → Bottle 瓶身外径锁定（等径齐平）
    # 真实唇釉：cap 外径 = 瓶身外径，cap 套住瓶颈而非瓶身
    # cap 内径(22.4) < body_od(24)，cap 坐在肩部斜面清除点上
    CrossComponentDerived(
        source_component="cap",
        source_param="outer_od_mm",
        target_component="bottle",
        target_param="body_od_mm",
        compute_range=lambda v, p: (v - 0.5, v + 0.5),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="瓶身外径 ≈ 瓶盖外径（外观齐平）"
    ),
    # B2: Bottle 外径定 → Cap 外径锁定（等径齐平）
    CrossComponentDerived(
        source_component="bottle",
        source_param="body_od_mm",
        target_component="cap",
        target_param="outer_od_mm",
        compute_range=lambda v, p: (v - 0.5, v + 0.5),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="瓶盖外径 ≈ 瓶身外径（外观齐平）"
    ),

    # B3: Cap 内径定 → Bottle 颈外径范围
    # 物理约束：颈外径 < 瓶盖内径（瓶颈必须能装入瓶盖内腔）
    # 下限只用 finish 规格约束（QC 检查 |neck_od - spec_od| ≤ 1.0）
    # 注意：大瓶盖 (inner_id=31.6) 可以配小口径 (finish 18-415)，
    #       不能强制 neck_od 接近 inner_id，否则与 finish 冲突
    CrossComponentDerived(
        source_component="cap",
        source_param="inner_id_mm",
        target_component="bottle",
        target_param="neck_od_mm",
        compute_range=lambda v, p: (
            float(str(p.get('finish', '18-415')).split('-')[0]) - 1.0,
            min(v - 0.5, float(str(p.get('finish', '18-415')).split('-')[0]) + 1.0)
        ),
        compute_default=lambda v, p: round(float(str(p.get('finish', '18-415')).split('-')[0]), 1),
        lock_when_set=False,
        description="颈外径 ≈ finish 规格值（±1mm），且 < 瓶盖内径"
    ),
    # B4: Bottle 颈外径定 → Cap 内径下限
    # 物理约束：inner_id > neck_od（瓶颈装入瓶盖）
    # 上限受瓶身外径约束：inner_id ≤ body_od - 1.6（最小壁厚0.8×2）
    CrossComponentDerived(
        source_component="bottle",
        source_param="neck_od_mm",
        target_component="cap",
        target_param="inner_id_mm",
        compute_range=lambda v, p: (v + 0.5,
                                    min(v + 15.0, p.get('body_od_mm', 24.0) - 1.6)),
        compute_default=lambda v, p: round(v + 4.0, 1),
        lock_when_set=False,
        description="瓶盖内径 > 瓶颈外径 + 0.5mm，≤ 瓶身外径 - 1.6mm（壁厚）"
    ),

    # B5: Cap 高度定 → Bottle 颈高范围
    # 颈高下限 7.0mm：螺纹安全需 pitch*turns+1 ≈ 2.7*2+1=6.4，取 7.0
    CrossComponentDerived(
        source_component="cap",
        source_param="cavity_depth_mm",
        target_component="bottle",
        target_param="neck_height_mm",
        compute_range=lambda v, p: (7.0, max(7.0, v * 0.6)),
        compute_default=lambda v, p: round(max(7.0, v * 0.45), 1),
        lock_when_set=False,
        description="颈高 ≥ 7mm（螺纹安全）且 ≤ 瓶盖腔深 × 0.6"
    ),
    # B6: Bottle 颈高定 → Cap 腔深下限
    # 只设下限：cavity_depth ≥ neck_height + 2mm（盖腔需覆盖瓶颈）
    # 上限不做限制（由 cap 自身高度约束 cavity_depth ≤ height - 1.5）
    CrossComponentDerived(
        source_component="bottle",
        source_param="neck_height_mm",
        target_component="cap",
        target_param="cavity_depth_mm",
        compute_range=lambda v, p: (max(v + 2.0, 12.0), 70.0),
        compute_default=lambda v, p: round(v + 5.0, 1),
        lock_when_set=False,
        description="瓶盖腔深 ≥ 颈高 + 2mm（且 ≥ 12mm）"
    ),

    # ═══════════════════════════════════════════════════════════════════
    # C 组：（已移除）密封塞改为内腔顶面垫圈，无需与孔口配合
    # ═══════════════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════════════
    # D 组：Bottle ↔ Wiper（颈部⊃内塞 — 双向 4 条）
    # ═══════════════════════════════════════════════════════════════════

    # D1: Bottle 颈外径定 → Wiper 凸环外径上限
    CrossComponentDerived(
        source_component="bottle",
        source_param="neck_od_mm",
        target_component="wiper",
        target_param="flange_od_mm",
        compute_range=lambda v, p: (v - 2.0, v - 0.5),
        compute_default=lambda v, p: round(v - 1.0, 1),
        lock_when_set=True,
        description="内塞凸环外径 ≈ 瓶颈外径 - 1mm（颈部⊃内塞）"
    ),
    # D2: Wiper 凸环外径定 → Bottle 颈外径下限
    CrossComponentDerived(
        source_component="wiper",
        source_param="flange_od_mm",
        target_component="bottle",
        target_param="neck_od_mm",
        compute_range=lambda v, p: (v + 0.5, v + 2.0),
        compute_default=lambda v, p: round(v + 1.0, 1),
        lock_when_set=True,
        description="瓶颈外径 ≈ 内塞凸环外径 + 1mm（内部定→外部下限）"
    ),

    # D3: Bottle 颈内径定 → Wiper 外径上限
    CrossComponentDerived(
        source_component="bottle",
        source_param="neck_od_mm",
        target_component="wiper",
        target_param="outer_od_mm",
        # 颈内径 = neck_od - 2 * lip_thickness; wiper.outer_od < 颈内径
        compute_range=lambda v, p: (8.0, v - 2 * BOTTLE_LIP_THICK - BOTTLE_NECK_CLEARANCE),
        compute_default=lambda v, p: round(v - 2 * BOTTLE_LIP_THICK - 0.5, 1),
        lock_when_set=True,
        description="内塞外径 < 瓶颈内径（颈部⊃内塞筒体）"
    ),
    # D4: Wiper 外径定 → Bottle 颈外径下限
    CrossComponentDerived(
        source_component="wiper",
        source_param="outer_od_mm",
        target_component="bottle",
        target_param="neck_od_mm",
        compute_range=lambda v, p: (v + 2 * BOTTLE_LIP_THICK + BOTTLE_NECK_CLEARANCE,
                                    v + 2 * BOTTLE_LIP_THICK + 3.0),
        compute_default=lambda v, p: round(v + 2 * BOTTLE_LIP_THICK + 0.5, 1),
        lock_when_set=True,
        description="瓶颈外径 ≥ 内塞外径 + 2×唇厚 + 间隙（内部定→外部下限）"
    ),

    # ═══════════════════════════════════════════════════════════════════
    # E 组：Wiper ↔ Wand（孔口⊃刷杆杆部 — 双向 2 条）
    # ═══════════════════════════════════════════════════════════════════

    # E1: Wiper 孔径定 → Wand 杆径上限
    CrossComponentDerived(
        source_component="wiper",
        source_param="orifice_mm",
        target_component="wand",
        target_param="stem_diameter_mm",
        compute_range=lambda v, p: (2.0, v - GAP_WIPER_STEM),
        compute_default=lambda v, p: round(v - 2.5, 1),
        lock_when_set=False,
        description="刷杆杆径 < 内塞孔径 - 1.5mm（杆穿过孔口）"
    ),
    # E2: Wand 杆径定 → Wiper 孔径下限
    CrossComponentDerived(
        source_component="wand",
        source_param="stem_diameter_mm",
        target_component="wiper",
        target_param="orifice_mm",
        compute_range=lambda v, p: (v + GAP_WIPER_STEM, v + 4.0),
        compute_default=lambda v, p: round(v + 2.5, 1),
        lock_when_set=False,
        description="内塞孔径 ≥ 刷杆杆径 + 1.5mm（杆穿过孔口）"
    ),

    # ═══════════════════════════════════════════════════════════════════
    # F 组：Wand ↔ Bottle 螺纹互锁（双向 4 条）
    # ═══════════════════════════════════════════════════════════════════

    # F1: Wand 螺纹峰径定 → Bottle 颈外径锁定
    CrossComponentDerived(
        source_component="wand",
        source_param="thread.crest_dia_mm",
        target_component="bottle",
        target_param="neck_od_mm",
        compute_range=lambda v, p: (v - 0.5, v + 0.5),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="瓶颈外径 = 刷杆螺纹峰径（螺纹配合）"
    ),
    # F2: Bottle 颈外径定 → Wand 螺纹峰径锁定
    CrossComponentDerived(
        source_component="bottle",
        source_param="neck_od_mm",
        target_component="wand",
        target_param="thread.crest_dia_mm",
        compute_range=lambda v, p: (v - 0.5, v + 0.5),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="刷杆螺纹峰径 = 瓶颈外径（螺纹配合）"
    ),

    # F3: Wand 螺距定 → Bottle 螺距锁定
    CrossComponentDerived(
        source_component="wand",
        source_param="thread.pitch_mm",
        target_component="bottle",
        target_param="thread.pitch_mm",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="瓶身螺距 = 刷杆螺距（必须一致）"
    ),
    # F4: Bottle 螺距定 → Wand 螺距锁定
    CrossComponentDerived(
        source_component="bottle",
        source_param="thread.pitch_mm",
        target_component="wand",
        target_param="thread.pitch_mm",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="刷杆螺距 = 瓶身螺距（必须一致）"
    ),

    # F5/F6: 圈数互锁
    CrossComponentDerived(
        source_component="wand",
        source_param="thread.turns",
        target_component="bottle",
        target_param="thread.turns",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="瓶身螺纹圈数 = 刷杆螺纹圈数（必须一致）"
    ),
    CrossComponentDerived(
        source_component="bottle",
        source_param="thread.turns",
        target_component="wand",
        target_param="thread.turns",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="刷杆螺纹圈数 = 瓶身螺纹圈数（必须一致）"
    ),

    # F7/F8: 牙深互锁
    CrossComponentDerived(
        source_component="wand",
        source_param="thread.depth_mm",
        target_component="bottle",
        target_param="thread.depth_mm",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="瓶身牙深 = 刷杆牙深（必须一致）"
    ),
    CrossComponentDerived(
        source_component="bottle",
        source_param="thread.depth_mm",
        target_component="wand",
        target_param="thread.depth_mm",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="刷杆牙深 = 瓶身牙深（必须一致）"
    ),

    # F9/F10: 导程角互锁
    CrossComponentDerived(
        source_component="wand",
        source_param="thread.lead_angle_deg",
        target_component="bottle",
        target_param="thread.lead_angle_deg",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="瓶身导程角 = 刷杆导程角（必须一致）"
    ),
    CrossComponentDerived(
        source_component="bottle",
        source_param="thread.lead_angle_deg",
        target_component="wand",
        target_param="thread.lead_angle_deg",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="刷杆导程角 = 瓶身导程角（必须一致）"
    ),

    # F11/F12: 分段螺纹互锁（bool 型 → 用 compute_default 传递值）
    CrossComponentDerived(
        source_component="wand",
        source_param="thread.segmented",
        target_component="bottle",
        target_param="thread.segmented",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="瓶身分段螺纹 = 刷杆分段螺纹（必须一致）"
    ),
    CrossComponentDerived(
        source_component="bottle",
        source_param="thread.segmented",
        target_component="wand",
        target_param="thread.segmented",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="刷杆分段螺纹 = 瓶身分段螺纹（必须一致）"
    ),

    # F13/F14: 分段间隔角度互锁
    CrossComponentDerived(
        source_component="wand",
        source_param="thread.gap_angle_deg",
        target_component="bottle",
        target_param="thread.gap_angle_deg",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="瓶身分段角度 = 刷杆分段角度（必须一致）"
    ),
    CrossComponentDerived(
        source_component="bottle",
        source_param="thread.gap_angle_deg",
        target_component="wand",
        target_param="thread.gap_angle_deg",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="刷杆分段角度 = 瓶身分段角度（必须一致）"
    ),

    # ═══════════════════════════════════════════════════════════════════
    # I 组：Bottle ↔ Wand 杆长约束（杆+刷头不戳出瓶底 — 双向 2 条）
    # ═══════════════════════════════════════════════════════════════════

    # I1: Bottle 内深定 → Wand 杆长范围
    # 下限：杆+刷头至少达到瓶身内深的 70%（刷头需探到瓶底附近）
    # 上限：杆+刷头不能戳出瓶底
    # A5 上限已放宽，不再与此规则冲突
    CrossComponentDerived(
        source_component="bottle",
        source_param="inner_depth_mm",
        target_component="wand",
        target_param="stem_length_mm",
        compute_range=lambda v, p: (
            max(20.0, (v - BOTTLE_WAND_BRUSH_LEN - BOTTLE_WAND_CLEARANCE) * 0.7),
            v - BOTTLE_WAND_BRUSH_LEN - BOTTLE_WAND_CLEARANCE),
        compute_default=lambda v, p: round(v - BOTTLE_WAND_BRUSH_LEN - 5.0, 1),
        lock_when_set=False,
        description="杆长需探到瓶底附近（≥70%有效深度），且不戳出瓶底"
    ),
    # I2: Wand 杆长定 → Bottle 内深下限
    # inner_depth 受 bottle.height 制约（QC: inner_depth < height - bottom - 0.5）
    # 上限收紧为 min + 2mm，确保默认 height 能容纳
    CrossComponentDerived(
        source_component="wand",
        source_param="stem_length_mm",
        target_component="bottle",
        target_param="inner_depth_mm",
        compute_range=lambda v, p: (v + BOTTLE_WAND_BRUSH_LEN + BOTTLE_WAND_CLEARANCE,
                                    v + BOTTLE_WAND_BRUSH_LEN + BOTTLE_WAND_CLEARANCE + 2.0),
        compute_default=lambda v, p: round(v + BOTTLE_WAND_BRUSH_LEN + 4.0, 1),
        lock_when_set=False,
        description="瓶身内深 ≥ 杆长 + 刷头长 + 余量"
    ),
    # I3: Wand 杆长定 → Bottle 总高下限（确保瓶身够高容纳内深）
    # height ≥ inner_depth + bottom_thickness + 0.5，而 inner_depth ≥ stem+brush+clearance
    CrossComponentDerived(
        source_component="wand",
        source_param="stem_length_mm",
        target_component="bottle",
        target_param="height_mm",
        compute_range=lambda v, p: (v + BOTTLE_WAND_BRUSH_LEN + BOTTLE_WAND_CLEARANCE + 4.0,
                                    150.0),
        compute_default=lambda v, p: round(v + BOTTLE_WAND_BRUSH_LEN + 8.0, 1),
        lock_when_set=False,
        description="瓶身总高 ≥ 杆长 + 刷头长 + 底厚余量（确保杆能放入）"
    ),

    # ═══════════════════════════════════════════════════════════════════
    # J 组：Bottle ↔ Wiper 高度约束（内塞装入颈部 — 双向 2 条）
    # ═══════════════════════════════════════════════════════════════════

    # J1: Bottle 颈高定 → Wiper 高度上限
    CrossComponentDerived(
        source_component="bottle",
        source_param="neck_height_mm",
        target_component="wiper",
        target_param="height_mm",
        compute_range=lambda v, p: (4.0, v - BOTTLE_WIPER_NECK_GAP),
        compute_default=lambda v, p: round(min(v - BOTTLE_WIPER_NECK_GAP, 12.0), 1),
        lock_when_set=False,
        description="内塞总高 ≤ 瓶颈高 - 1mm（内塞装入颈部）"
    ),
    # J2: Wiper 高度定 → Bottle 颈高下限
    # 颈高下限至少 7.0mm（螺纹安全）
    CrossComponentDerived(
        source_component="wiper",
        source_param="height_mm",
        target_component="bottle",
        target_param="neck_height_mm",
        compute_range=lambda v, p: (max(7.0, v + BOTTLE_WIPER_NECK_GAP), v + 8.0),
        compute_default=lambda v, p: round(v + BOTTLE_WIPER_NECK_GAP, 1),
        lock_when_set=False,
        description="瓶颈高 ≥ 内塞高 + 1mm"
    ),

    # ═══════════════════════════════════════════════════════════════════
    # G 组：（已移除）密封塞改为内腔顶面垫圈，无需约束孔径/杆径
    # ═══════════════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════════════
    # H 组：Finish 规格传播（首个含 finish 的组件锁定其他）
    # ═══════════════════════════════════════════════════════════════════

    # H1-H3: Cap finish → 其他三个组件 finish
    CrossComponentDerived(
        source_component="cap",
        source_param="finish",
        target_component="bottle",
        target_param="finish",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="瓶身口部规格 = 瓶盖口部规格"
    ),
    CrossComponentDerived(
        source_component="cap",
        source_param="finish",
        target_component="wand",
        target_param="finish",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="刷杆口部规格 = 瓶盖口部规格"
    ),
    CrossComponentDerived(
        source_component="cap",
        source_param="finish",
        target_component="wiper",
        target_param="finish",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="内塞口部规格 = 瓶盖口部规格"
    ),
    # H4-H6: Bottle finish → 其他三个组件 finish
    CrossComponentDerived(
        source_component="bottle",
        source_param="finish",
        target_component="cap",
        target_param="finish",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="瓶盖口部规格 = 瓶身口部规格"
    ),
    CrossComponentDerived(
        source_component="bottle",
        source_param="finish",
        target_component="wand",
        target_param="finish",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="刷杆口部规格 = 瓶身口部规格"
    ),
    CrossComponentDerived(
        source_component="bottle",
        source_param="finish",
        target_component="wiper",
        target_param="finish",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="内塞口部规格 = 瓶身口部规格"
    ),
    # H7-H9: Wand finish → 其他
    CrossComponentDerived(
        source_component="wand",
        source_param="finish",
        target_component="cap",
        target_param="finish",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="瓶盖口部规格 = 刷杆口部规格"
    ),
    CrossComponentDerived(
        source_component="wand",
        source_param="finish",
        target_component="bottle",
        target_param="finish",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="瓶身口部规格 = 刷杆口部规格"
    ),
    CrossComponentDerived(
        source_component="wand",
        source_param="finish",
        target_component="wiper",
        target_param="finish",
        compute_range=lambda v, p: (v, v),
        compute_default=lambda v, p: v,
        lock_when_set=True,
        description="内塞口部规格 = 刷杆口部规格"
    ),
]


_cross_rules_registered = False


def register_cross_component_rules() -> None:
    """注册跨组件派生规则到状态管理器"""
    global _cross_rules_registered
    if _cross_rules_registered:
        return
    state_mgr = get_state_manager()
    state_mgr.register_cross_rules(CROSS_COMPONENT_RULES)
    _cross_rules_registered = True


# 模块加载时自动注册
register_lip_gloss_derived_rules()
register_cross_component_rules()
