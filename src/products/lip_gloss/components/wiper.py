# -*- coding: utf-8 -*-
"""
内塞组件（Wiper Component）

参数设计原则：
1. 核心参数（用户指定）vs 派生参数（自动计算）
2. 内塞需要适配瓶颈和刷杆
3. 内径由外径派生

参数分类：
- 核心参数：总高、外径、孔径、材料等
- 派生参数：内径、凸环尺寸等
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
from products.lip_gloss.drawings.wiper_sheet import export_wiper_sheet


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


class WiperComponent:
    """
    唇釉瓶内塞组件（Wiper Insert）：
    - schema：完整参数族（主体/凸环/孔口/刮片/材料）
    - rules：硬约束（几何一致性、配合关系）
    - generate：strict normalize -> modeler.build_wiper -> export step/svg
    """

    # ---------------- schema ----------------
    def schema(self) -> Dict[str, Any]:
        return {
            "id": "wiper",
            "name": "内塞（刮片/密封）",
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
            # A. 核心参数 - 主体尺寸
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="height_mm", name="总高 H", unit="mm", type="float",
                default=12.0, min=4.0, max=25.0, step=0.1,
                required=True, is_core=True, group="主体"
            ),
            ParamDef(
                k="outer_od_mm", name="外径 OD（与瓶颈配合）", unit="mm", type="float",
                default=15.5, min=8.0, max=22.0, step=0.1,
                required=True, is_core=True, group="主体"
            ),
            # 派生参数：内径
            ParamDef(
                k="inner_id_mm", name="内径 ID", unit="mm", type="float",
                default=12.0, min=5.0, max=20.0, step=0.1,
                required=True, is_core=False, group="主体",
                derived_rule=get_derived_rule("wiper", "inner_id_mm")
            ),

            # ═══════════════════════════════════════════════════════════════
            # B. 核心参数 - 中心孔口
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="orifice_mm", name="小孔径（中心孔口）", unit="mm", type="float",
                default=7.0, min=2.0, max=14.0, step=0.1,
                required=True, is_core=True, group="孔口"
            ),
            ParamDef(
                k="orifice_edge_mm", name="孔口边缘厚度", unit="mm", type="float",
                default=0.3, min=0.1, max=1.0, step=0.05,
                is_core=True, group="孔口"
            ),

            # ═══════════════════════════════════════════════════════════════
            # C. 派生参数 - 凸环/卡扣
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="flange_od_mm", name="凸环外径", unit="mm", type="float",
                default=17.0, min=10.0, max=24.0, step=0.1,
                required=True, is_core=False, group="凸环",
                derived_rule=get_derived_rule("wiper", "flange_od_mm")
            ),
            ParamDef(
                k="flange_id_mm", name="凸环内径", unit="mm", type="float",
                default=14.5, min=8.0, max=22.0, step=0.1,
                required=True, is_core=False, group="凸环",
                derived_rule=get_derived_rule("wiper", "flange_id_mm")
            ),
            ParamDef(
                k="flange_height_mm", name="凸环高度", unit="mm", type="float",
                default=1.5, min=0.5, max=4.0, step=0.1,
                is_core=True, group="凸环"
            ),
            ParamDef(
                k="flange_position", name="凸环位置", type="enum",
                default="bottom", choices=["bottom", "middle", "top"],
                is_core=True, group="凸环"
            ),

            # ═══════════════════════════════════════════════════════════════
            # D. 核心参数 - 刮片/隔膜
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="diaphragm_style", name="隔膜样式", type="enum",
                default="flat", choices=["flat", "concave", "convex"],
                is_core=True, group="隔膜"
            ),
            ParamDef(
                k="diaphragm_thickness_mm", name="隔膜厚度", unit="mm", type="float",
                default=0.8, min=0.3, max=2.0, step=0.1,
                is_core=True, group="隔膜"
            ),
            ParamDef(
                k="diaphragm_depth_mm", name="隔膜凹凸深度", unit="mm", type="float",
                default=1.0, min=0.0, max=4.0, step=0.1,
                is_core=True, group="隔膜"
            ),

            # ═══════════════════════════════════════════════════════════════
            # E. 核心参数 - 加强筋
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="rib.enabled", name="加强筋-启用", type="bool",
                default=False, is_core=True, group="加强筋"
            ),
            ParamDef(
                k="rib.count", name="加强筋数量", type="int",
                default=4, min=2, max=12, step=1,
                is_core=True, group="加强筋"
            ),
            ParamDef(
                k="rib.width_mm", name="加强筋宽度", unit="mm", type="float",
                default=0.6, min=0.3, max=1.5, step=0.1,
                is_core=True, group="加强筋"
            ),
            ParamDef(
                k="rib.height_mm", name="加强筋高度", unit="mm", type="float",
                default=0.4, min=0.2, max=1.0, step=0.1,
                is_core=True, group="加强筋"
            ),

            # ═══════════════════════════════════════════════════════════════
            # F. 配合与材料
            # ═══════════════════════════════════════════════════════════════
            ParamDef(
                k="fit_clearance_mm", name="配合间隙", unit="mm", type="float",
                default=0.1, min=0.0, max=0.5, step=0.05,
                is_core=True, group="配合"
            ),
            ParamDef(
                k="material", name="材料", type="enum",
                default="LDPE", choices=["LDPE", "silicone", "TPE", "NBR"],
                is_core=True, group="配合"
            ),
            ParamDef(
                k="finish", name="配合瓶口规格", type="str",
                default="18-415", is_core=True, group="配合"
            ),
        ]

    def _style_presets(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "wiper_standard_18",
                "name": "标准内塞 18-415",
                "desc": "适配18-415瓶口的标准LDPE内塞",
                "params": {
                    # 主体（高度需 < neck_h 以避免伸入肩部，且避开wand气密环区域）
                    "height_mm": 8.0,
                    "outer_od_mm": 15.5,
                    "inner_id_mm": 12.0,

                    # 孔口
                    "orifice_mm": 7.0,
                    "orifice_edge_mm": 0.3,

                    # 凸环（必须 < neck_id=16.0mm 才能装入瓶颈）
                    "flange_od_mm": 16.0,
                    "flange_id_mm": 14.5,
                    "flange_height_mm": 1.5,
                    "flange_position": "bottom",

                    # 隔膜
                    "diaphragm_style": "concave",
                    "diaphragm_thickness_mm": 0.8,
                    "diaphragm_depth_mm": 1.5,

                    # 加强筋
                    "rib.enabled": False,
                    "rib.count": 4,
                    "rib.width_mm": 0.6,
                    "rib.height_mm": 0.4,

                    # 配合
                    "fit_clearance_mm": 0.1,
                    "material": "LDPE",
                    "finish": "18-415",
                },
            },
            {
                "id": "wiper_silicone_soft",
                "name": "硅胶软刮内塞",
                "desc": "硅胶材质，柔软刮片，适合高粘度产品",
                "params": {
                    "height_mm": 8.0,
                    "outer_od_mm": 15.5,
                    "inner_id_mm": 13.0,

                    "orifice_mm": 6.0,
                    "orifice_edge_mm": 0.25,

                    "flange_od_mm": 16.0,
                    "flange_id_mm": 14.0,
                    "flange_height_mm": 1.2,
                    "flange_position": "bottom",

                    "diaphragm_style": "concave",
                    "diaphragm_thickness_mm": 0.6,
                    "diaphragm_depth_mm": 2.0,

                    "rib.enabled": True,
                    "rib.count": 4,
                    "rib.width_mm": 0.5,
                    "rib.height_mm": 0.3,

                    "fit_clearance_mm": 0.15,
                    "material": "silicone",
                    "finish": "18-415",
                },
            },
        ]

    # ---------------- rules (hard fail) ----------------
    def _rules(self) -> List[Rule]:
        def _geometry_valid(p: Dict[str, Any]) -> bool:
            """几何一致性：外径 > 内径 > 孔径"""
            od = float(p["outer_od_mm"])
            id_ = float(p["inner_id_mm"])
            orifice = float(p["orifice_mm"])
            return od > id_ and id_ > orifice and orifice > 0

        def _flange_valid(p: Dict[str, Any]) -> bool:
            """凸环一致性：凸环外径 > 外径，凸环内径 < 外径"""
            od = float(p["outer_od_mm"])
            flange_od = float(p["flange_od_mm"])
            flange_id = float(p["flange_id_mm"])
            return flange_od >= od and flange_id < flange_od and flange_id > 0

        def _wall_thickness_valid(p: Dict[str, Any]) -> bool:
            """壁厚合理性：(外径-内径)/2 >= 0.5mm"""
            od = float(p["outer_od_mm"])
            id_ = float(p["inner_id_mm"])
            wall = (od - id_) / 2.0
            return wall >= 0.5

        def _orifice_edge_valid(p: Dict[str, Any]) -> bool:
            """孔口边缘：(内径-孔径)/2 >= 孔口边缘厚度"""
            id_ = float(p["inner_id_mm"])
            orifice = float(p["orifice_mm"])
            edge = float(p.get("orifice_edge_mm", 0.3))
            diaphragm_ring = (id_ - orifice) / 2.0
            return diaphragm_ring >= edge

        def _height_valid(p: Dict[str, Any]) -> bool:
            """高度合理性：总高 > 凸环高度 + 隔膜厚度"""
            H = float(p["height_mm"])
            flange_h = float(p.get("flange_height_mm", 1.5))
            diaphragm_t = float(p.get("diaphragm_thickness_mm", 0.8))
            return H > (flange_h + diaphragm_t + 1.0)

        def _finish_match(p: Dict[str, Any]) -> bool:
            """规格匹配：凸环外径与finish标注匹配"""
            flange_od = float(p["flange_od_mm"])
            finish = str(p.get("finish", "18-415"))
            try:
                spec_od = float(finish.split("-")[0])
            except (ValueError, IndexError):
                return True
            # 凸环外径应接近瓶口内径（略小于规格外径）
            return abs(flange_od - spec_od) <= 2.0

        return [
            Rule("geometry_valid", "hard", "几何不合理：需满足 外径 > 内径 > 孔径 > 0", _geometry_valid),
            Rule("flange_valid", "hard", "凸环不合理：需满足 凸环外径 >= 外径，凸环内径 < 凸环外径", _flange_valid),
            Rule("wall_thickness_valid", "hard", "壁厚过薄：(外径-内径)/2 需 >= 0.5mm", _wall_thickness_valid),
            Rule("orifice_edge_valid", "hard", "孔口边缘过窄：隔膜环宽需 >= 孔口边缘厚度", _orifice_edge_valid),
            Rule("height_valid", "hard", "高度不足：总高需 > 凸环高 + 隔膜厚 + 1mm", _height_valid),
            Rule("finish_match", "hard", "规格不匹配：凸环外径与瓶口规格差异过大", _finish_match),
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

        run_dir = _ensure_dir(Path(outroot) / f"{_now_tag()}__wiper__{(preset_id or 'custom')}")
        drawings_dir = _ensure_dir(run_dir / "drawings")
        step_path = run_dir / "wiper.step"
        stl_path = run_dir / "wiper.stl"
        svg_path = drawings_dir / "wiper_sheet.svg"

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
            solid = modeler.build("wiper", p_norm, meta=meta)
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
            export_wiper_sheet(p_norm, svg_path)
            out["svg"] = str(svg_path)
        except Exception as e:
            out["ok"] = False
            out["error"] = f"工程图导出失败：{e}"
            out["svg"] = None

        out["qc"].setdefault("modeler_meta", meta)
        return out
