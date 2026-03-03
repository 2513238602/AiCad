# -*- coding: utf-8 -*-
"""
唇釉瓶测试 - 公共配置与测试数据

提供:
- 各规格参数集（标准/大/小）
- Windows UTF-8 环境修复
- src 路径注入
"""
from __future__ import annotations

import sys
import io

# Windows GBK 环境下 CadQuery/OCCT 可能输出非 GBK 字符，统一用 UTF-8
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, "g:/AiCad/src")

from typing import Any, Dict, List

# 确保派生规则已注册
import products.lip_gloss.derived_params  # noqa: F401

from core.component_state import ComponentStateManager, get_state_manager

ALL_COMPONENTS = ["cap", "bottle", "wand", "wiper"]


# ============================================================
# 各规格参数集
# ============================================================

COMPONENT_PARAMS_STANDARD: Dict[str, Dict[str, Any]] = {
    "cap": {
        "outer_od_mm": 24.0,
        "height_mm": 25.0,
        "taper_deg": 0.0,
        "inner_id_mm": 22.4,
        "cavity_depth_mm": 23.5,
        "edge_fillet_mm": 0.5,
        "seal": {"plug_od_mm": 6.5, "plug_h_mm": 5.0},
        "grip": {"style": "ribs", "count": 24, "depth_mm": 0.3},
        "finish": "18-415",
        "body_od_mm": 24.0,
    },
    "bottle": {
        "height_mm": 70.0,
        "body_od_mm": 24.0,
        "shape": "cyl",
        "taper_deg": 0.0,
        "neck_od_mm": 18.0,
        "neck_height_mm": 10.0,
        "lip_thickness_mm": 1.0,
        "thread": {
            "enabled": True,
            "pitch_mm": 2.7,
            "turns": 2,
            "depth_mm": 0.5,
            "lead_angle_deg": 3.0,
            "crest_dia_mm": 18.5,
        },
        "shoulder_height_mm": 10.0,
        "shoulder_style": "round",
        "shoulder_fillet_mm": 3.0,
        "capacity_ml": 5.0,
        "inner_depth_mm": 55.0,
        "wall_thickness_mm": 1.2,
        "bottom_thickness_mm": 2.0,
        "bottom_style": "flat",
        "finish": "18-415",
        "cap_clearance_mm": 0.2,
    },
    "wand": {
        "wand_type": "cap_integrated",
        "total_height_mm": 65.0,
        "outer_od_mm": 21.5,
        "cap_height_mm": 19.0,
        "stem_diameter_mm": 4.0,
        "stem_length_mm": 40.0,
        "stem_profile": "round",
        "mouth_to_top_mm": 12.0,
        "orifice_mm": 7.0,
        "cavity_depth_mm": 13.0,
        "inner_depth_mm": 45.0,
        "thread": {
            "enabled": True,
            "crest_dia_mm": 18.0,
            "pitch_mm": 2.7,
            "turns": 2,
            "depth_mm": 0.5,
            "lead_angle_deg": 3.0,
        },
        "seal_ring": {"od_mm": 16.0, "height_mm": 3.0, "style": "flat"},
        "brush": {
            "type": "doe_foot",
            "length_mm": 12.0,
            "width_mm": 10.0,
            "thickness_mm": 4.0,
        },
        "finish": "18-415",
        "fit_clearance_mm": 0.15,
    },
    "wiper": {
        "height_mm": 8.0,
        "outer_od_mm": 15.5,
        "inner_id_mm": 12.0,
        "orifice_mm": 7.0,
        "orifice_edge_mm": 0.3,
        "flange_od_mm": 17.0,
        "flange_id_mm": 14.5,
        "flange_height_mm": 1.5,
        "flange_position": "bottom",
        "diaphragm_style": "flat",
        "diaphragm_thickness_mm": 0.8,
        "fit_clearance_mm": 0.1,
        "material": "LDPE",
        "finish": "18-415",
    },
}

COMPONENT_PARAMS_LARGE: Dict[str, Dict[str, Any]] = {
    "cap": {
        "outer_od_mm": 30.0,
        "height_mm": 35.0,
        "inner_id_mm": 28.0,
        "cavity_depth_mm": 33.0,
        "seal": {"plug_od_mm": 9.0, "plug_h_mm": 7.0},
        "finish": "24-410",
        "body_od_mm": 30.0,
    },
    "bottle": {
        "height_mm": 100.0,
        "body_od_mm": 30.0,
        "neck_od_mm": 24.0,
        "neck_height_mm": 14.0,
        "lip_thickness_mm": 1.2,
        "thread": {"pitch_mm": 2.7, "crest_dia_mm": 24.5},
        "inner_depth_mm": 80.0,
        "wall_thickness_mm": 1.5,
        "finish": "24-410",
    },
    "wand": {
        "total_height_mm": 85.0,
        "outer_od_mm": 27.0,
        "cap_height_mm": 25.0,
        "stem_diameter_mm": 5.5,
        "stem_length_mm": 55.0,
        "orifice_mm": 9.5,
        "thread": {"crest_dia_mm": 24.0, "pitch_mm": 2.7},
        "finish": "24-410",
    },
    "wiper": {
        "height_mm": 12.0,
        "outer_od_mm": 21.0,
        "orifice_mm": 9.5,
        "flange_od_mm": 23.0,
        "finish": "24-410",
    },
}

COMPONENT_PARAMS_SMALL: Dict[str, Dict[str, Any]] = {
    "cap": {
        "outer_od_mm": 16.0,
        "height_mm": 18.0,
        "inner_id_mm": 14.5,
        "cavity_depth_mm": 16.0,
        "seal": {"plug_od_mm": 4.5, "plug_h_mm": 3.5},
        "finish": "13-415",
        "body_od_mm": 16.0,
    },
    "bottle": {
        "height_mm": 50.0,
        "body_od_mm": 16.0,
        "neck_od_mm": 13.0,
        "neck_height_mm": 7.0,
        "lip_thickness_mm": 0.8,
        "thread": {"pitch_mm": 2.0, "crest_dia_mm": 13.5},
        "inner_depth_mm": 38.0,
        "wall_thickness_mm": 1.0,
        "finish": "13-415",
    },
    "wand": {
        "total_height_mm": 50.0,
        "outer_od_mm": 13.5,
        "cap_height_mm": 14.0,
        "stem_diameter_mm": 3.0,
        "stem_length_mm": 30.0,
        "orifice_mm": 5.0,
        "thread": {"crest_dia_mm": 13.0, "pitch_mm": 2.0},
        "finish": "13-415",
    },
    "wiper": {
        "height_mm": 6.0,
        "outer_od_mm": 11.0,
        "orifice_mm": 5.0,
        "flange_od_mm": 12.5,
        "finish": "13-415",
    },
}

ALL_PARAM_SETS = {
    "标准(18-415)": COMPONENT_PARAMS_STANDARD,
    "大尺寸(24-410)": COMPONENT_PARAMS_LARGE,
    "小尺寸(13-415)": COMPONENT_PARAMS_SMALL,
}
