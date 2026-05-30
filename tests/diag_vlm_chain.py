# -*- coding: utf-8 -*-
"""
诊断脚本：模拟 VLM 图片生成的参数合成链，检查哪些参数违反 QC。
用法: python tests/diag_vlm_chain.py
"""
import sys, os, io, json

# Windows GBK 终端兼容
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', 'src')))
sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

from core.vlm_extract import (
    build_bottle_params, derive_cap_params,
    derive_wand_params, derive_wiper_params,
    reconcile_all_params,
)
from core.interpreter import Interpreter
from products.lip_gloss.components.registry import get_component


def diagnose(user_dims: dict, vlm_shape: dict, label: str = ""):
    """模拟 VLM 链并输出 QC 结果"""
    print(f"\n{'='*60}")
    print(f"诊断: {label}")
    print(f"  user_dims: {json.dumps(user_dims, ensure_ascii=False)}")
    print(f"{'='*60}")

    bottle_p = build_bottle_params(user_dims, vlm_shape)
    cap_p = derive_cap_params(bottle_p, vlm_shape)
    wand_p = derive_wand_params(cap_p, bottle_p)
    wiper_p = derive_wiper_params(bottle_p, wand_p)

    all_p = {"bottle": bottle_p, "cap": cap_p, "wand": wand_p, "wiper": wiper_p}
    all_p, report = reconcile_all_params(all_p)
    if report:
        print(f"\n  reconcile 修正 ({len(report)} 项):")
        for r in report:
            print(f"    {r}")

    # 逐组件跑 normalize_strict
    for comp_id in ["bottle", "cap", "wand", "wiper"]:
        comp = get_component("lip_gloss", comp_id)
        params = all_p[comp_id]

        interp = Interpreter()
        p_json = [comp._p(p) for p in comp._param_defs()]
        _, _, qc = interp.normalize_strict(
            p_json,
            preset_params={},
            user_params=params,
            rules=comp._rules(),
            allow_unknown_keys=False,
        )

        hard_fails = [c for c in qc.get("checks", [])
                       if c.get("severity") == "hard" and not c.get("ok")]
        if hard_fails:
            print(f"\n  [{comp_id}] QC FAIL ({len(hard_fails)} 条):")
            for c in hard_fails:
                print(f"    {c['id']}: {c['msg']}")
                if c.get("data"):
                    print(f"      data: {json.dumps(c['data'], ensure_ascii=False, default=str)}")
        else:
            print(f"\n  [{comp_id}] QC OK ✓")


# ── 场景 1: 典型值 (100mm 产品) ──
diagnose(
    user_dims={"height_mm": 65, "body_od_mm": 22, "neck_od_mm": 18},
    vlm_shape={
        "cross_section": "round", "corner_radius_mm": 0, "shape": "cyl",
        "taper_deg": 0, "cap_top_shape": "flat", "cap_grip_style": "smooth",
        "shoulder_style": "round", "shoulder_fillet_mm": 3.0,
        "bottom_style": "flat", "profile_mode": "classic",
        "cap_height_mm": 35, "cap_od_ratio": 1.0,
        "cap_stem_enabled": True, "cap_stem_diameter_mm": 4.25,
        "cap_brush_type": "doe_foot",
        "bottle_material": "glossy_plastic", "cap_material": "glossy_plastic",
        "wand_material": "glossy_plastic", "wiper_material": "matte_plastic",
        "confidence": 1.0,
    },
    label="典型圆形瓶 100mm (cap_stem=True)",
)

# ── 场景 2: 同上但 cap_stem=False ──
diagnose(
    user_dims={"height_mm": 65, "body_od_mm": 22, "neck_od_mm": 18},
    vlm_shape={
        "cross_section": "round", "corner_radius_mm": 0, "shape": "cyl",
        "taper_deg": 0, "cap_top_shape": "flat", "cap_grip_style": "smooth",
        "shoulder_style": "round", "shoulder_fillet_mm": 3.0,
        "bottom_style": "flat", "profile_mode": "classic",
        "cap_height_mm": 35, "cap_od_ratio": 1.0,
        "cap_stem_enabled": False,
        "bottle_material": "glossy_plastic", "cap_material": "glossy_plastic",
        "confidence": 1.0,
    },
    label="典型圆形瓶 100mm (cap_stem=False)",
)

# ── 场景 3: 小瓶 (60mm 产品, CV 推算可能出小值) ──
diagnose(
    user_dims={"height_mm": 40, "body_od_mm": 14, "neck_od_mm": 11},
    vlm_shape={
        "cross_section": "round", "corner_radius_mm": 0, "shape": "cyl",
        "taper_deg": 0, "cap_top_shape": "flat", "cap_grip_style": "smooth",
        "shoulder_style": "round", "shoulder_fillet_mm": 2.0,
        "bottom_style": "flat", "profile_mode": "classic",
        "cap_height_mm": 20, "cap_od_ratio": 1.0,
        "cap_stem_enabled": True, "cap_stem_diameter_mm": 4.25,
        "cap_brush_type": "doe_foot",
        "confidence": 1.0,
    },
    label="小瓶 60mm (body_od=14, neck=11)",
)

# ── 场景 4: 极端小值 ──
diagnose(
    user_dims={"height_mm": 30, "body_od_mm": 10, "neck_od_mm": 8},
    vlm_shape={
        "cross_section": "round", "corner_radius_mm": 0, "shape": "cyl",
        "taper_deg": 0, "cap_top_shape": "flat", "cap_grip_style": "smooth",
        "shoulder_style": "round", "shoulder_fillet_mm": 1.0,
        "bottom_style": "flat", "profile_mode": "classic",
        "cap_height_mm": 12, "cap_od_ratio": 1.0,
        "cap_stem_enabled": True, "cap_stem_diameter_mm": 4.25,
        "cap_brush_type": "doe_foot",
        "confidence": 1.0,
    },
    label="极端小值 (body_od=10 < bottle.min=12)",
)
