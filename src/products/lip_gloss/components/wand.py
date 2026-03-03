# -*- coding: utf-8 -*-
"""
刷杆组件（Wand Component）

参数设计原则：
1. 核心参数（用户指定）vs 派生参数（自动计算）
2. 刷杆需要适配瓶盖内径和瓶身螺纹
3. 气密环外径由刷杆外径派生

参数分类：
- 核心参数：结构类型、总高、外径、杆径、刷头参数等
- 派生参数：气密环外径、盖子内腔深度等
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
from products.lip_gloss.drawings.wand_sheet import export_wand_sheet


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


class WandComponent:
    """
    唇釉瓶刷杆组件（Applicator Wand）：
    - schema：完整参数族（类型/盖子/杆身/螺纹/气密环/刷头）
    - rules：硬约束（几何一致性、配合关系）
    - generate：strict normalize -> modeler.build_wand -> export step/svg

    两种结构类型：
    - cap_integrated：帽盖一体式，刷杆嵌入盖子内部
    - separate_stem：独立杆式，刷杆头部独立于外盖
    """

    # ---------------- schema ----------------
    def schema(self) -> Dict[str, Any]:
        return {
            "id": "wand",
            "name": "刷杆（涂抹棒）",
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
            # A. 核心参数 - 结构类型
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="wand_type", name="结构类型", type="enum",
                default="cap_integrated",
                choices=["cap_integrated", "separate_stem"],
                required=True, is_core=True, group="类型"
            ),

            # ═══════════════════════════════════════════════════════════════
            # B. 核心参数 - 整体尺寸
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="total_height_mm", name="总高", unit="mm", type="float",
                default=65.0, min=40.0, max=200.0, step=0.1,
                required=True, is_core=True, group="整体"
            ),
            ParamDef(
                k="outer_od_mm", name="外径（盖子外径）", unit="mm", type="float",
                default=21.5, min=15.0, max=35.0, step=0.1,
                required=True, is_core=True, group="整体"
            ),
            ParamDef(
                k="cap_height_mm", name="盖子高度", unit="mm", type="float",
                default=18.0, min=8.0, max=35.0, step=0.1,
                required=True, is_core=True, group="整体"
            ),

            # ═══════════════════════════════════════════════════════════════
            # C. 核心参数 - 杆身
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="stem_diameter_mm", name="杆径", unit="mm", type="float",
                default=4.0, min=2.0, max=10.0, step=0.1,
                required=True, is_core=True, group="杆身"
            ),
            ParamDef(
                k="stem_length_mm", name="杆长", unit="mm", type="float",
                default=55.0, min=20.0, max=150.0, step=0.1,
                required=True, is_core=False, group="杆身",
                derived_rule=get_derived_rule("wand", "stem_length_mm")
            ),
            ParamDef(
                k="stem_profile", name="杆身轮廓", type="enum",
                default="round", choices=["round", "oval", "tapered"],
                is_core=True, group="杆身"
            ),
            ParamDef(
                k="stem_taper_ratio", name="锥度比", type="float",
                default=1.0, min=0.6, max=1.0, step=0.05,
                is_core=True, group="杆身"
            ),
            ParamDef(
                k="stem_wall_mm", name="杆壁厚（空心杆）", unit="mm", type="float",
                default=0.8, min=0.0, max=3.0, step=0.1,
                is_core=True, group="杆身"
            ),

            # ═══════════════════════════════════════════════════════════════
            # D. 核心参数 - 口部/连接
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="mouth_to_top_mm", name="口部至顶部距离", unit="mm", type="float",
                default=12.0, min=5.0, max=25.0, step=0.1,
                required=True, is_core=False, group="口部",
                derived_rule=get_derived_rule("wand", "mouth_to_top_mm")
            ),
            ParamDef(
                k="orifice_mm", name="小孔径（与内塞配合）", unit="mm", type="float",
                default=7.0, min=3.0, max=15.0, step=0.1,
                required=True, is_core=True, group="口部"
            ),
            # 派生参数：盖子内腔深度
            ParamDef(
                k="cavity_depth_mm", name="盖子内腔深度", unit="mm", type="float",
                default=13.0, min=5.0, max=35.0, step=0.1,
                is_core=False, group="口部",
                derived_rule=get_derived_rule("wand", "cavity_depth_mm")
            ),
            ParamDef(
                k="inner_depth_mm", name="杆身内深（空心深度）", unit="mm", type="float",
                default=45.0, min=0.0, max=80.0, step=0.1,
                is_core=True, group="口部"
            ),

            # ═══════════════════════════════════════════════════════════════
            # E. 核心参数 - 螺纹
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="thread.enabled", name="内螺纹-启用", type="bool",
                default=True, is_core=True, group="螺纹"
            ),
            ParamDef(
                k="thread.crest_dia_mm", name="螺牙峰径", unit="mm", type="float",
                default=18.0, min=10.0, max=28.0, step=0.1,
                required=True, is_core=False, group="螺纹",
                derived_rule=get_derived_rule("wand", "thread.crest_dia_mm")
            ),
            ParamDef(
                k="thread.pitch_mm", name="螺距", unit="mm", type="float",
                default=2.7, min=1.5, max=4.0, step=0.1,
                is_core=True, group="螺纹"
            ),
            ParamDef(
                k="thread.turns", name="圈数", type="int",
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
            # F. 派生参数 - 气密环
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="seal_ring.od_mm", name="气密环外径", unit="mm", type="float",
                default=16.0, min=12.0, max=25.0, step=0.1,
                required=True, is_core=False, group="气密环",
                derived_rule=get_derived_rule("wand", "seal_ring.od_mm")
            ),
            ParamDef(
                k="seal_ring.height_mm", name="气密环高度", unit="mm", type="float",
                default=3.0, min=1.0, max=8.0, step=0.1,
                is_core=True, group="气密环"
            ),
            ParamDef(
                k="seal_ring.style", name="气密环形态", type="enum",
                default="flat", choices=["flat", "conical", "ring"],
                is_core=True, group="气密环"
            ),

            # ═══════════════════════════════════════════════════════════════
            # G. 核心参数 - 刷头
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="brush.type", name="刷头类型", type="enum",
                default="doe_foot",
                choices=["doe_foot", "fiber_brush", "silicone_spatula"],
                is_core=True, group="刷头"
            ),
            ParamDef(
                k="brush.length_mm", name="刷头长度", unit="mm", type="float",
                default=12.0, min=5.0, max=25.0, step=0.1,
                is_core=True, group="刷头"
            ),
            ParamDef(
                k="brush.width_mm", name="刷头宽度", unit="mm", type="float",
                default=10.0, min=4.0, max=18.0, step=0.1,
                is_core=True, group="刷头"
            ),
            ParamDef(
                k="brush.thickness_mm", name="刷头厚度", unit="mm", type="float",
                default=4.0, min=2.0, max=10.0, step=0.1,
                is_core=True, group="刷头"
            ),

            # ═══════════════════════════════════════════════════════════════
            # H. 配合参数
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="finish", name="口部规格（标注）", type="str",
                default="18-415", is_core=True, group="配合"
            ),
            ParamDef(
                k="fit_clearance_mm", name="配合间隙", unit="mm", type="float",
                default=0.15, min=0.05, max=0.5, step=0.05,
                is_core=True, group="配合"
            ),
        ]

    def _style_presets(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "wand_integrated_18",
                "name": "一体式刷杆 18-415",
                "desc": "标准帽盖一体式设计，doe-foot刷头，适配18-415瓶口",
                "params": {
                    # 类型
                    "wand_type": "cap_integrated",

                    # 整体（外径适配瓶盖内径22.4mm）
                    "total_height_mm": 65.0,
                    "outer_od_mm": 21.5,  # 瓶盖内径22.4 - 0.9 = 21.5
                    "cap_height_mm": 17.0,  # 需 ≤ cap腔顶-safe_z（避免穿透cap顶部）

                    # 杆身
                    "stem_diameter_mm": 4.0,
                    "stem_length_mm": 55.0,
                    "stem_profile": "round",
                    "stem_taper_ratio": 1.0,
                    "stem_wall_mm": 0.8,

                    # 口部
                    "mouth_to_top_mm": 11.0,
                    "orifice_mm": 7.0,
                    "cavity_depth_mm": 16.5,  # 顶部壁厚=17-16.5=0.5mm
                    "inner_depth_mm": 45.0,

                    # 螺纹（root_dia 自动计算 = crest - 2*depth）
                    "thread.enabled": True,
                    "thread.crest_dia_mm": 18.0,
                    "thread.pitch_mm": 2.7,
                    "thread.turns": 2,
                    "thread.depth_mm": 0.5,
                    "thread.lead_angle_deg": 3.0,
                    "thread.segmented": False,
                    "thread.gap_angle_deg": 20.0,

                    # 气密环（基于 outer_od 21.5 - 5.5 = 16.0）
                    "seal_ring.od_mm": 16.0,
                    "seal_ring.height_mm": 3.0,
                    "seal_ring.style": "flat",

                    # 刷头
                    "brush.type": "doe_foot",
                    "brush.length_mm": 12.0,
                    "brush.width_mm": 10.0,
                    "brush.thickness_mm": 4.0,

                    # 配合
                    "finish": "18-415",
                    "fit_clearance_mm": 0.15,
                },
            },
            {
                "id": "wand_separate_18",
                "name": "独立杆式 18-415",
                "desc": "独立刷杆设计，带外盖套筒，适配18-415瓶口",
                "params": {
                    # 类型
                    "wand_type": "separate_stem",

                    # 整体（外径适配瓶盖内径22.4mm）
                    "total_height_mm": 70.0,
                    "outer_od_mm": 21.5,  # 瓶盖内径22.4 - 0.9 = 21.5
                    "cap_height_mm": 17.0,  # 需 ≤ cap腔顶-safe_z（避免穿透cap顶部）

                    # 杆身
                    "stem_diameter_mm": 4.5,
                    "stem_length_mm": 52.0,
                    "stem_profile": "tapered",
                    "stem_taper_ratio": 0.85,
                    "stem_wall_mm": 0.6,

                    # 口部
                    "mouth_to_top_mm": 12.0,
                    "orifice_mm": 7.0,
                    "cavity_depth_mm": 16.5,  # 顶部壁厚=17-16.5=0.5mm
                    "inner_depth_mm": 40.0,

                    # 螺纹（root_dia 自动计算 = crest - 2*depth）
                    "thread.enabled": True,
                    "thread.crest_dia_mm": 18.0,
                    "thread.pitch_mm": 2.7,
                    "thread.turns": 2,
                    "thread.depth_mm": 0.5,
                    "thread.lead_angle_deg": 3.0,
                    "thread.segmented": True,  # 独立杆式使用分段螺纹
                    "thread.gap_angle_deg": 20.0,

                    # 气密环（基于 outer_od 21.5 - 5.5 = 16.0）
                    "seal_ring.od_mm": 16.0,
                    "seal_ring.height_mm": 4.0,
                    "seal_ring.style": "conical",

                    # 刷头
                    "brush.type": "doe_foot",
                    "brush.length_mm": 14.0,
                    "brush.width_mm": 11.0,
                    "brush.thickness_mm": 4.5,

                    # 配合
                    "finish": "18-415",
                    "fit_clearance_mm": 0.15,
                },
            },
        ]

    # ---------------- rules (hard fail) ----------------
    def _rules(self) -> List[Rule]:
        def _stem_fit(p: Dict[str, Any]) -> bool:
            """杆身需穿过小孔径：stem_diameter < orifice - 1mm"""
            stem_d = float(p["stem_diameter_mm"])
            orifice = float(p["orifice_mm"])
            return stem_d < orifice - 0.5

        def _thread_valid(p: Dict[str, Any]) -> bool:
            """螺纹合理性：峰径 - 2*牙深 > 杆径"""
            thr = p.get("thread", {}) or {}
            crest = float(thr.get("crest_dia_mm", 18.0))
            depth = float(thr.get("depth_mm", 0.5))
            stem = float(p["stem_diameter_mm"])
            # 底径由峰径和牙深自动计算
            root = crest - 2 * depth
            return crest > root and root > stem

        def _seal_fit(p: Dict[str, Any]) -> bool:
            """气密环配合：气密环外径 < 螺牙底径"""
            seal_ring = p.get("seal_ring", {}) or {}
            seal_od = float(seal_ring.get("od_mm", 17.5))
            thr = p.get("thread", {}) or {}
            crest = float(thr.get("crest_dia_mm", 18.0))
            depth = float(thr.get("depth_mm", 0.5))
            # 底径由峰径和牙深自动计算
            root = crest - 2 * depth
            # 气密环应略小于螺纹底径
            return seal_od <= root + 1.5

        def _height_check(p: Dict[str, Any]) -> bool:
            """高度一致性：总高 >= 盖子高度 + 刷头长度"""
            total = float(p["total_height_mm"])
            cap_h = float(p["cap_height_mm"])
            brush = p.get("brush", {}) or {}
            brush_len = float(brush.get("length_mm", 12.0))
            stem_len = float(p["stem_length_mm"])
            # 总高应容纳盖子+杆身+刷头（考虑重叠）
            return total >= cap_h + brush_len - 5.0

        def _finish_match(p: Dict[str, Any]) -> bool:
            """规格匹配：螺牙峰径与finish标注匹配"""
            thr = p.get("thread", {}) or {}
            crest = float(thr.get("crest_dia_mm", 18.0))
            finish = str(p.get("finish", "18-415"))
            try:
                spec_dia = float(finish.split("-")[0])
            except (ValueError, IndexError):
                return True
            # 峰径应接近规格直径
            return abs(crest - spec_dia) <= 2.0

        return [
            Rule("stem_fit", "hard", "杆身过粗：杆径需 < 小孔径 - 0.5mm", _stem_fit),
            Rule("thread_valid", "hard", "螺纹不合理：需满足 峰径 > 底径 > 杆径", _thread_valid),
            Rule("seal_fit", "hard", "气密环过大：气密环外径需 <= 螺牙底径 + 1.5mm", _seal_fit),
            Rule("height_check", "hard", "高度不足：总高需 >= 盖高 + 刷头长 - 5mm", _height_check),
            # depth_valid 已移除：杆长由总高派生，cross-component I1 约束防止杆长超出瓶底
            Rule("finish_match", "hard", "规格不匹配：螺牙峰径与口部规格差异过大", _finish_match),
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

        run_dir = _ensure_dir(Path(outroot) / f"{_now_tag()}__wand__{(preset_id or 'custom')}")
        drawings_dir = _ensure_dir(run_dir / "drawings")
        step_path = run_dir / "wand.step"
        stl_path = run_dir / "wand.stl"
        svg_path = drawings_dir / "wand_sheet.svg"

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
            out["error"] = "参数不满足硬约束（strict），已阻止导出。"
            return out

        modeler = Modeler()
        meta: Dict[str, Any] = {}
        try:
            solid = modeler.build("wand", p_norm, meta=meta)
            modeler.export_step(solid, str(step_path))
            out["step"] = str(step_path)
            # 导出 STL 用于 Web 3D 预览
            try:
                import cadquery as cq

                cq.exporters.export(solid, str(stl_path), exportType="STL")
                out["stl"] = str(stl_path)
            except Exception:
                out["stl"] = None
        except Exception as e:
            out["ok"] = False
            out["error"] = f"建模/STEP 导出失败：{e}"
            out["qc"].setdefault("modeler_meta", meta)
            return out

        try:
            export_wand_sheet(p_norm, svg_path)
            out["svg"] = str(svg_path)
        except Exception as e:
            out["ok"] = False
            out["error"] = f"工程图导出失败：{e}"
            out["svg"] = None

        out["qc"].setdefault("modeler_meta", meta)
        return out
