# -*- coding: utf-8 -*-
"""
测试唇釉瓶配合系统
验证：
1. 所有预设能够独立生成
2. 不同顺序生成组件时配合参数正确
3. 无 QC 硬约束失败
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from products.lip_gloss.components.registry import get_component, schema


def test_all_presets():
    """测试所有预设能够独立生成"""
    print("\n" + "=" * 60)
    print("测试 1: 所有预设独立生成")
    print("=" * 60)

    s = schema()
    products = s.get("products", [])

    all_passed = True

    for prod in products:
        prod_id = prod["id"]
        for comp in prod.get("components", []):
            comp_id = comp["id"]
            if not comp.get("enabled", False):
                print(f"  [SKIP] {prod_id}/{comp_id} - 未启用")
                continue

            presets = comp.get("style_presets", [])
            if not presets:
                print(f"  [WARN] {prod_id}/{comp_id} - 无预设")
                continue

            for preset in presets:
                preset_id = preset["id"]
                preset_name = preset.get("name", preset_id)

                try:
                    component = get_component(prod_id, comp_id)
                    result = component.generate(
                        preset_id=preset_id,
                        user_params={},
                        outroot=str(PROJECT_ROOT / "artifacts" / "test_fit")
                    )

                    qc = result.get("qc", {})
                    ok = result.get("ok", False)

                    if ok:
                        print(f"  [PASS] {comp_id}/{preset_name}")
                    else:
                        all_passed = False
                        error = result.get("error", "Unknown error")
                        print(f"  [FAIL] {comp_id}/{preset_name}: {error}")
                        # 打印失败的检查项
                        for check in qc.get("checks", []):
                            if not check.get("ok", True):
                                print(f"         - {check.get('id')}: {check.get('msg')}")

                except Exception as e:
                    all_passed = False
                    print(f"  [ERROR] {comp_id}/{preset_name}: {e}")

    return all_passed


def test_spec_18_415_flow():
    """测试 18-415 规格的完整生成流程"""
    print("\n" + "=" * 60)
    print("测试 2: 18-415 规格完整流程（bottle → wiper → wand → cap）")
    print("=" * 60)

    # 18-415 规格的标准配合参数
    SPEC_18_415 = {
        "bottle": {
            "neck_od_mm": 18.0,
            "thread.pitch_mm": 2.7,
            "thread.turns": 2,
        },
        "wiper": {
            "flange_od_mm": 17.0,
            "orifice_mm": 7.0,
        },
        "wand": {
            "thread.crest_dia_mm": 18.0,
            "thread.pitch_mm": 2.7,
            "thread.turns": 2,
            "stem_diameter_mm": 4.5,
        },
        "cap": {
            "inner_id_mm": 18.4,
            "thread.crest_dia_mm": 18.4,
            "thread.pitch_mm": 2.7,
            "thread.turns": 2,
            "seal.plug_od_mm": 6.0,
        },
    }

    outroot = str(PROJECT_ROOT / "artifacts" / "test_fit_flow")
    all_passed = True

    for comp_id in ["bottle", "wiper", "wand", "cap"]:
        try:
            component = get_component("lip_gloss", comp_id)
            # 使用默认预设 + 规格参数
            presets = component._style_presets() if hasattr(component, '_style_presets') else []
            preset_id = presets[0]["id"] if presets else None

            # 合并规格参数
            user_params = SPEC_18_415.get(comp_id, {}).copy()

            result = component.generate(
                preset_id=preset_id,
                user_params=user_params,
                outroot=outroot
            )

            ok = result.get("ok", False)
            qc = result.get("qc", {})

            if ok:
                print(f"  [PASS] {comp_id} (18-415)")
            else:
                all_passed = False
                error = result.get("error", "Unknown error")
                print(f"  [FAIL] {comp_id}: {error}")
                for check in qc.get("checks", []):
                    if not check.get("ok", True):
                        print(f"         - {check.get('id')}: {check.get('msg')}")

        except Exception as e:
            all_passed = False
            print(f"  [ERROR] {comp_id}: {e}")
            import traceback
            traceback.print_exc()

    return all_passed


def test_reverse_flow():
    """测试反向生成流程（cap 先）"""
    print("\n" + "=" * 60)
    print("测试 3: 反向流程（cap → wand → wiper → bottle）")
    print("=" * 60)

    SPEC_18_415 = {
        "bottle": {
            "neck_od_mm": 18.0,
            "thread.pitch_mm": 2.7,
            "thread.turns": 2,
        },
        "wiper": {
            "flange_od_mm": 17.0,
            "orifice_mm": 7.0,
        },
        "wand": {
            "thread.crest_dia_mm": 18.0,
            "thread.pitch_mm": 2.7,
            "thread.turns": 2,
            "stem_diameter_mm": 4.5,
        },
        "cap": {
            "inner_id_mm": 18.4,
            "thread.crest_dia_mm": 18.4,
            "thread.pitch_mm": 2.7,
            "thread.turns": 2,
            "seal.plug_od_mm": 6.0,
        },
    }

    outroot = str(PROJECT_ROOT / "artifacts" / "test_fit_reverse")
    all_passed = True

    # 反向顺序
    for comp_id in ["cap", "wand", "wiper", "bottle"]:
        try:
            component = get_component("lip_gloss", comp_id)
            presets = component._style_presets() if hasattr(component, '_style_presets') else []
            preset_id = presets[0]["id"] if presets else None

            user_params = SPEC_18_415.get(comp_id, {}).copy()

            result = component.generate(
                preset_id=preset_id,
                user_params=user_params,
                outroot=outroot
            )

            ok = result.get("ok", False)
            qc = result.get("qc", {})

            if ok:
                print(f"  [PASS] {comp_id} (18-415)")
            else:
                all_passed = False
                error = result.get("error", "Unknown error")
                print(f"  [FAIL] {comp_id}: {error}")
                for check in qc.get("checks", []):
                    if not check.get("ok", True):
                        print(f"         - {check.get('id')}: {check.get('msg')}")

        except Exception as e:
            all_passed = False
            print(f"  [ERROR] {comp_id}: {e}")

    return all_passed


def test_20_410_spec():
    """测试 20-410 规格"""
    print("\n" + "=" * 60)
    print("测试 4: 20-410 规格流程")
    print("=" * 60)

    # 20-410 规格的标准配合参数
    # bottle 和 wiper 支持 finish 参数，cap 和 wand 不支持
    SPEC_20_410 = {
        "bottle": {
            "neck_od_mm": 20.0,
            "thread.pitch_mm": 2.5,
            "thread.turns": 2,
            "finish": "20-410",  # bottle 支持 finish 参数
        },
        "wiper": {
            "flange_od_mm": 19.0,
            "outer_od_mm": 17.5,
            "orifice_mm": 8.0,
            "finish": "20-410",  # wiper 支持 finish 参数
        },
        "wand": {
            "thread.crest_dia_mm": 20.0,
            "thread.pitch_mm": 2.5,
            "thread.turns": 2,
            "stem_diameter_mm": 5.0,
            # wand 不支持 finish 参数
        },
        "cap": {
            "inner_id_mm": 20.4,
            "outer_od_mm": 26.0,  # 增大外径以适应更大的内径
            "thread.crest_dia_mm": 20.4,
            "thread.pitch_mm": 2.5,
            "thread.turns": 2,
            "seal.plug_od_mm": 7.0,
            # cap 不支持 finish 参数
        },
    }

    outroot = str(PROJECT_ROOT / "artifacts" / "test_fit_20_410")
    all_passed = True

    for comp_id in ["bottle", "wiper", "wand", "cap"]:
        try:
            component = get_component("lip_gloss", comp_id)
            presets = component._style_presets() if hasattr(component, '_style_presets') else []
            preset_id = presets[0]["id"] if presets else None

            user_params = SPEC_20_410.get(comp_id, {}).copy()

            result = component.generate(
                preset_id=preset_id,
                user_params=user_params,
                outroot=outroot
            )

            ok = result.get("ok", False)
            qc = result.get("qc", {})

            if ok:
                print(f"  [PASS] {comp_id} (20-410)")
            else:
                all_passed = False
                error = result.get("error", "Unknown error")
                print(f"  [FAIL] {comp_id}: {error}")
                for check in qc.get("checks", []):
                    if not check.get("ok", True):
                        print(f"         - {check.get('id')}: {check.get('msg')}")

        except Exception as e:
            all_passed = False
            print(f"  [ERROR] {comp_id}: {e}")

    return all_passed


def main():
    print("=" * 60)
    print("唇釉瓶配合系统测试")
    print("=" * 60)

    results = []

    # 测试 1: 所有预设独立生成
    results.append(("所有预设独立生成", test_all_presets()))

    # 测试 2: 18-415 正向流程
    results.append(("18-415 正向流程", test_spec_18_415_flow()))

    # 测试 3: 反向流程
    results.append(("反向流程", test_reverse_flow()))

    # 测试 4: 20-410 规格
    results.append(("20-410 规格", test_20_410_spec()))

    # 汇总
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("[SUCCESS] All tests passed!")
    else:
        print("[FAILED] Some tests failed, check errors above")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
