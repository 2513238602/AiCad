# -*- coding: utf-8 -*-
"""
集成测试：3D 模型几何正确性

验证不同参数组合下瓶身 3D 模型无镂空/体积异常。

用法：
    python tests/lip_gloss/test_geometry.py
"""
from __future__ import annotations

import math


def run_geometry_test() -> bool:
    """测试瓶身 3D 几何正确性"""
    try:
        import cadquery as cq  # noqa: F401
    except ImportError:
        print(f"\n{'='*70}")
        print(f"  集成测试: 3D几何 - 跳过（CadQuery 未安装）")
        print(f"{'='*70}")
        return True

    from core.modeler import Modeler

    print(f"\n{'='*70}")
    print(f"  集成测试: 3D 模型几何正确性")
    print(f"{'='*70}")

    modeler = Modeler()
    errors = []

    test_cases = [
        ("标准 24/18", {"body_od_mm": 24.0, "neck_od_mm": 18.0, "wall_thickness_mm": 1.2}),
        ("大差值 30/18", {"body_od_mm": 30.0, "neck_od_mm": 18.0, "wall_thickness_mm": 1.2}),
        ("极端 35/18", {"body_od_mm": 35.0, "neck_od_mm": 18.0, "wall_thickness_mm": 1.2}),
        ("小瓶 16/13", {"body_od_mm": 16.0, "neck_od_mm": 13.0, "wall_thickness_mm": 1.0}),
        ("等径 20/20", {"body_od_mm": 20.0, "neck_od_mm": 20.0, "wall_thickness_mm": 1.2}),
    ]

    base_params = {
        "height_mm": 70.0,
        "shape": "cyl",
        "taper_deg": 0.0,
        "neck_height_mm": 10.0,
        "lip_thickness_mm": 1.0,
        "thread": {"enabled": False},
        "shoulder_height_mm": 10.0,
        "shoulder_style": "round",
        "shoulder_fillet_mm": 3.0,
        "inner_depth_mm": 50.0,
        "bottom_thickness_mm": 2.0,
        "bottom_style": "flat",
        "bottom_concave_mm": 0.0,
        "bottom_fillet_mm": 1.5,
    }

    for name, overrides in test_cases:
        params = {**base_params, **overrides}
        body_od = params["body_od_mm"]
        neck_od = params["neck_od_mm"]
        wall = params["wall_thickness_mm"]
        inner_r_body = (body_od - 2 * wall) / 2
        neck_r = neck_od / 2
        is_hollow_scenario = inner_r_body > neck_r

        meta = {"features": {}}
        try:
            result = modeler.build_bottle(params, meta)
            vol = result.val().Volume()

            if vol < 1.0:
                errors.append(f"{name}: 体积异常小 ({vol:.1f} mm³)")
                continue

            outer_vol = math.pi * (body_od / 2) ** 2 * params["height_mm"]
            if vol > outer_vol * 1.05:
                errors.append(f"{name}: 体积 ({vol:.0f}) > 外包体积 ({outer_vol:.0f})")
                continue

            ratio = vol / outer_vol
            if ratio < 0.05 or ratio > 0.90:
                errors.append(f"{name}: 体积比异常 {ratio:.1%}")
                continue

            hollow_tag = " [HOLLOW_SCENARIO]" if is_hollow_scenario else ""
            print(f"  [{name}] vol={vol:.0f}mm³, ratio={ratio:.1%}{hollow_tag} [OK]")

        except Exception as e:
            errors.append(f"{name}: 构建失败 - {e}")

    if errors:
        print(f"\n  [FAIL] 3D 模型几何测试失败:")
        for e in errors:
            print(f"    ERROR: {e}")
        return False
    else:
        print(f"\n  [PASS] 3D 模型几何测试通过")
        return True


if __name__ == "__main__":
    import sys
    ok = run_geometry_test()
    sys.exit(0 if ok else 1)
