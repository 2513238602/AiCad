#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
前端配合约束测试

模拟前端的约束检查逻辑，验证所有约束是否正确配置。
"""

import sys
import os
import math
import io

# 设置UTF-8输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def check_constraint(source_val, target_val, relation, offset=0, tolerance=0):
    """模拟前端的约束检查逻辑"""
    if relation == ">":
        return target_val > source_val + offset
    elif relation == "<":
        return target_val < source_val + offset
    elif relation == "≤":
        return target_val <= source_val + tolerance
    elif relation == "=":
        return target_val == source_val
    elif relation == "≈":
        return abs(target_val - source_val) <= tolerance
    return True


def test_cap_to_bottle_constraints():
    """测试 cap → bottle 的约束"""
    print("\n" + "="*60)
    print("测试: Cap → Bottle 约束")
    print("="*60)

    # Cap 默认参数
    cap_params = {
        "inner_id_mm": 18.4,
        "thread.pitch_mm": 2.7
    }

    # Bottle 默认参数
    bottle_params = {
        "neck_od_mm": 18.0,
        "thread.pitch_mm": 2.7
    }

    results = []

    # 约束1: inner_id_mm → neck_od_mm (≤, tolerance=0.4)
    # 检查: neck_od_mm <= inner_id_mm + 0.4
    source_val = cap_params["inner_id_mm"]
    target_val = bottle_params["neck_od_mm"]
    passed = check_constraint(source_val, target_val, "≤", tolerance=0.4)
    suggested = source_val - 0.4

    print(f"\n约束1: neck_od_mm ≤ inner_id_mm + 0.4")
    print(f"  Cap inner_id_mm = {source_val}")
    print(f"  Bottle neck_od_mm = {target_val}")
    print(f"  检查: {target_val} <= {source_val + 0.4} = {passed}")
    print(f"  建议值: {suggested}")
    print(f"  结果: {'✓ 通过' if passed else '✗ 失败'}")
    results.append(("neck_od_mm ≤ inner_id_mm + 0.4", passed))

    # 约束2: thread.pitch_mm → thread.pitch_mm (=)
    source_val = cap_params["thread.pitch_mm"]
    target_val = bottle_params["thread.pitch_mm"]
    passed = check_constraint(source_val, target_val, "=")

    print(f"\n约束2: thread.pitch_mm = thread.pitch_mm")
    print(f"  Cap pitch = {source_val}")
    print(f"  Bottle pitch = {target_val}")
    print(f"  检查: {target_val} == {source_val} = {passed}")
    print(f"  结果: {'✓ 通过' if passed else '✗ 失败'}")
    results.append(("thread.pitch_mm = pitch", passed))

    return results


def test_bottle_to_wand_constraints():
    """测试 bottle → wand 的约束"""
    print("\n" + "="*60)
    print("测试: Bottle → Wand 约束")
    print("="*60)

    # Bottle 默认参数
    bottle_params = {
        "neck_od_mm": 18.0,
        "thread.pitch_mm": 2.7,
        "thread.turns": 2
    }

    # Wand 默认参数
    wand_params = {
        "thread.crest_dia_mm": 18.0,
        "thread.pitch_mm": 2.7,
        "thread.turns": 2
    }

    results = []

    # 约束1: neck_od_mm → thread.crest_dia_mm (≈, tolerance=0.5)
    source_val = bottle_params["neck_od_mm"]
    target_val = wand_params["thread.crest_dia_mm"]
    passed = check_constraint(source_val, target_val, "≈", tolerance=0.5)

    print(f"\n约束1: crest_dia_mm ≈ neck_od_mm (±0.5)")
    print(f"  Bottle neck_od = {source_val}")
    print(f"  Wand crest_dia = {target_val}")
    print(f"  检查: |{target_val} - {source_val}| = {abs(target_val - source_val)} <= 0.5 = {passed}")
    print(f"  结果: {'✓ 通过' if passed else '✗ 失败'}")
    results.append(("crest_dia_mm ≈ neck_od_mm", passed))

    # 约束2: thread.pitch_mm = thread.pitch_mm
    source_val = bottle_params["thread.pitch_mm"]
    target_val = wand_params["thread.pitch_mm"]
    passed = check_constraint(source_val, target_val, "=")

    print(f"\n约束2: thread.pitch_mm = thread.pitch_mm")
    print(f"  Bottle pitch = {source_val}")
    print(f"  Wand pitch = {target_val}")
    print(f"  结果: {'✓ 通过' if passed else '✗ 失败'}")
    results.append(("thread.pitch_mm = pitch", passed))

    # 约束3: thread.turns = thread.turns
    source_val = bottle_params["thread.turns"]
    target_val = wand_params["thread.turns"]
    passed = check_constraint(source_val, target_val, "=")

    print(f"\n约束3: thread.turns = thread.turns")
    print(f"  Bottle turns = {source_val}")
    print(f"  Wand turns = {target_val}")
    print(f"  结果: {'✓ 通过' if passed else '✗ 失败'}")
    results.append(("thread.turns = turns", passed))

    return results


def test_wand_to_wiper_constraints():
    """测试 wand → wiper 的约束"""
    print("\n" + "="*60)
    print("测试: Wand → Wiper 约束")
    print("="*60)

    # Wand 默认参数
    wand_params = {
        "stem_diameter_mm": 4.0
    }

    # Wiper 默认参数
    wiper_params = {
        "orifice_mm": 7.0
    }

    results = []

    # 约束: orifice_mm > stem_diameter_mm + 1.0
    source_val = wand_params["stem_diameter_mm"]
    target_val = wiper_params["orifice_mm"]
    passed = check_constraint(source_val, target_val, ">", offset=1.0)
    suggested = source_val + 2.0

    print(f"\n约束: orifice_mm > stem_diameter_mm + 1.0")
    print(f"  Wand stem_diameter = {source_val}")
    print(f"  Wiper orifice = {target_val}")
    print(f"  检查: {target_val} > {source_val + 1.0} = {passed}")
    print(f"  建议值: {suggested}")
    print(f"  结果: {'✓ 通过' if passed else '✗ 失败'}")
    results.append(("orifice_mm > stem_diameter + 1", passed))

    return results


def test_edge_cases():
    """测试边界情况"""
    print("\n" + "="*60)
    print("测试: 边界情况")
    print("="*60)

    results = []

    # 测试1: 当前值等于建议值的情况
    print("\n测试1: 当前值 = 建议值")
    source_val = 18.4  # cap inner_id
    target_val = 18.0  # bottle neck_od
    suggested = source_val - 0.4  # 18.0
    passed = check_constraint(source_val, target_val, "≤", tolerance=0.4)

    print(f"  source (inner_id) = {source_val}")
    print(f"  current (neck_od) = {target_val}")
    print(f"  suggested = {suggested}")
    print(f"  current == suggested: {target_val == suggested}")
    print(f"  约束满足: {passed}")
    print(f"  应该显示提示: {'否' if (target_val == suggested and passed) else '是'}")
    results.append(("当前值=建议值且约束满足", target_val == suggested and passed))

    # 测试2: 15mm 小规格
    print("\n测试2: 15mm 小规格")
    source_val = 15.4  # cap inner_id
    target_val = 15.0  # bottle neck_od
    passed = check_constraint(source_val, target_val, "≤", tolerance=0.4)

    print(f"  source (inner_id) = {source_val}")
    print(f"  current (neck_od) = {target_val}")
    print(f"  检查: {target_val} <= {source_val + 0.4} = {passed}")
    results.append(("15mm规格约束检查", passed))

    # 测试3: 20mm 大规格
    print("\n测试3: 20mm 大规格")
    source_val = 20.4  # cap inner_id
    target_val = 20.0  # bottle neck_od
    passed = check_constraint(source_val, target_val, "≤", tolerance=0.4)

    print(f"  source (inner_id) = {source_val}")
    print(f"  current (neck_od) = {target_val}")
    print(f"  检查: {target_val} <= {source_val + 0.4} = {passed}")
    results.append(("20mm规格约束检查", passed))

    return results


def main():
    print("="*60)
    print("前端配合约束测试")
    print("="*60)

    all_results = []

    all_results.extend(test_cap_to_bottle_constraints())
    all_results.extend(test_bottle_to_wand_constraints())
    all_results.extend(test_wand_to_wiper_constraints())
    all_results.extend(test_edge_cases())

    # 汇总
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)

    passed = sum(1 for _, ok in all_results if ok)
    failed = sum(1 for _, ok in all_results if not ok)

    print(f"{'约束':<40} {'结果':<10}")
    print("-"*50)
    for name, ok in all_results:
        status = "✓ 通过" if ok else "✗ 失败"
        print(f"{name:<40} {status:<10}")
    print("-"*50)
    print(f"总计: {passed} 通过, {failed} 失败")

    if failed > 0:
        print("\n[失败] 部分约束检查未通过！")
        return False
    else:
        print("\n[成功] 所有约束检查通过！")
        return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
