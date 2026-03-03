# -*- coding: utf-8 -*-
"""
穷举测试：跨组件约束系统鲁棒性验证

测试策略：
1. 4个组件的全排列 = 4! = 24 种生成顺序
2. 每种顺序中，每生成一个组件后检查对剩余组件的约束
3. 检查项：
   - 约束计算是否抛异常
   - 数值约束的 min <= max（无冲突）
   - 锁定参数的 default 在 [min, max] 范围内
   - 多源约束交集是否合理
   - 字符串约束（finish）是否正确传播

用法：
    python tests/lip_gloss/test_constraint_exhaustive.py
"""
from __future__ import annotations

import itertools
from typing import Any, Dict, List, Tuple

from conftest import (
    ALL_COMPONENTS, ALL_PARAM_SETS,
    get_state_manager,
)
from core.component_state import ComponentStateManager


# ============================================================
# 测试结果
# ============================================================

class TestResult:
    def __init__(self, order: Tuple[str, ...], param_set_name: str):
        self.order = order
        self.param_set_name = param_set_name
        self.steps: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.passed = True

    def add_error(self, msg: str):
        self.errors.append(msg)
        self.passed = False

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def order_str(self) -> str:
        return " → ".join(self.order)


# ============================================================
# 约束验证
# ============================================================

def validate_constraint(
    result: TestResult,
    step_idx: int,
    target_comp: str,
    param_key: str,
    info: Dict[str, Any],
    generated_so_far: List[str],
):
    """验证单个约束的合理性"""
    prefix = f"Step{step_idx+1}[{','.join(generated_so_far)}]→{target_comp}.{param_key}"

    # 字符串类约束（finish 等）
    if info.get("constrained_min") is None and info.get("constrained_max") is None:
        default = info.get("constrained_default")
        if default is None:
            result.add_error(f"{prefix}: 字符串约束 default 为 None")
        return

    c_min = info.get("constrained_min")
    c_max = info.get("constrained_max")
    c_default = info.get("constrained_default")
    conflict = info.get("conflict", False)

    # 检查 min/max 是否为数字
    if not isinstance(c_min, (int, float)):
        result.add_error(f"{prefix}: constrained_min={c_min} 不是数字")
        return
    if not isinstance(c_max, (int, float)):
        result.add_error(f"{prefix}: constrained_max={c_max} 不是数字")
        return

    # 检查范围合理性
    if c_min > c_max:
        if conflict:
            result.add_warning(f"{prefix}: 区间冲突 [{c_min}, {c_max}]（已标记 conflict=True）")
        else:
            result.add_error(f"{prefix}: min({c_min}) > max({c_max}) 但未标记 conflict!")

    # 检查 default 在范围内（允许微小浮点误差）
    if c_min <= c_max:
        if c_default is not None and isinstance(c_default, (int, float)):
            if c_default < c_min - 0.1 or c_default > c_max + 0.1:
                result.add_error(
                    f"{prefix}: default={c_default} 超出 [{c_min}, {c_max}]"
                )

    # 检查物理合理性：所有数值应 > 0（尺寸参数不可为负）
    if c_min < 0:
        result.add_warning(f"{prefix}: min={c_min} < 0（负值尺寸）")
    if c_max < 0:
        result.add_error(f"{prefix}: max={c_max} < 0（负值尺寸上限）")

    # 检查范围不能太窄（避免过度约束）
    if c_min <= c_max and (c_max - c_min) < 0.001 and not info.get("locked"):
        result.add_warning(f"{prefix}: 范围极窄 [{c_min}, {c_max}] 但未锁定")


def run_permutation_test(
    order: Tuple[str, ...],
    param_sets: Dict[str, Dict[str, Any]],
    param_set_name: str,
    global_rules: list,
) -> TestResult:
    """测试一种排列顺序"""
    result = TestResult(order, param_set_name)

    sm = ComponentStateManager()
    sm.register_cross_rules(global_rules)

    generated_so_far: List[str] = []

    for step_idx, comp in enumerate(order):
        params = param_sets[comp]
        sm.set_generated(comp, params)
        generated_so_far.append(comp)

        remaining = [c for c in ALL_COMPONENTS if c not in generated_so_far]

        step_info = {
            "generated": comp,
            "remaining": remaining,
            "constraints": {},
        }

        for target in remaining:
            try:
                constraints = sm.get_all_constraints_for_component(target)
            except Exception as e:
                result.add_error(
                    f"Step{step_idx+1} [{','.join(generated_so_far)}] "
                    f"→ get_constraints({target}) 抛异常: {type(e).__name__}: {e}"
                )
                continue

            step_info["constraints"][target] = constraints

            for param_key, info in constraints.items():
                validate_constraint(
                    result, step_idx, target, param_key, info, generated_so_far
                )

        result.steps.append(step_info)

    return result


# ============================================================
# 主测试入口
# ============================================================

def run_exhaustive_test(verbose: bool = True) -> bool:
    """
    运行全排列穷举测试。

    Returns: True 如果全部通过
    """
    global_rules = get_state_manager()._cross_rules

    all_results: List[TestResult] = []
    total_perms = 0
    total_errors = 0
    total_warnings = 0

    for set_name, param_sets in ALL_PARAM_SETS.items():
        if verbose:
            print(f"\n{'='*70}")
            print(f"  参数集: {set_name}")
            print(f"{'='*70}")

        for perm in itertools.permutations(ALL_COMPONENTS):
            result = run_permutation_test(perm, param_sets, set_name, global_rules)
            all_results.append(result)
            total_perms += 1

            if verbose:
                status = "PASS" if result.passed else "FAIL"
                warn_str = f" ({len(result.warnings)} warnings)" if result.warnings else ""
                err_str = f" ({len(result.errors)} errors)" if result.errors else ""
                print(f"  [{status}] {result.order_str()}{err_str}{warn_str}")

                if result.errors:
                    for e in result.errors:
                        print(f"    ERROR: {e}")
                    total_errors += len(result.errors)
                if result.warnings:
                    for w in result.warnings:
                        print(f"    WARN:  {w}")
                    total_warnings += len(result.warnings)
            else:
                total_errors += len(result.errors)
                total_warnings += len(result.warnings)

    # 汇总报告
    print(f"\n{'='*70}")
    print(f"  穷举测试汇总")
    print(f"{'='*70}")
    print(f"  参数集数:     {len(ALL_PARAM_SETS)}")
    print(f"  排列总数:     {total_perms}")
    print(f"  通过:         {sum(1 for r in all_results if r.passed)}")
    print(f"  失败:         {sum(1 for r in all_results if not r.passed)}")
    print(f"  错误总数:     {total_errors}")
    print(f"  警告总数:     {total_warnings}")

    # 按错误分类统计
    if total_errors > 0:
        print(f"\n  错误分类:")
        error_types: Dict[str, int] = {}
        for r in all_results:
            for e in r.errors:
                if "min(" in e and "> max(" in e:
                    key = "区间冲突未标记"
                elif "default=" in e and "超出" in e:
                    key = "default超出范围"
                elif "抛异常" in e:
                    key = "计算异常"
                elif "不是数字" in e:
                    key = "非数字类型"
                elif "负值" in e:
                    key = "负值尺寸"
                else:
                    key = "其他"
                error_types[key] = error_types.get(key, 0) + 1
        for k, v in sorted(error_types.items(), key=lambda x: -x[1]):
            print(f"    {k}: {v}")

    if total_warnings > 0:
        print(f"\n  警告分类:")
        warn_types: Dict[str, int] = {}
        for r in all_results:
            for w in r.warnings:
                if "区间冲突" in w:
                    key = "区间冲突(已标记)"
                elif "负值" in w:
                    key = "负值尺寸"
                elif "极窄" in w:
                    key = "范围极窄"
                else:
                    key = "其他"
                warn_types[key] = warn_types.get(key, 0) + 1
        for k, v in sorted(warn_types.items(), key=lambda x: -x[1]):
            print(f"    {k}: {v}")

    # 约束覆盖率分析
    if verbose:
        print(f"\n{'='*70}")
        print(f"  约束覆盖率分析（标准参数集）")
        print(f"{'='*70}")
        standard_results = [r for r in all_results if r.param_set_name == "标准(18-415)"]
        param_coverage: Dict[str, Dict[str, int]] = {}
        for r in standard_results:
            for step in r.steps:
                for target, constraints in step["constraints"].items():
                    for param_key in constraints:
                        param_coverage.setdefault(target, {})
                        param_coverage[target][param_key] = param_coverage[target].get(param_key, 0) + 1

        for comp in ALL_COMPONENTS:
            if comp in param_coverage:
                print(f"\n  {comp}:")
                for param, count in sorted(param_coverage[comp].items()):
                    print(f"    {param}: 被约束 {count} 次（跨 {len(standard_results)} 个排列）")

    return total_errors == 0


if __name__ == "__main__":
    import sys
    ok = run_exhaustive_test(verbose=True)
    print(f"\n  最终结果: {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)
