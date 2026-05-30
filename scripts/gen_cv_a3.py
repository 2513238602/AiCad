# -*- coding: utf-8 -*-
"""用 CV 提取参数生成 A3 瓶子 — 与 Gallery 硬编码版对比"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from web_server import _gvlm, _fix_finish_spec, GALLERY_CATALOG
from prebuild_gallery import build_one

# ---- CV 提取的 canda_silver_01 参数（最佳 mask 质量） ----
# 注意: taper_deg 在 CV 中为负（顶宽底窄）,
#       但 CAD 系统的正值含义也是「底部较宽的锥度」，
#       这里取 abs 值让 CAD 系统正确解读。
CV_VLM_SHAPE = _gvlm({
    "shape": "taper",
    "taper_deg": 6.0,               # CV: abs(-6.01) ≈ 6°
    "cross_section": "octagon",      # CV 无法检测，保留人工设定
    "corner_radius_mm": 0.8,
    "shoulder_style": "round",       # CV: round（Gallery: angular）
    "shoulder_fillet_mm": 3.0,       # CV: 肩部圆滑 → 增大 fillet
    "shoulder_height_mm": 5.0,
    "bottom_fillet_mm": 1.0,
    "cap_top_shape": "dome",         # CV: dome（Gallery: flat）
    "cap_grip_style": "smooth",
    "cap_od_base": "body_top",       # CV: body_top
    "cap_od_ratio": 0.84,            # CV: 0.84（Gallery: 1.0）
    "cap_height_mm": 35,             # CV: 68.6 不合理，回退到 Gallery 值
    "cap_taper_deg": 0.93,           # CV: 0.93（Gallery: 0.5）
    "cap_stem_enabled": True,
    "cap_stem_diameter_mm": 4.25,
    "cap_brush_type": "doe_foot",
})

# 同样的 user_dims
USER_DIMS = {"height_mm": 65, "body_od_mm": 24, "neck_od_mm": 17}

# ---- 注册为临时 Gallery 配置 ----
CV_SPEC = {
    "desc": "A3 CV版 — canda_silver_01 CV提取参数",
    "components": ["bottle", "cap", "wiper"],
    "user_dims": USER_DIMS,
    "vlm_shape": CV_VLM_SHAPE,
}


def main():
    print("=" * 60)
    print("生成 A3 CV版 (基于 canda_silver_01 CV 提取参数)")
    print("=" * 60)

    # 对比显示参数差异
    gal_shape = GALLERY_CATALOG["A3_round_pointed"]["vlm_shape"]
    diff_keys = []
    for k in sorted(set(list(CV_VLM_SHAPE.keys()) + list(gal_shape.keys()))):
        cv_v = CV_VLM_SHAPE.get(k)
        gal_v = gal_shape.get(k)
        if cv_v != gal_v:
            diff_keys.append(k)
            print(f"  {k:>25s}: Gallery={gal_v}  CV={cv_v}")

    print(f"\n共 {len(diff_keys)} 个参数不同\n")

    # 生成
    from prebuild_gallery import PREBUILT_ROOT
    # 注入到 GALLERY_CATALOG 以复用 build_one
    from web_server import GALLERY_CATALOG as cat
    cat["A3_cv_version"] = CV_SPEC

    manifest = build_one("A3_cv_version", CV_SPEC)

    print("\n" + "=" * 60)
    out_dir = PREBUILT_ROOT / "A3_cv_version"
    comps = manifest.get("components", {})
    for cid, cdata in comps.items():
        stl = cdata.get("stl", "N/A")
        print(f"  {cid}: {stl}")
        if "params" in cdata:
            p = cdata["params"]
            if cid == "bottle":
                print(f"    body_od={p.get('body_od_mm')}, height={p.get('height_mm')}, "
                      f"taper={p.get('taper_deg')}, cross={p.get('cross_section')}")
            elif cid == "cap":
                print(f"    od={p.get('outer_od_mm')}, height={p.get('height_mm')}, "
                      f"taper={p.get('taper_deg')}, top={p.get('top_shape')}")

    print(f"\nSTL 输出目录: {out_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
