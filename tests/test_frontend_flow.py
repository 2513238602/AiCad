# -*- coding: utf-8 -*-
"""
模拟前端工作流测试
验证用户在 Web UI 中的典型操作流程能够正常工作
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from products.lip_gloss.components.registry import get_component


def simulate_frontend_flow_1():
    """
    流程 1: 用户按顺序生成所有组件（使用默认预设）
    bottle -> wiper -> wand -> cap
    """
    print("\n" + "=" * 60)
    print("Frontend Flow 1: Sequential Generation (Default Presets)")
    print("bottle -> wiper -> wand -> cap")
    print("=" * 60)

    outroot = str(PROJECT_ROOT / "artifacts" / "test_frontend_1")
    all_passed = True

    # 模拟前端的 sessionFinishSpec（默认 18-415）
    session_spec = "18-415"

    for comp_id in ["bottle", "wiper", "wand", "cap"]:
        try:
            component = get_component("lip_gloss", comp_id)
            presets = component._style_presets()
            preset_id = presets[0]["id"] if presets else None

            # 使用默认预设，不传额外参数（模拟用户直接点击生成）
            result = component.generate(
                preset_id=preset_id,
                user_params={},
                outroot=outroot
            )

            if result.get("ok", False):
                print(f"  [PASS] {comp_id} generated successfully")
            else:
                all_passed = False
                error = result.get("error", "Unknown error")
                print(f"  [FAIL] {comp_id}: {error}")

        except Exception as e:
            all_passed = False
            print(f"  [ERROR] {comp_id}: {e}")

    return all_passed


def simulate_frontend_flow_2():
    """
    流程 2: 用户从瓶盖开始生成（模拟先设计瓶盖的场景）
    cap -> wand -> bottle -> wiper
    """
    print("\n" + "=" * 60)
    print("Frontend Flow 2: Start from Cap (Alternative Order)")
    print("cap -> wand -> bottle -> wiper")
    print("=" * 60)

    outroot = str(PROJECT_ROOT / "artifacts" / "test_frontend_2")
    all_passed = True

    for comp_id in ["cap", "wand", "bottle", "wiper"]:
        try:
            component = get_component("lip_gloss", comp_id)
            presets = component._style_presets()
            preset_id = presets[0]["id"] if presets else None

            result = component.generate(
                preset_id=preset_id,
                user_params={},
                outroot=outroot
            )

            if result.get("ok", False):
                print(f"  [PASS] {comp_id} generated successfully")
            else:
                all_passed = False
                error = result.get("error", "Unknown error")
                print(f"  [FAIL] {comp_id}: {error}")

        except Exception as e:
            all_passed = False
            print(f"  [ERROR] {comp_id}: {e}")

    return all_passed


def simulate_frontend_flow_3():
    """
    流程 3: 用户只生成部分组件（2个组件）
    bottle + cap 配合
    """
    print("\n" + "=" * 60)
    print("Frontend Flow 3: Partial Assembly (Bottle + Cap only)")
    print("=" * 60)

    outroot = str(PROJECT_ROOT / "artifacts" / "test_frontend_3")
    all_passed = True

    for comp_id in ["bottle", "cap"]:
        try:
            component = get_component("lip_gloss", comp_id)
            presets = component._style_presets()
            preset_id = presets[0]["id"] if presets else None

            result = component.generate(
                preset_id=preset_id,
                user_params={},
                outroot=outroot
            )

            if result.get("ok", False):
                print(f"  [PASS] {comp_id} generated successfully")
            else:
                all_passed = False
                error = result.get("error", "Unknown error")
                print(f"  [FAIL] {comp_id}: {error}")

        except Exception as e:
            all_passed = False
            print(f"  [ERROR] {comp_id}: {e}")

    return all_passed


def simulate_frontend_flow_4():
    """
    流程 4: 用户切换预设后重新生成
    先用标准预设，再切换到其他预设
    """
    print("\n" + "=" * 60)
    print("Frontend Flow 4: Preset Switching")
    print("cap (standard) -> cap (dome) -> bottle (standard)")
    print("=" * 60)

    outroot = str(PROJECT_ROOT / "artifacts" / "test_frontend_4")
    all_passed = True

    # 生成标准瓶盖
    try:
        cap = get_component("lip_gloss", "cap")
        result = cap.generate(
            preset_id="cap_18415_standard",
            user_params={},
            outroot=outroot
        )
        if result.get("ok", False):
            print("  [PASS] cap (standard preset)")
        else:
            all_passed = False
            print(f"  [FAIL] cap (standard): {result.get('error')}")
    except Exception as e:
        all_passed = False
        print(f"  [ERROR] cap (standard): {e}")

    # 切换到圆顶瓶盖预设
    try:
        result = cap.generate(
            preset_id="cap_18415_dome",
            user_params={},
            outroot=outroot
        )
        if result.get("ok", False):
            print("  [PASS] cap (dome preset)")
        else:
            all_passed = False
            print(f"  [FAIL] cap (dome): {result.get('error')}")
    except Exception as e:
        all_passed = False
        print(f"  [ERROR] cap (dome): {e}")

    # 生成瓶身
    try:
        bottle = get_component("lip_gloss", "bottle")
        result = bottle.generate(
            preset_id="bottle_standard_5ml",
            user_params={},
            outroot=outroot
        )
        if result.get("ok", False):
            print("  [PASS] bottle (standard preset)")
        else:
            all_passed = False
            print(f"  [FAIL] bottle: {result.get('error')}")
    except Exception as e:
        all_passed = False
        print(f"  [ERROR] bottle: {e}")

    return all_passed


def simulate_frontend_flow_5():
    """
    流程 5: 用户修改参数后生成（模拟调整外径等）
    """
    print("\n" + "=" * 60)
    print("Frontend Flow 5: Parameter Modification")
    print("bottle with custom height -> cap with default")
    print("=" * 60)

    outroot = str(PROJECT_ROOT / "artifacts" / "test_frontend_5")
    all_passed = True

    # 生成自定义高度的瓶身
    try:
        bottle = get_component("lip_gloss", "bottle")
        result = bottle.generate(
            preset_id="bottle_standard_5ml",
            user_params={"height_mm": 85.0, "inner_depth_mm": 65.0},  # 更高的瓶子
            outroot=outroot
        )
        if result.get("ok", False):
            print("  [PASS] bottle (height=85mm)")
        else:
            all_passed = False
            print(f"  [FAIL] bottle: {result.get('error')}")
    except Exception as e:
        all_passed = False
        print(f"  [ERROR] bottle: {e}")

    # 生成瓶盖（应该使用默认预设）
    try:
        cap = get_component("lip_gloss", "cap")
        result = cap.generate(
            preset_id="cap_18415_standard",
            user_params={},
            outroot=outroot
        )
        if result.get("ok", False):
            print("  [PASS] cap (default)")
        else:
            all_passed = False
            print(f"  [FAIL] cap: {result.get('error')}")
    except Exception as e:
        all_passed = False
        print(f"  [ERROR] cap: {e}")

    return all_passed


def main():
    print("=" * 60)
    print("Frontend Workflow Simulation Tests")
    print("=" * 60)

    results = []

    results.append(("Flow 1: Sequential Generation", simulate_frontend_flow_1()))
    results.append(("Flow 2: Alternative Order", simulate_frontend_flow_2()))
    results.append(("Flow 3: Partial Assembly", simulate_frontend_flow_3()))
    results.append(("Flow 4: Preset Switching", simulate_frontend_flow_4()))
    results.append(("Flow 5: Parameter Modification", simulate_frontend_flow_5()))

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("[SUCCESS] All frontend flow tests passed!")
    else:
        print("[FAILED] Some tests failed")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
