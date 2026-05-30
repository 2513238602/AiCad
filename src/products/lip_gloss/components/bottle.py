# -*- coding: utf-8 -*-
"""
瓶身组件（Bottle Component）

参数设计原则：
1. 核心参数（用户指定）vs 派生参数（自动计算）
2. 容量由尺寸自动计算（用户选择的方案B）
3. 派生参数有动态范围，跟随核心参数变化

参数分类：
- 核心参数：总高、外径、形状、颈径等（用户自由指定）
- 派生参数：内深、壁厚、肩高、容量（由核心参数自动计算）
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.interpreter import Interpreter, Rule
from core.modeler import Modeler
from core.param_system import ParamDef
from products.lip_gloss.derived_params import get_derived_rule
from products.lip_gloss.drawings.bottle_sheet import export_bottle_sheet


# ═══════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════

def _ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def _now_tag() -> str:
    return time.strftime("%Y-%m-%d_%H%M%S", time.localtime())


def _json_write(p: Path, obj: Any) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class BottleComponent:
    """
    唇釉瓶瓶身组件：
    - schema：完整参数族（整体/口部/肩部/容量/底部/配合）
    - rules：硬约束（壁厚、容量、几何一致性等）
    - generate：strict normalize -> modeler.build_bottle -> export step/svg
    """

    # ---------------- schema ----------------
    def schema(self) -> Dict[str, Any]:
        return {
            "id": "bottle",
            "name": "瓶身（唇釉容器）",
            "style_presets": self._style_presets(),
            "params": [self._p(p) for p in self._param_defs()],
        }

    def _p(self, p: ParamDef) -> Dict[str, Any]:
        """将 ParamDef 转换为前端 JSON 格式"""
        out = {
            "k": p.k,
            "name": p.name,
            "unit": p.unit,
            "default": p.default,
            "type": p.type,
            "is_core": p.is_core,
            "group": p.group,
        }
        if p.min is not None:
            out["min"] = p.min
        if p.max is not None:
            out["max"] = p.max
        if p.step is not None:
            out["step"] = p.step
        if p.choices is not None:
            out["choices"] = p.choices
        if p.required:
            out["required"] = True
        if p.readonly:
            out["readonly"] = True

        # 派生规则信息
        if p.derived_rule is not None:
            out["derived_from"] = p.derived_rule.master_param
            out["derived_desc"] = p.derived_rule.description
            out["derived_type"] = p.k

        return out

    def _param_defs(self) -> List[ParamDef]:
        """
        参数定义 - 核心参数 vs 派生参数

        核心参数（is_core=True）：用户自由指定
        派生参数（is_core=False）：由核心参数自动计算
        """
        return [
            # ═══════════════════════════════════════════════════════════════
            # A. 核心参数 - 整体尺寸（用户指定）
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="height_mm", name="总高 H", unit="mm", type="float",
                default=70.0, min=15.0, max=150.0, step=0.1,
                required=True, is_core=True, group="整体"
            ),
            ParamDef(
                k="body_od_mm", name="瓶身外径 ⌀OD", unit="mm", type="float",
                default=24.0, min=12.0, max=45.0, step=0.1,
                required=True, is_core=True, group="整体"
            ),
            ParamDef(
                k="shape", name="瓶身轮廓", type="enum",
                default="cyl", choices=["cyl", "taper"],
                required=True, is_core=True, group="整体"
            ),
            ParamDef(
                k="taper_deg", name="锥度角", unit="deg", type="float",
                default=0.0, min=-5.0, max=8.0, step=0.1,
                is_core=True, group="整体"
            ),
            ParamDef(
                k="cross_section", name="截面形状", type="enum",
                default="round", choices=["round", "square", "triangle", "hexagon", "octagon"],
                is_core=True, group="整体"
            ),
            ParamDef(
                k="corner_radius_mm", name="方形圆角", unit="mm", type="float",
                default=3.0, min=0.5, max=10.0, step=0.1,
                is_core=True, group="整体"
            ),
            ParamDef(
                k="profile_mode", name="外轮廓模式", type="enum",
                default="classic", choices=["classic", "spline"],
                is_core=True, group="整体"
            ),
            ParamDef(
                k="profile_points_json", name="轮廓控制点 (JSON)", type="str",
                default="[]", is_core=True, group="整体"
            ),
            ParamDef(
                k="profile_symmetry", name="轮廓对称模式", type="enum",
                default="symmetric", choices=["symmetric", "asymmetric"],
                is_core=True, group="整体"
            ),
            ParamDef(
                k="profile_b_points_json", name="B轮廓控制点 (JSON)", type="str",
                default="[]", is_core=True, group="整体"
            ),

            # ═══════════════════════════════════════════════════════════════
            # B. 核心参数 - 口部/颈部
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="neck_od_mm", name="口外径（颈外径）", unit="mm", type="float",
                default=18.0, min=10.0, max=32.0, step=0.1,
                required=True, is_core=True, group="口部"
            ),
            ParamDef(
                k="neck_height_mm", name="颈高", unit="mm", type="float",
                default=10.0, min=4.0, max=25.0, step=0.1,
                required=True, is_core=True, group="口部"
            ),
            ParamDef(
                k="lip_thickness_mm", name="唇口厚", unit="mm", type="float",
                default=1.0, min=0.5, max=2.5, step=0.05,
                required=True, is_core=True, group="口部"
            ),

            # 螺纹参数（核心）
            ParamDef(
                k="thread.enabled", name="外螺纹-启用", type="bool",
                default=True, is_core=True, group="螺纹"
            ),
            ParamDef(
                k="thread.pitch_mm", name="螺距 P", unit="mm", type="float",
                default=2.7, min=1.5, max=4.0, step=0.1,
                is_core=True, group="螺纹"
            ),
            ParamDef(
                k="thread.turns", name="圈数 N", type="int",
                default=2, min=1, max=5, step=1,
                is_core=True, group="螺纹"
            ),
            ParamDef(
                k="thread.depth_mm", name="牙深", unit="mm", type="float",
                default=0.5, min=0.2, max=1.5, step=0.05,
                is_core=True, group="螺纹"
            ),
            ParamDef(
                k="thread.lead_angle_deg", name="导程角", unit="deg", type="float",
                default=3.0, min=0.0, max=15.0, step=0.5,
                is_core=True, group="螺纹"
            ),
            ParamDef(
                k="thread.segmented", name="分段螺纹", type="bool",
                default=False, is_core=True, group="螺纹"
            ),
            ParamDef(
                k="thread.gap_angle_deg", name="分段间隔角度", unit="deg", type="float",
                default=20.0, min=5.0, max=60.0, step=1.0,
                is_core=True, group="螺纹"
            ),

            # ═══════════════════════════════════════════════════════════════
            # C. 派生参数 - 肩部（自动计算）
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="shoulder_height_mm", name="肩高", unit="mm", type="float",
                default=10.0, min=2.0, max=30.0, step=0.1,
                required=True, is_core=False, group="肩部",
                derived_rule=get_derived_rule("bottle", "shoulder_height_mm")
            ),
            ParamDef(
                k="shoulder_style", name="肩部形态", type="enum",
                default="round", choices=["round", "angular", "sloped"],
                is_core=True, group="肩部"
            ),
            ParamDef(
                k="shoulder_fillet_mm", name="肩部圆角 R", unit="mm", type="float",
                default=3.0, min=0.0, max=15.0, step=0.1,
                is_core=True, group="肩部"
            ),

            # ═══════════════════════════════════════════════════════════════
            # D. 派生参数 - 容量与内腔（自动计算）
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="capacity_ml", name="内容量（计算值）", unit="ml", type="float",
                default=5.0, min=2.0, max=15.0, step=0.1,
                required=True, is_core=False, group="容量", readonly=True,
                derived_rule=get_derived_rule("bottle", "capacity_ml")
            ),
            ParamDef(
                k="full_capacity_ml", name="满口容量", unit="ml", type="float",
                default=6.0, min=2.5, max=18.0, step=0.1,
                is_core=False, group="容量", readonly=True,
                derived_rule=get_derived_rule("bottle", "full_capacity_ml")
            ),
            ParamDef(
                k="inner_depth_mm", name="内深", unit="mm", type="float",
                default=55.0, min=10.0, max=130.0, step=0.1,
                required=True, is_core=False, group="容量",
                derived_rule=get_derived_rule("bottle", "inner_depth_mm")
            ),
            ParamDef(
                k="wall_thickness_mm", name="壁厚 t", unit="mm", type="float",
                default=1.2, min=0.8, max=3.0, step=0.1,
                required=True, is_core=False, group="容量",
                derived_rule=get_derived_rule("bottle", "wall_thickness_mm")
            ),
            ParamDef(
                k="bottom_thickness_mm", name="底厚", unit="mm", type="float",
                default=2.0, min=1.0, max=8.0, step=0.1,
                required=True, is_core=True, group="底部"
            ),

            # ═══════════════════════════════════════════════════════════════
            # E. 核心参数 - 底部
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="bottom_style", name="底部形态", type="enum",
                default="flat", choices=["flat", "concave", "convex"],
                is_core=True, group="底部"
            ),
            ParamDef(
                k="bottom_concave_mm", name="底部内凹深度", unit="mm", type="float",
                default=1.0, min=0.0, max=5.0, step=0.1,
                is_core=True, group="底部"
            ),
            ParamDef(
                k="bottom_fillet_mm", name="底部外圆角", unit="mm", type="float",
                default=1.5, min=0.0, max=8.0, step=0.1,
                is_core=True, group="底部"
            ),

            # ═══════════════════════════════════════════════════════════════
            # G. 核心参数 - 装饰特征
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="collar_enabled", name="肩部装饰环", type="bool",
                default=False, is_core=True, group="装饰"
            ),
            ParamDef(
                k="collar_height_mm", name="装饰环高度", unit="mm", type="float",
                default=4.0, min=1.5, max=12.0, step=0.5,
                is_core=True, group="装饰"
            ),
            ParamDef(
                k="collar_rib_count", name="装饰环筋数", type="int",
                default=30, min=0, max=60, step=1,
                is_core=True, group="装饰"
            ),
            ParamDef(
                k="collar_rib_depth_mm", name="装饰环筋深", unit="mm", type="float",
                default=0.3, min=0.05, max=1.0, step=0.05,
                is_core=True, group="装饰"
            ),
            ParamDef(
                k="collar_width_excess_mm", name="装饰环外凸量", unit="mm", type="float",
                default=0.0, min=0.0, max=3.0, step=0.1,
                is_core=True, group="装饰"
            ),
            ParamDef(
                k="base_ring_enabled", name="底座环", type="bool",
                default=False, is_core=True, group="装饰"
            ),
            ParamDef(
                k="base_ring_height_mm", name="底座环高度", unit="mm", type="float",
                default=2.0, min=0.5, max=8.0, step=0.5,
                is_core=True, group="装饰"
            ),
            ParamDef(
                k="base_ring_width_excess_mm", name="底座环宽余量", unit="mm", type="float",
                default=0.5, min=0.2, max=3.0, step=0.1,
                is_core=True, group="装饰"
            ),

            # ═══════════════════════════════════════════════════════════════
            # F. 配合参数
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="finish", name="口部规格（标注）", type="str",
                default="18-415", is_core=True, group="配合"
            ),
            ParamDef(
                k="cap_clearance_mm", name="瓶盖配合间隙", unit="mm", type="float",
                default=0.2, min=0.05, max=0.5, step=0.05,
                is_core=True, group="配合"
            ),
        ]

    def _style_presets(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "bottle_standard_5ml",
                "name": "标准唇釉瓶 5ml",
                "desc": "经典直筒造型，18-415 口部，适合常规唇釉产品",
                "params": {
                    # 整体（body_od 与瓶盖 outer_od 一致）
                    "height_mm": 70.0,
                    "body_od_mm": 24.0,
                    "shape": "cyl",
                    "taper_deg": 0.0,

                    # 口部
                    "neck_od_mm": 18.0,
                    "neck_height_mm": 10.0,
                    "lip_thickness_mm": 1.0,

                    # 螺纹（bottom_dia 自动计算 = neck_od - 2*depth）
                    "thread.enabled": True,
                    "thread.pitch_mm": 2.7,
                    "thread.turns": 2,
                    "thread.depth_mm": 0.5,
                    "thread.lead_angle_deg": 3.0,
                    "thread.segmented": False,
                    "thread.gap_angle_deg": 20.0,

                    # 肩部（适配 body_od 24 到 neck_od 18 的过渡）
                    "shoulder_height_mm": 10.0,
                    "shoulder_style": "round",
                    "shoulder_fillet_mm": 3.0,

                    # 容量
                    "capacity_ml": 5.0,
                    "full_capacity_ml": 6.0,
                    "inner_depth_mm": 55.0,
                    "wall_thickness_mm": 1.2,
                    "bottom_thickness_mm": 2.0,

                    # 底部
                    "bottom_style": "flat",
                    "bottom_concave_mm": 0.0,
                    "bottom_fillet_mm": 1.5,

                    # 配合
                    "finish": "18-415",
                    "cap_clearance_mm": 0.2,
                },
            },
            {
                "id": "bottle_taper_6ml",
                "name": "锥形唇釉瓶 6ml",
                "desc": "微锥度造型，视觉更纤细",
                "params": {
                    # 整体（body_od 与瓶盖 outer_od 一致）
                    "height_mm": 80.0,
                    "body_od_mm": 24.0,
                    "shape": "taper",
                    "taper_deg": 2.0,

                    "neck_od_mm": 18.0,
                    "neck_height_mm": 10.0,
                    "lip_thickness_mm": 1.0,

                    "thread.enabled": True,
                    "thread.pitch_mm": 2.7,
                    "thread.turns": 2,
                    "thread.depth_mm": 0.5,
                    "thread.lead_angle_deg": 3.0,
                    "thread.segmented": False,
                    "thread.gap_angle_deg": 20.0,

                    # 肩部（适配 body_od 24 到 neck_od 18 的过渡）
                    "shoulder_height_mm": 10.0,
                    "shoulder_style": "sloped",
                    "shoulder_fillet_mm": 2.0,

                    "capacity_ml": 6.0,
                    "full_capacity_ml": 7.5,
                    "inner_depth_mm": 62.0,
                    "wall_thickness_mm": 1.2,
                    "bottom_thickness_mm": 2.5,

                    "bottom_style": "flat",
                    "bottom_concave_mm": 0.0,
                    "bottom_fillet_mm": 2.0,

                    "finish": "18-415",
                    "cap_clearance_mm": 0.2,
                },
            },
            {
                "id": "bottle_spline_s_curve",
                "name": "S 形曲线瓶 5ml",
                "desc": "spline 曲线外形，微鼓肚 S 形造型，时尚设计感",
                "params": {
                    "height_mm": 70.0,
                    "body_od_mm": 24.0,
                    "shape": "cyl",
                    "taper_deg": 0.5,
                    "profile_mode": "spline",
                    "profile_points_json": json.dumps([
                        [12.0, 0.0],
                        [12.3, 10.0],
                        [12.5, 25.0],
                        [12.2, 40.0],
                        [10.5, 52.0],
                        [9.0, 60.0],
                    ]),

                    "neck_od_mm": 18.0,
                    "neck_height_mm": 10.0,
                    "lip_thickness_mm": 1.0,

                    "thread.enabled": True,
                    "thread.pitch_mm": 2.7,
                    "thread.turns": 2,
                    "thread.depth_mm": 0.5,
                    "thread.lead_angle_deg": 3.0,
                    "thread.segmented": False,
                    "thread.gap_angle_deg": 20.0,

                    "shoulder_height_mm": 10.0,
                    "shoulder_style": "round",
                    "shoulder_fillet_mm": 3.0,

                    "capacity_ml": 5.0,
                    "full_capacity_ml": 6.0,
                    "inner_depth_mm": 55.0,
                    "wall_thickness_mm": 1.2,
                    "bottom_thickness_mm": 2.0,

                    "bottom_style": "flat",
                    "bottom_concave_mm": 0.0,
                    "bottom_fillet_mm": 1.5,

                    "finish": "18-415",
                    "cap_clearance_mm": 0.2,
                },
            },
            {
                "id": "bottle_spline_round_shoulder",
                "name": "直筒圆肩瓶 5ml",
                "desc": "spline 曲线外形，笔直瓶身 + 柔和圆肩过渡",
                "params": {
                    "height_mm": 70.0,
                    "body_od_mm": 24.0,
                    "shape": "cyl",
                    "taper_deg": 0.5,
                    "profile_mode": "spline",
                    "profile_points_json": json.dumps([
                        [12.0, 0.0],
                        [12.0, 15.0],
                        [11.9, 35.0],
                        [11.5, 48.0],
                        [10.0, 55.0],
                        [9.0, 60.0],
                    ]),

                    "neck_od_mm": 18.0,
                    "neck_height_mm": 10.0,
                    "lip_thickness_mm": 1.0,

                    "thread.enabled": True,
                    "thread.pitch_mm": 2.7,
                    "thread.turns": 2,
                    "thread.depth_mm": 0.5,
                    "thread.lead_angle_deg": 3.0,
                    "thread.segmented": False,
                    "thread.gap_angle_deg": 20.0,

                    "shoulder_height_mm": 10.0,
                    "shoulder_style": "round",
                    "shoulder_fillet_mm": 3.0,

                    "capacity_ml": 5.0,
                    "full_capacity_ml": 6.0,
                    "inner_depth_mm": 55.0,
                    "wall_thickness_mm": 1.2,
                    "bottom_thickness_mm": 2.0,

                    "bottom_style": "flat",
                    "bottom_concave_mm": 0.0,
                    "bottom_fillet_mm": 1.5,

                    "finish": "18-415",
                    "cap_clearance_mm": 0.2,
                },
            },
        ]

    # ---------------- rules (hard fail) ----------------
    def _rules(self) -> List[Rule]:
        TOL_WALL = 0.15
        TOL_CAPACITY = 0.20  # 20% 容量公差

        def _wall_consistency(p: Dict[str, Any]) -> bool:
            """壁厚一致性：body_od - 2*wall 应为合理内径"""
            body_od = float(p["body_od_mm"])
            wall = float(p["wall_thickness_mm"])
            inner_d = body_od - 2 * wall
            return inner_d >= 6.0  # 内径至少 6mm

        def _capacity_check(p: Dict[str, Any]) -> bool:
            """容量合理性：计算容量 vs 标称容量，误差 <=20%"""
            body_od = float(p["body_od_mm"])
            wall = float(p["wall_thickness_mm"])
            inner_depth = float(p["inner_depth_mm"])
            capacity_ml = float(p["capacity_ml"])

            inner_d = body_od - 2 * wall
            inner_r = inner_d / 2.0
            # 简化计算：圆柱体积（忽略肩部锥度）
            v_calc = math.pi * inner_r * inner_r * inner_depth / 1000.0  # mm³ -> ml

            if capacity_ml <= 0:
                return False
            # 计算容量应大于等于标称容量（允许 20% 误差）
            return v_calc >= capacity_ml * (1 - TOL_CAPACITY)

        def _geometry_consistency(p: Dict[str, Any]) -> bool:
            """几何一致性：总高 >= 颈高 + 肩高 + 底厚 + 余量"""
            H = float(p["height_mm"])
            neck_h = float(p["neck_height_mm"])
            shoulder_h = float(p["shoulder_height_mm"])
            bottom_t = float(p["bottom_thickness_mm"])
            # 瓶身段至少 5mm
            return H >= (neck_h + shoulder_h + bottom_t + 5.0)

        def _neck_spec_match(p: Dict[str, Any]) -> bool:
            """口径与 finish 标注匹配"""
            neck_od = float(p["neck_od_mm"])
            finish = str(p.get("finish", "18-415"))
            # 从 finish 提取口径（如 "18-415" -> 18）
            try:
                spec_od = float(finish.split("-")[0])
            except (ValueError, IndexError):
                return True  # 无法解析时跳过
            return abs(neck_od - spec_od) <= 1.0  # 允许 1mm 误差

        def _thread_safe(p: Dict[str, Any]) -> bool:
            """螺纹安全性"""
            thr = p.get("thread", {}) or {}
            if not bool(thr.get("enabled", False)):
                return True
            pitch = float(thr.get("pitch_mm", 2.7))
            turns = int(thr.get("turns", 2))
            depth = float(thr.get("depth_mm", 0.5))
            neck_h = float(p["neck_height_mm"])
            lip_t = float(p["lip_thickness_mm"])

            # 螺纹长度不能超出颈部
            thread_len = pitch * turns
            if thread_len > (neck_h - 1.0):
                return False
            # 牙深不能超过唇口厚
            if depth > (lip_t - 0.2):
                return False
            return True

        def _inner_depth_valid(p: Dict[str, Any]) -> bool:
            """内深合理性"""
            H = float(p["height_mm"])
            inner_depth = float(p["inner_depth_mm"])
            bottom_t = float(p["bottom_thickness_mm"])
            neck_h = float(p["neck_height_mm"])
            # 内深不能超过 总高 - 底厚
            if inner_depth >= (H - bottom_t - 0.5):
                return False
            # 内深至少深入瓶身 5mm（超过颈高）
            if inner_depth < (neck_h + 5.0):
                return False
            return True

        def _full_capacity_valid(p: Dict[str, Any]) -> bool:
            """满口容量 >= 标称容量"""
            full_cap = float(p.get("full_capacity_ml", 0.0))
            capacity = float(p["capacity_ml"])
            return full_cap >= capacity

        return [
            Rule("wall_consistency", "hard", "壁厚不合理：内径过小（< 6mm）", _wall_consistency),
            Rule("capacity_check", "hard", "容量不合理：计算容量与标称容量差异过大", _capacity_check),
            Rule("geometry_consistency", "hard", "几何不一致：总高不足以容纳颈+肩+底", _geometry_consistency),
            Rule("neck_spec_match", "hard", "口径与 finish 标注不匹配", _neck_spec_match),
            Rule("thread_safe", "hard", "螺纹参数不安全：长度超出颈部或牙深超过唇厚", _thread_safe),
            Rule("inner_depth_valid", "hard", "内深不合理：超出可用空间或过浅", _inner_depth_valid),
            Rule("full_capacity_valid", "hard", "满口容量小于标称容量", _full_capacity_valid),
        ]

    # ---------------- generate ----------------
    def generate(
        self,
        preset_id: Optional[str] = None,
        user_params: Optional[Dict[str, Any]] = None,
        outroot: str = "artifacts/webui",
        *,
        params: Optional[Dict[str, Any]] = None,  # legacy
        out_root: Optional[str] = None,  # legacy
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        if out_root is not None:
            outroot = out_root
        if params is not None and user_params is None:
            user_params = params
        user_params = user_params or {}

        presets = {p["id"]: p for p in self._style_presets()}
        preset = presets.get(preset_id) if preset_id else None
        preset_params = (preset or {}).get("params", {})

        interp = Interpreter()
        param_defs_json = [self._p(p) for p in self._param_defs()]
        p_norm, flat, qc = interp.normalize_strict(
            param_defs_json,
            preset_params=preset_params,
            user_params=user_params,
            rules=self._rules(),
            allow_unknown_keys=False,
        )

        run_dir = _ensure_dir(Path(outroot) / f"{_now_tag()}__bottle__{(preset_id or 'custom')}")
        drawings_dir = _ensure_dir(run_dir / "drawings")
        step_path = run_dir / "bottle.step"
        stl_path = run_dir / "bottle.stl"
        svg_path = drawings_dir / "bottle_sheet.svg"

        _json_write(run_dir / "params.json", p_norm)
        _json_write(run_dir / "qc.json", qc)

        out = {
            "ok": bool(qc["ok"]),
            "run_dir": str(run_dir),
            "step": None,
            "stl": None,
            "svg": None,
            "qc": qc,
            "error": None,
        }

        if not qc["ok"]:
            _fails = [c["msg"] for c in qc.get("checks", []) if not c["ok"] and c.get("severity") == "hard"]
            out["error"] = "硬约束失败：" + "；".join(_fails) if _fails else "参数不满足硬约束（strict），已阻止导出。"
            return out

        modeler = Modeler()
        meta: Dict[str, Any] = {}
        try:
            solid = modeler.build("bottle", p_norm, meta=meta)
            out["solid"] = solid
            modeler.export_step(solid, str(step_path))
            out["step"] = str(step_path)
            # 导出 STL 用于 Web 3D 预览
            try:
                import cadquery as cq

                cq.exporters.export(solid, str(stl_path), exportType="STL",
                                    tolerance=0.01, angularTolerance=0.05)
                out["stl"] = str(stl_path)
            except Exception:
                out["stl"] = None
        except Exception as e:
            out["ok"] = False
            out["error"] = f"建模/STEP 导出失败：{e}"
            out["qc"].setdefault("modeler_meta", meta)
            return out

        try:
            export_bottle_sheet(p_norm, svg_path, solid=solid)
            out["svg"] = str(svg_path)
        except Exception as e:
            out["ok"] = False
            out["error"] = f"工程图导出失败：{e}"
            out["svg"] = None

        out["qc"].setdefault("modeler_meta", meta)
        return out
