# -*- coding: utf-8 -*-
"""
瓶盖组件（Cap Component）- 重构版

参数设计原则：
1. 核心参数（用户指定）vs 派生参数（自动计算）
2. 无内螺纹设计 - 依靠刷杆内螺纹与瓶身外螺纹配合
3. 密封塞与内塞孔口配合
4. 默认值基于 18-415 口部规格标准
5. 内腔尽可能深，壁厚尽可能薄（最小 0.8mm）

参数分类：
- 核心参数：外径、总高、锥度角、顶面形态、防滑纹样式等（用户自由指定）
- 派生参数：内径、内腔深（由核心参数自动计算，动态范围）
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.interpreter import Interpreter, Rule
from core.modeler import Modeler
from core.param_system import ParamDef
from products.lip_gloss.derived_params import get_derived_rule
from products.lip_gloss.drawings.cap_sheet import export_cap_sheet


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


class CapComponent:
    """
    瓶盖组件（重构版）：
    - 精简参数：~20 个核心参数（原 ~35 个）
    - 配合优先：螺纹、内腔、密封塞参数强调与其他组件配合
    - 18-415 标准：默认值基于行业标准
    """

    # ---------------- schema ----------------
    def schema(self) -> Dict[str, Any]:
        return {
            "id": "cap",
            "name": "瓶盖（唇釉/唇彩）",
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

        # 派生规则信息（供前端计算动态范围）
        if p.derived_rule is not None:
            out["derived_from"] = p.derived_rule.master_param
            out["derived_desc"] = p.derived_rule.description
            # 导出计算函数名（前端需要知道如何计算）
            out["derived_type"] = p.k  # 用参数 key 标识派生类型

        return out

    def _param_defs(self) -> List[ParamDef]:
        """
        参数定义 - 核心参数 vs 派生参数

        核心参数（is_core=True）：用户自由指定，系统不修改
        派生参数（is_core=False）：由核心参数自动计算，动态范围

        配合关系（无内螺纹设计）：
        - inner_id_mm >= 刷杆.outer_od_mm（瓶盖套在刷杆外）
        - cavity_depth_mm 尽可能深，只留最薄顶部壁厚
        """
        return [
            # ═══════════════════════════════════════════════════════════════
            # A. 核心参数 - 外形尺寸（用户指定，决定瓶盖外观）
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="outer_od_mm", name="外径 ⌀OD", unit="mm", type="float",
                default=24.0, min=12.0, max=50.0, step=0.1,
                required=True, is_core=True, group="外形"
            ),
            ParamDef(
                k="height_mm", name="总高 H", unit="mm", type="float",
                default=25.0, min=10.0, max=80.0, step=0.1,
                required=True, is_core=True, group="外形"
            ),
            ParamDef(
                k="taper_deg", name="锥度角", unit="deg", type="float",
                default=0.0, min=0.0, max=10.0, step=0.5,
                is_core=True, group="外形"
            ),
            ParamDef(
                k="top_shape", name="顶面形态", type="enum",
                default="flat", choices=["flat", "dome", "pointed"],
                is_core=True, group="外形"
            ),
            ParamDef(
                k="profile_mode", name="外轮廓模式", type="enum",
                default="classic", choices=["classic", "spline"],
                is_core=True, group="外形"
            ),
            ParamDef(
                k="profile_points_json", name="轮廓控制点 (JSON)", type="str",
                default="[]", is_core=True, group="外形"
            ),
            ParamDef(
                k="cross_section", name="截面形状", type="enum",
                default="round", choices=["round", "square", "triangle", "hexagon", "octagon"],
                is_core=True, group="外形"
            ),
            ParamDef(
                k="corner_radius_mm", name="方形圆角", unit="mm", type="float",
                default=3.0, min=0.5, max=10.0, step=0.5,
                is_core=True, group="外形"
            ),

            # ═══════════════════════════════════════════════════════════════
            # B. 派生参数 - 内腔配合（自动计算，动态范围）
            # 壁厚 = (outer_od - inner_id) / 2，最小 0.8mm
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="inner_id_mm", name="内径 ⌀ID（配合刷杆）", unit="mm", type="float",
                default=22.4, min=8.0, max=45.0, step=0.1,
                required=True, is_core=False, group="内腔",
                derived_rule=get_derived_rule("cap", "inner_id_mm")
            ),
            ParamDef(
                k="cavity_depth_mm", name="内腔深", unit="mm", type="float",
                default=23.5, min=5.0, max=70.0, step=0.1,
                required=True, is_core=False, group="内腔",
                derived_rule=get_derived_rule("cap", "cavity_depth_mm")
            ),
            ParamDef(
                k="edge_fillet_mm", name="边缘圆角", unit="mm", type="float",
                default=0.5, min=0.0, max=5.0, step=0.1,
                is_core=True, group="外形"
            ),

            # ═══════════════════════════════════════════════════════════════
            # C. 核心参数 - 外观细节
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="grip.style", name="防滑纹样式", type="enum",
                default="ribs", choices=["none", "ribs", "knurl", "horizontal_grooves", "stripe"],
                is_core=True, group="防滑纹"
            ),
            ParamDef(
                k="grip.count", name="纹理数量", type="int",
                default=24, min=0, max=120, step=1,
                is_core=True, group="防滑纹"
            ),
            ParamDef(
                k="grip.depth_mm", name="纹理深度", unit="mm", type="float",
                default=0.3, min=0.0, max=2.0, step=0.05,
                is_core=True, group="防滑纹"
            ),

            # ═══════════════════════════════════════════════════════════════
            # E. 配合参数
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="finish", name="口部规格（标注）", type="str",
                default="18-415", is_core=True, group="配合"
            ),

            # ═══════════════════════════════════════════════════════════════
            # F. 内置杆子（可选，代替独立 wand 组件）
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="stem.enabled", name="内置杆子", type="bool",
                default=False, is_core=True, group="杆子"
            ),
            ParamDef(
                k="stem.diameter_mm", name="杆径", type="float",
                default=4.5, min=2.0, max=10.0, step=0.25,
                is_core=True, group="杆子"
            ),
            ParamDef(
                k="stem.length_mm", name="杆长", type="float",
                default=50.0, min=20.0, max=150.0, step=1.0,
                is_core=False, group="杆子"
            ),
            ParamDef(
                k="stem.profile", name="杆身轮廓", type="str",
                default="round", is_core=True, group="杆子"
            ),
            ParamDef(
                k="stem.taper_ratio", name="杆锥度比", type="float",
                default=1.0, min=0.6, max=1.0, step=0.05,
                is_core=True, group="杆子"
            ),
            ParamDef(
                k="stem.wall_mm", name="杆壁厚", type="float",
                default=0.8, min=0.0, max=3.0, step=0.1,
                is_core=True, group="杆子"
            ),

            # ---- 内螺纹（stem 启用时使用） ----
            ParamDef(
                k="thread.enabled", name="内螺纹", type="bool",
                default=False, is_core=True, group="螺纹"
            ),
            ParamDef(
                k="thread.crest_dia_mm", name="螺牙峰径", type="float",
                default=18.0, min=10.0, max=28.0, step=0.5,
                is_core=False, group="螺纹"
            ),
            ParamDef(
                k="thread.pitch_mm", name="螺距", type="float",
                default=2.7, min=1.5, max=4.0, step=0.1,
                is_core=True, group="螺纹"
            ),
            ParamDef(
                k="thread.turns", name="圈数", type="int",
                default=2, min=1, max=5,
                is_core=True, group="螺纹"
            ),
            ParamDef(
                k="thread.depth_mm", name="牙深", type="float",
                default=0.75, min=0.2, max=1.5, step=0.05,
                is_core=True, group="螺纹"
            ),
            ParamDef(
                k="thread.lead_angle_deg", name="导程角", type="float",
                default=3.0, min=0.0, max=15.0, step=0.5,
                is_core=True, group="螺纹"
            ),
            ParamDef(
                k="thread.segmented", name="分段螺纹", type="bool",
                default=False, is_core=True, group="螺纹"
            ),
            ParamDef(
                k="thread.gap_angle_deg", name="分段间隔角", type="float",
                default=20.0, min=5.0, max=60.0, step=5.0,
                is_core=True, group="螺纹"
            ),

            # ---- 气密环 ----
            ParamDef(
                k="seal_ring.od_mm", name="气密环外径", type="float",
                default=12.0, min=8.0, max=25.0, step=0.5,
                is_core=False, group="气密环"
            ),
            ParamDef(
                k="seal_ring.height_mm", name="气密环高", type="float",
                default=2.0, min=1.0, max=8.0, step=0.5,
                is_core=True, group="气密环"
            ),
            ParamDef(
                k="seal_ring.style", name="气密环形态", type="str",
                default="flat", is_core=True, group="气密环"
            ),

            # ---- 刷头 ----
            ParamDef(
                k="brush.type", name="刷头类型", type="str",
                default="doe_foot", is_core=True, group="刷头"
            ),
            ParamDef(
                k="brush.length_mm", name="刷长", type="float",
                default=12.0, min=5.0, max=25.0, step=0.5,
                is_core=True, group="刷头"
            ),
            ParamDef(
                k="brush.width_mm", name="刷宽", type="float",
                default=8.0, min=4.0, max=18.0, step=0.5,
                is_core=True, group="刷头"
            ),
            ParamDef(
                k="brush.thickness_mm", name="刷厚", type="float",
                default=3.0, min=2.0, max=10.0, step=0.5,
                is_core=True, group="刷头"
            ),

        ]

    def _style_presets(self) -> List[Dict[str, Any]]:
        """
        预设 - 基于 18-415 标准
        """
        return [
            {
                "id": "cap_18415_standard",
                "name": "标准瓶盖 18-415",
                "desc": "适配18-415瓶口的标准瓶盖，密封塞+竖筋防滑",
                "params": {
                    # A. 外形尺寸（壁厚 = (24 - 22.4) / 2 = 0.8mm 最薄）
                    "outer_od_mm": 24.0,
                    "height_mm": 25.0,
                    "taper_deg": 0.0,
                    "top_shape": "flat",

                    # B. 内腔配合（内腔尽可能深，顶部只留 1.5mm）
                    "inner_id_mm": 22.4,
                    "cavity_depth_mm": 23.5,
                    "edge_fillet_mm": 0.5,

                    # C. 外观细节
                    "grip.style": "ribs",
                    "grip.count": 24,
                    "grip.depth_mm": 0.3,
                },
            },
            {
                "id": "cap_18415_dome",
                "name": "圆顶瓶盖 18-415",
                "desc": "圆顶造型，锥度外形，高端唇釉瓶盖",
                "params": {
                    # A. 外形尺寸（壁厚 = (24 - 22.4) / 2 = 0.8mm 最薄）
                    "outer_od_mm": 24.0,
                    "height_mm": 28.0,
                    "taper_deg": 2.0,
                    "top_shape": "dome",

                    # B. 内腔配合（内腔尽可能深，顶部只留 2mm 给圆顶造型）
                    "inner_id_mm": 22.4,
                    "cavity_depth_mm": 26.0,
                    "edge_fillet_mm": 0.5,

                    # C. 外观细节
                    "grip.style": "knurl",
                    "grip.count": 36,
                    "grip.depth_mm": 0.2,
                },
            },
            {
                "id": "cap_spline_arc",
                "name": "弧形瓶盖",
                "desc": "spline 曲线外形，柔和弧线造型，无防滑纹",
                "params": {
                    "outer_od_mm": 24.0,
                    "height_mm": 28.0,
                    "taper_deg": 1.0,
                    "top_shape": "flat",
                    "profile_mode": "spline",
                    "profile_points_json": json.dumps([
                        [12.0, 0.0],
                        [12.2, 8.0],
                        [12.1, 18.0],
                        [11.5, 28.0],
                    ]),

                    "inner_id_mm": 22.4,
                    "cavity_depth_mm": 26.0,
                    "edge_fillet_mm": 0.5,

                    "grip.style": "none",
                    "grip.count": 0,
                    "grip.depth_mm": 0.0,
                },
            },
            {
                "id": "cap_spline_taper",
                "name": "锥形设计感瓶盖",
                "desc": "spline 曲线外形，底宽顶窄的锥形设计，无防滑纹",
                "params": {
                    "outer_od_mm": 24.0,
                    "height_mm": 30.0,
                    "taper_deg": 3.0,
                    "top_shape": "dome",
                    "profile_mode": "spline",
                    "profile_points_json": json.dumps([
                        [12.0, 0.0],
                        [11.8, 10.0],
                        [11.0, 20.0],
                        [10.2, 30.0],
                    ]),

                    "inner_id_mm": 22.4,
                    "cavity_depth_mm": 28.0,
                    "edge_fillet_mm": 0.5,

                    "grip.style": "none",
                    "grip.count": 0,
                    "grip.depth_mm": 0.0,
                },
            },
        ]

    # ---------------- rules (hard fail) ----------------
    def _rules(self) -> List[Rule]:
        """
        硬约束规则 - 确保几何合理性和配合关系
        """

        def _od_greater_than_id(p: Dict[str, Any]) -> bool:
            """外径必须大于内径（确保有壁厚）"""
            od = float(p["outer_od_mm"])
            id_ = float(p["inner_id_mm"])
            wall = round((od - id_) / 2.0, 4)
            # 锥形cap(body_top模式)允许薄壁0.3mm(需容纳body_top+螺纹)
            taper = float(p.get("taper_deg", 0))
            min_wall = 0.3 if taper > 0.5 else 0.8
            return wall >= min_wall

        def _cavity_in_height(p: Dict[str, Any]) -> bool:
            """内腔深度不能超过总高"""
            h = float(p["height_mm"])
            cav = float(p["cavity_depth_mm"])
            return 0 < cav < h

        def _grip_safe(p: Dict[str, Any]) -> bool:
            """防滑纹深度安全"""
            grip = p.get("grip", {}) or {}
            style = str(grip.get("style", "none"))
            if style == "none":
                return True
            depth = float(grip.get("depth_mm", 0.3))
            # 计算壁厚
            od = float(p["outer_od_mm"])
            id_ = float(p["inner_id_mm"])
            wall = round((od - id_) / 2.0, 4)
            # 纹理深度不能超过壁厚的 50%
            return depth <= wall * 0.5

        def _thread_safe(p: Dict[str, Any]) -> bool:
            """内螺纹安全性：峰径必须小于内腔直径，且不能击穿外壁"""
            thr = p.get("thread", {}) or {}
            if not bool(thr.get("enabled", False)):
                return True
            crest = float(thr.get("crest_dia_mm", 18.0))
            id_ = float(p["inner_id_mm"])
            od = float(p["outer_od_mm"])
            # 螺纹峰径必须小于内腔直径（否则螺纹朝外长）
            if crest >= id_:
                return False
            # 螺纹峰径必须在外壁以内（含最小壁厚余量）
            if crest >= od - 1.0:
                return False
            return True

        return [
            Rule("od_greater_than_id", "hard",
                 "外径必须大于内径：要求壁厚 (OD-ID)/2 >= 0.4mm(锥形)/0.8mm(直筒)",
                 _od_greater_than_id),
            Rule("cavity_in_height", "hard",
                 "内腔深度超过总高：要求 0 < cavity < height",
                 _cavity_in_height),
            Rule("grip_safe", "hard",
                 "纹理深度过大：不能超过壁厚的 50%",
                 _grip_safe),
            Rule("thread_safe", "hard",
                 "螺纹穿壁：峰径必须小于内腔直径且不击穿外壁",
                 _thread_safe),
        ]

    # ---------------- generate ----------------
    def generate(
        self,
        preset_id: Optional[str] = None,
        user_params: Optional[Dict[str, Any]] = None,
        outroot: str = "artifacts/webui",
        *,
        params: Optional[Dict[str, Any]] = None,
        out_root: Optional[str] = None,
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

        run_dir = _ensure_dir(Path(outroot) / f"{_now_tag()}__cap__{(preset_id or 'custom')}")
        drawings_dir = _ensure_dir(run_dir / "drawings")
        step_path = run_dir / "cap.step"
        stl_path = run_dir / "cap.stl"
        svg_path = drawings_dir / "cap_sheet.svg"

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
            solid = modeler.build("cap", p_norm, meta=meta)
            out["solid"] = solid
            modeler.export_step(solid, str(step_path))
            out["step"] = str(step_path)
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
            export_cap_sheet(p_norm, svg_path, solid=solid)
            out["svg"] = str(svg_path)
        except Exception as e:
            out["ok"] = False
            out["error"] = f"工程图导出失败：{e}"
            out["svg"] = None

        out["qc"].setdefault("modeler_meta", meta)
        return out
