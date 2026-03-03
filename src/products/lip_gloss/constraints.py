# -*- coding: utf-8 -*-
"""
唇釉瓶配合约束定义（Lip Gloss Fit Constraints）

本模块定义唇釉瓶各组件之间的配合约束。

组件：
- cap (瓶盖)
- bottle (瓶身)
- wand (刷杆)
- wiper (内塞)

优先级规则：
- 瓶盖(cap)约束优先级最高(20)，因为它决定整体外观
- 瓶身(bottle)约束优先级次高(15)
- 刷杆(wand)约束优先级中等(10)
- 内塞(wiper)约束优先级最低(5)

作者：AiCad
日期：2024
"""
from __future__ import annotations

from typing import Any, Dict, List

from core.fit_constraints import (
    FitConstraint,
    InternalConstraint,
    LinkedParam,
    get_registry,
)


# ═══════════════════════════════════════════════════════════════════════════
# 常量：配合间隙
# ═══════════════════════════════════════════════════════════════════════════

GAP_CAP_WAND = 1.0           # 瓶盖内径 - 刷杆外径间隙
GAP_CAP_WAND_DEPTH = 4.0     # 瓶盖内腔深 - 刷杆盖高间隙
GAP_SEAL_RING = 5.5          # 刷杆外径 - 气密环外径间隙
GAP_CAP_NECK = 4.0           # 瓶盖内径 - 瓶身颈外径间隙（给刷杆螺纹留空间）
MIN_SHOULDER = 8.0           # 最小肩高
MIN_WALL = 0.8               # 最小壁厚


# ═══════════════════════════════════════════════════════════════════════════
# 优先级常量
# ═══════════════════════════════════════════════════════════════════════════

PRIORITY_CAP = 20      # 瓶盖约束优先级最高
PRIORITY_BOTTLE = 15   # 瓶身约束优先级次高
PRIORITY_WAND = 10     # 刷杆约束优先级中等
PRIORITY_WIPER = 5     # 内塞约束优先级最低


# ═══════════════════════════════════════════════════════════════════════════
# 配合约束定义
# ═══════════════════════════════════════════════════════════════════════════

LIP_GLOSS_FIT_CONSTRAINTS: List[FitConstraint] = [
    # ─────────────────────────────────────────────────────────────────────
    # Cap → Wand 约束（优先级 20）
    # 瓶盖生成后，刷杆必须能装入瓶盖内腔
    # ─────────────────────────────────────────────────────────────────────
    FitConstraint(
        source_component="cap",
        target_component="wand",
        source_param="inner_id_mm",
        target_param="outer_od_mm",
        offset=-GAP_CAP_WAND,
        priority=PRIORITY_CAP,
        linked_params=[
            LinkedParam(
                param="seal_ring.od_mm",
                compute=lambda src, p: src - GAP_CAP_WAND - GAP_SEAL_RING,
                description="气密环外径随刷杆外径联动"
            ),
        ],
        description="刷杆外径适配瓶盖内径"
    ),
    FitConstraint(
        source_component="cap",
        target_component="wand",
        source_param="cavity_depth_mm",
        target_param="cap_height_mm",
        offset=-GAP_CAP_WAND_DEPTH,
        priority=PRIORITY_CAP,
        description="刷杆盖高适配瓶盖内腔深"
    ),

    # ─────────────────────────────────────────────────────────────────────
    # Cap → Bottle 约束（优先级 20）
    # 瓶盖生成后，瓶身外径和颈部需要适配
    # 关键：瓶身外径 = 瓶盖外径（平整外观）
    # ─────────────────────────────────────────────────────────────────────
    FitConstraint(
        source_component="cap",
        target_component="bottle",
        source_param="outer_od_mm",
        target_param="body_od_mm",
        offset=0.0,
        priority=PRIORITY_CAP,
        linked_params=[
            LinkedParam(
                param="shoulder_height_mm",
                compute=lambda src, p: max(MIN_SHOULDER, (src - 18.0) * 0.5 + 8.0),
                description="肩高随瓶身外径联动"
            ),
        ],
        description="瓶身外径匹配瓶盖外径（平整外观）"
    ),
    FitConstraint(
        source_component="cap",
        target_component="bottle",
        source_param="inner_id_mm",
        target_param="neck_od_mm",
        offset=-GAP_CAP_NECK,
        priority=PRIORITY_CAP,
        description="颈外径适配瓶盖内径（留刷杆螺纹空间）"
    ),

    # ─────────────────────────────────────────────────────────────────────
    # Wand → Cap 约束（优先级 10）
    # 刷杆先生成，瓶盖必须能容纳刷杆
    # ─────────────────────────────────────────────────────────────────────
    FitConstraint(
        source_component="wand",
        target_component="cap",
        source_param="outer_od_mm",
        target_param="inner_id_mm",
        offset=GAP_CAP_WAND,
        priority=PRIORITY_WAND,
        description="瓶盖内径容纳刷杆外径"
    ),
    FitConstraint(
        source_component="wand",
        target_component="cap",
        source_param="cap_height_mm",
        target_param="cavity_depth_mm",
        offset=GAP_CAP_WAND_DEPTH,
        priority=PRIORITY_WAND,
        linked_params=[
            LinkedParam(
                param="height_mm",
                compute=lambda src, p: src + GAP_CAP_WAND_DEPTH + 1.5,
                description="瓶盖总高随内腔深联动"
            ),
        ],
        description="瓶盖内腔容纳刷杆盖子"
    ),

    # ─────────────────────────────────────────────────────────────────────
    # Wand → Bottle 约束（优先级 10）
    # 刷杆螺纹需要与瓶身螺纹配合
    # 注意：不约束 body_od_mm，因为 cap→bottle 已经约束了（优先级更高）
    # ─────────────────────────────────────────────────────────────────────
    FitConstraint(
        source_component="wand",
        target_component="bottle",
        source_param="thread.crest_dia_mm",
        target_param="neck_od_mm",
        offset=0.0,
        priority=PRIORITY_WAND,
        description="瓶身颈径匹配刷杆螺纹"
    ),
    FitConstraint(
        source_component="wand",
        target_component="bottle",
        source_param="thread.pitch_mm",
        target_param="thread.pitch_mm",
        offset=0.0,
        priority=PRIORITY_WAND,
        description="瓶身螺距匹配刷杆螺距"
    ),

    # ─────────────────────────────────────────────────────────────────────
    # Bottle → Cap 约束（优先级 15）
    # 瓶身生成后，瓶盖需要适配瓶身
    # ─────────────────────────────────────────────────────────────────────
    FitConstraint(
        source_component="bottle",
        target_component="cap",
        source_param="body_od_mm",
        target_param="outer_od_mm",
        offset=0.0,
        priority=PRIORITY_BOTTLE,
        linked_params=[
            LinkedParam(
                param="inner_id_mm",
                compute=lambda src, p: src - 2 * MIN_WALL,
                description="瓶盖内径随外径联动（保持0.8mm壁厚）"
            ),
            LinkedParam(
                param="cavity_depth_mm",
                compute=lambda src, p: p.get("height_mm", 25.0) - 1.5,
                description="内腔深度最大化"
            ),
        ],
        description="瓶盖外径匹配瓶身外径"
    ),

    # ─────────────────────────────────────────────────────────────────────
    # Bottle → Wand 约束（优先级 15）
    # 瓶身生成后，刷杆螺纹需要匹配
    # ─────────────────────────────────────────────────────────────────────
    FitConstraint(
        source_component="bottle",
        target_component="wand",
        source_param="neck_od_mm",
        target_param="thread.crest_dia_mm",
        offset=0.0,
        priority=PRIORITY_BOTTLE,
        description="刷杆螺纹匹配瓶身颈径"
    ),
    FitConstraint(
        source_component="bottle",
        target_component="wand",
        source_param="thread.pitch_mm",
        target_param="thread.pitch_mm",
        offset=0.0,
        priority=PRIORITY_BOTTLE,
        description="刷杆螺距匹配瓶身螺距"
    ),

    # ─────────────────────────────────────────────────────────────────────
    # Wiper 相关约束（优先级 5）
    # ─────────────────────────────────────────────────────────────────────
    FitConstraint(
        source_component="bottle",
        target_component="wiper",
        source_param="neck_od_mm",
        target_param="flange_od_mm",
        offset=-1.0,
        priority=PRIORITY_WIPER,
        description="内塞凸环适配瓶颈外径"
    ),
    FitConstraint(
        source_component="wiper",
        target_component="wand",
        source_param="orifice_mm",
        target_param="stem_diameter_mm",
        offset=-2.0,
        priority=PRIORITY_WIPER,
        description="杆径适配内塞孔口"
    ),
    # 注：密封塞已改为内腔顶面垫圈，无需与wiper孔口配合
    FitConstraint(
        source_component="wand",
        target_component="wiper",
        source_param="stem_diameter_mm",
        target_param="orifice_mm",
        offset=2.0,
        priority=PRIORITY_WAND,
        description="内塞孔口适配杆径"
    ),
]


# ═══════════════════════════════════════════════════════════════════════════
# 组件内部约束
# ═══════════════════════════════════════════════════════════════════════════

LIP_GLOSS_INTERNAL_CONSTRAINTS: List[InternalConstraint] = [
    # Cap 内部约束
    InternalConstraint(
        component="cap",
        trigger_param="outer_od_mm",
        adjust_param="inner_id_mm",
        compute=lambda od, p: od - 2 * MIN_WALL,
        description="瓶盖内径随外径调整（壁厚0.8mm）"
    ),
    InternalConstraint(
        component="cap",
        trigger_param="height_mm",
        adjust_param="cavity_depth_mm",
        compute=lambda h, p: h - 1.5,
        description="内腔深度随总高调整（顶厚1.5mm）"
    ),

    # Wand 内部约束
    InternalConstraint(
        component="wand",
        trigger_param="outer_od_mm",
        adjust_param="seal_ring.od_mm",
        compute=lambda od, p: od - GAP_SEAL_RING,
        description="气密环外径随刷杆外径调整"
    ),
    InternalConstraint(
        component="wand",
        trigger_param="thread.crest_dia_mm",
        adjust_param="seal_ring.od_mm",
        compute=lambda crest, p: min(crest - 1.0, p.get("seal_ring", {}).get("od_mm", 17.5)),
        description="气密环不超过螺牙底径"
    ),

    # Bottle 内部约束
    InternalConstraint(
        component="bottle",
        trigger_param="body_od_mm",
        adjust_param="wall_thickness_mm",
        compute=lambda od, p: min(1.5, max(1.0, od * 0.05)),
        description="壁厚随瓶身外径调整"
    ),
]


# ═══════════════════════════════════════════════════════════════════════════
# 注册函数
# ═══════════════════════════════════════════════════════════════════════════

def register_lip_gloss_constraints() -> None:
    """
    注册唇釉瓶的所有配合约束

    调用此函数将约束注册到全局注册表
    """
    registry = get_registry()

    # 避免重复注册
    if registry.is_product_registered("lip_gloss"):
        return

    registry.register_fit_constraints(LIP_GLOSS_FIT_CONSTRAINTS)
    registry.register_internal_constraints(LIP_GLOSS_INTERNAL_CONSTRAINTS)
    registry.register_product("lip_gloss")


# 模块加载时自动注册
register_lip_gloss_constraints()
