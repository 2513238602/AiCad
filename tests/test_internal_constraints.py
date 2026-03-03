#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
内部约束逻辑验证测试

模拟前端的内部约束检查逻辑，验证当修改某个参数时相关参数是否正确调整。
"""

import sys
import io

# 设置UTF-8输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def test_cap_internal_constraints():
    """测试 Cap 的内部约束"""
    print("\n" + "="*60)
    print("测试: Cap 内部约束")
    print("="*60)

    results = []

    # 内部约束定义（与 index.html 中一致）
    def calc_outer_od(inner_id_val, current_params):
        """当 inner_id 改变时，计算 outer_od"""
        current_outer_od = current_params.get("outer_od_mm", 20.0)
        min_wall = 0.8
        min_outer_od = inner_id_val + 2 * min_wall
        return current_outer_od if current_outer_od >= min_outer_od else min_outer_od

    # 测试场景1: inner_id 从 18.4 变为 19.0 (outer_od 24.0 足够)
    print("\n测试1: inner_id 18.4 → 19.0 (outer_od=24.0)")
    params = {"outer_od_mm": 24.0, "inner_id_mm": 18.4}
    new_inner_id = 19.0
    adjusted_outer = calc_outer_od(new_inner_id, params)
    wall_before = (params["outer_od_mm"] - new_inner_id) / 2
    wall_after = (adjusted_outer - new_inner_id) / 2

    print(f"  新 inner_id = {new_inner_id}")
    print(f"  当前 outer_od = {params['outer_od_mm']}")
    print(f"  调整后 outer_od = {adjusted_outer}")
    print(f"  壁厚变化: {wall_before:.2f}mm → {wall_after:.2f}mm")
    passed = wall_after >= 0.8 and adjusted_outer == params["outer_od_mm"]  # 不需要调整
    print(f"  结果: {'✓ 通过 (无需调整)' if passed else '✗ 失败'}")
    results.append(("不需要调整的场景", passed))

    # 测试场景2: inner_id 从 18.4 变为 22.5 (outer_od 24.0 不够)
    print("\n测试2: inner_id 18.4 → 22.5 (outer_od=24.0 不够)")
    params = {"outer_od_mm": 24.0, "inner_id_mm": 18.4}
    new_inner_id = 22.5
    adjusted_outer = calc_outer_od(new_inner_id, params)
    wall_with_old = (params["outer_od_mm"] - new_inner_id) / 2
    wall_with_new = (adjusted_outer - new_inner_id) / 2

    print(f"  新 inner_id = {new_inner_id}")
    print(f"  当前 outer_od = {params['outer_od_mm']}")
    print(f"  如果不调整: 壁厚 = {wall_with_old:.2f}mm (< 0.8mm，失败!)")
    print(f"  调整后 outer_od = {adjusted_outer}")
    print(f"  调整后壁厚 = {wall_with_new:.2f}mm")
    passed = wall_with_new >= 0.8 and adjusted_outer > params["outer_od_mm"]
    print(f"  结果: {'✓ 通过 (已自动调整)' if passed else '✗ 失败'}")
    results.append(("需要调整的场景", passed))

    # 测试场景3: inner_id 从 18.4 变为 23.5 (边界情况)
    print("\n测试3: inner_id 18.4 → 23.5 (边界情况)")
    params = {"outer_od_mm": 24.0, "inner_id_mm": 18.4}
    new_inner_id = 23.5
    min_outer_needed = new_inner_id + 2 * 0.8  # 25.1
    adjusted_outer = calc_outer_od(new_inner_id, params)
    wall_with_new = (adjusted_outer - new_inner_id) / 2

    print(f"  新 inner_id = {new_inner_id}")
    print(f"  理论需要 outer_od >= {min_outer_needed}")
    print(f"  调整后 outer_od = {adjusted_outer}")
    print(f"  调整后壁厚 = {wall_with_new:.2f}mm")
    passed = adjusted_outer >= min_outer_needed and wall_with_new >= 0.8
    print(f"  结果: {'✓ 通过' if passed else '✗ 失败'}")
    results.append(("边界情况", passed))

    return results


def test_fit_with_internal():
    """测试配合参数触发内部约束的完整流程"""
    print("\n" + "="*60)
    print("测试: 配合参数 + 内部约束完整流程")
    print("="*60)

    results = []

    # 场景：已生成刷杆 (outer_od_mm=20.0)，现在生成瓶盖
    # 配合约束：cap.inner_id > wand.outer_od + 0.3
    # 建议值：wand.outer_od + 0.5 = 20.5

    print("\n场景: 刷杆 outer_od=20.0mm，生成瓶盖")
    print("配合约束: cap.inner_id > wand.outer_od + 0.3")
    print("建议 inner_id = 20.0 + 0.5 = 20.5mm")

    # 瓶盖当前参数
    cap_params = {
        "outer_od_mm": 24.0,
        "inner_id_mm": 18.4,
        "height_mm": 25.0
    }

    # 应用配合参数
    suggested_inner_id = 20.5
    print(f"\n步骤1: 应用配合参数 inner_id = {suggested_inner_id}")

    # 计算内部约束调整
    min_wall = 0.8
    min_outer_od = suggested_inner_id + 2 * min_wall  # 22.1
    current_outer = cap_params["outer_od_mm"]

    print(f"步骤2: 检查内部约束")
    print(f"  当前 outer_od = {current_outer}")
    print(f"  最小需要 outer_od = {min_outer_od}")

    if current_outer >= min_outer_od:
        adjusted_outer = current_outer
        print(f"  无需调整: {current_outer} >= {min_outer_od}")
    else:
        adjusted_outer = min_outer_od
        print(f"  需要调整: {current_outer} → {adjusted_outer}")

    final_wall = (adjusted_outer - suggested_inner_id) / 2
    print(f"\n最终参数:")
    print(f"  outer_od_mm = {adjusted_outer}")
    print(f"  inner_id_mm = {suggested_inner_id}")
    print(f"  壁厚 = {final_wall:.2f}mm")

    passed = final_wall >= 0.8
    print(f"\n结果: {'✓ 通过' if passed else '✗ 失败'}")
    results.append(("刷杆→瓶盖配合+内部约束", passed))

    return results


def main():
    print("="*60)
    print("内部约束逻辑验证测试")
    print("="*60)

    all_results = []
    all_results.extend(test_cap_internal_constraints())
    all_results.extend(test_fit_with_internal())

    # 汇总
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)

    passed_count = sum(1 for _, ok in all_results if ok)
    failed_count = sum(1 for _, ok in all_results if not ok)

    print(f"{'测试项':<35} {'结果':<10}")
    print("-"*50)
    for name, ok in all_results:
        status = "✓ 通过" if ok else "✗ 失败"
        print(f"{name:<35} {status:<10}")
    print("-"*50)
    print(f"总计: {passed_count} 通过, {failed_count} 失败")

    if failed_count > 0:
        print("\n[失败] 部分测试未通过！")
        return False
    else:
        print("\n[成功] 所有测试通过！")
        return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
