# -*- coding: utf-8 -*-
"""
全面排列组合测试
测试所有可能的组件生成顺序和组合，验证：
1. 任何顺序都能成功生成
2. 任何子集都能成功生成
3. 默认预设参数能够正确装配
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from products.lip_gloss.components.registry import get_component
1

# 所有组件
ALL_COMPONENTS = ["bottle", "wiper", "wand", "cap"]


def generate_component(comp_id: str, outroot: str) -> dict:
    """生成单个组件并返回结果"""
    component = get_component("lip_gloss", comp_id)
    presets = component._style_presets()
    preset_id = presets[0]["id"] if presets else None

    result = component.generate(
        preset_id=preset_id,
        user_params={},
        outroot=outroot
    )
    return result


def test_single_component():
    """测试1: 单个组件生成"""
    print("\n" + "=" * 70)
    print("TEST 1: Single Component Generation")
    print("=" * 70)

    outroot = str(PROJECT_ROOT / "artifacts" / "test_combo_single")
    all_passed = True

    for comp_id in ALL_COMPONENTS:
        result = generate_component(comp_id, outroot)
        ok = result.get("ok", False)
        if ok:
            print(f"  [PASS] {comp_id}")
        else:
            all_passed = False
            print(f"  [FAIL] {comp_id}: {result.get('error', 'Unknown')}")

    return all_passed


def test_all_pairs():
    """测试2: 所有两两组合"""
    print("\n" + "=" * 70)
    print("TEST 2: All Pairs (2 components)")
    print("=" * 70)

    all_passed = True

    # 所有2个组件的排列（顺序敏感）
    pairs = list(itertools.permutations(ALL_COMPONENTS, 2))
    print(f"  Testing {len(pairs)} pairs...")

    for pair in pairs:
        outroot = str(PROJECT_ROOT / "artifacts" / f"test_combo_pair_{pair[0]}_{pair[1]}")
        pair_ok = True

        for comp_id in pair:
            result = generate_component(comp_id, outroot)
            if not result.get("ok", False):
                pair_ok = False
                print(f"  [FAIL] {' -> '.join(pair)}: {comp_id} failed - {result.get('error', '')[:50]}")
                break

        if pair_ok:
            print(f"  [PASS] {' -> '.join(pair)}")
        else:
            all_passed = False

    return all_passed


def test_all_triples():
    """测试3: 所有三组件组合"""
    print("\n" + "=" * 70)
    print("TEST 3: All Triples (3 components)")
    print("=" * 70)

    all_passed = True

    # 所有3个组件的排列
    triples = list(itertools.permutations(ALL_COMPONENTS, 3))
    print(f"  Testing {len(triples)} triples...")

    for triple in triples:
        outroot = str(PROJECT_ROOT / "artifacts" / f"test_combo_triple_{'_'.join(triple)}")
        triple_ok = True

        for comp_id in triple:
            result = generate_component(comp_id, outroot)
            if not result.get("ok", False):
                triple_ok = False
                print(f"  [FAIL] {' -> '.join(triple)}: {comp_id} failed - {result.get('error', '')[:50]}")
                break

        if triple_ok:
            print(f"  [PASS] {' -> '.join(triple)}")
        else:
            all_passed = False

    return all_passed


def test_all_four():
    """测试4: 所有四组件排列"""
    print("\n" + "=" * 70)
    print("TEST 4: All Four Components (all orders)")
    print("=" * 70)

    all_passed = True

    # 所有4个组件的排列
    quads = list(itertools.permutations(ALL_COMPONENTS, 4))
    print(f"  Testing {len(quads)} permutations...")

    for quad in quads:
        outroot = str(PROJECT_ROOT / "artifacts" / f"test_combo_quad_{'_'.join(quad)}")
        quad_ok = True

        for comp_id in quad:
            result = generate_component(comp_id, outroot)
            if not result.get("ok", False):
                quad_ok = False
                print(f"  [FAIL] {' -> '.join(quad)}: {comp_id} failed - {result.get('error', '')[:50]}")
                break

        if quad_ok:
            print(f"  [PASS] {' -> '.join(quad)}")
        else:
            all_passed = False

    return all_passed


def test_specific_assembly_scenarios():
    """测试5: 特定装配场景"""
    print("\n" + "=" * 70)
    print("TEST 5: Specific Assembly Scenarios")
    print("=" * 70)

    all_passed = True

    scenarios = [
        # 场景名, 组件列表
        ("Bottle + Cap (no wand)", ["bottle", "cap"]),
        ("Bottle + Wiper + Wand", ["bottle", "wiper", "wand"]),
        ("Cap + Wand (套装)", ["cap", "wand"]),
        ("Wiper + Wand (穿孔配合)", ["wiper", "wand"]),
        ("Full Assembly (标准顺序)", ["bottle", "wiper", "wand", "cap"]),
        ("Full Assembly (反向)", ["cap", "wand", "wiper", "bottle"]),
    ]

    for scenario_name, components in scenarios:
        outroot = str(PROJECT_ROOT / "artifacts" / f"test_scenario_{scenario_name.replace(' ', '_')}")
        scenario_ok = True

        for comp_id in components:
            result = generate_component(comp_id, outroot)
            if not result.get("ok", False):
                scenario_ok = False
                print(f"  [FAIL] {scenario_name}: {comp_id} failed")
                break

        if scenario_ok:
            print(f"  [PASS] {scenario_name}")
        else:
            all_passed = False

    return all_passed


def main():
    print("=" * 70)
    print("COMPREHENSIVE COMBINATION TEST")
    print("Testing all possible component generation orders and combinations")
    print("=" * 70)

    results = []

    results.append(("Single Components", test_single_component()))
    results.append(("All Pairs", test_all_pairs()))
    results.append(("All Triples", test_all_triples()))
    results.append(("All Four (24 permutations)", test_all_four()))
    results.append(("Specific Scenarios", test_specific_assembly_scenarios()))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total_tests = len(results)
    passed_tests = sum(1 for _, passed in results if passed)

    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

    print("\n" + "=" * 70)
    print(f"Results: {passed_tests}/{total_tests} test groups passed")

    if passed_tests == total_tests:
        print("[SUCCESS] ALL TESTS PASSED!")
        print("All component combinations can be generated successfully.")
    else:
        print("[FAILED] Some tests failed. Check above for details.")
    print("=" * 70)

    return 0 if passed_tests == total_tests else 1


if __name__ == "__main__":
    sys.exit(main())
