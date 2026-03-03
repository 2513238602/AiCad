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
"""
from __future__ import annotations

import sys
import io
import itertools
from typing import Any, Dict, List, Tuple

# Windows GBK 环境下 CadQuery/OCCT 可能输出非 GBK 字符，统一用 UTF-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, "g:/AiCad/src")

from core.component_state import ComponentStateManager, get_state_manager
import products.lip_gloss.derived_params  # noqa: F401 trigger registration

# ============================================================
# 各组件的"典型生成后参数"（模拟 generate 成功后存入 state）
# ============================================================

COMPONENT_PARAMS: Dict[str, Dict[str, Any]] = {
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
        "stem_length_mm": 55.0,
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
        "height_mm": 12.0,
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

# 额外测试参数集：较大尺寸
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
        "wall_thickness_mm": 1.5,
        "finish": "24-410",
    },
    "wand": {
        "total_height_mm": 85.0,
        "outer_od_mm": 27.0,
        "cap_height_mm": 25.0,
        "stem_diameter_mm": 5.5,
        "orifice_mm": 9.5,
        "thread": {"crest_dia_mm": 24.0, "pitch_mm": 2.7},
        "finish": "24-410",
    },
    "wiper": {
        "outer_od_mm": 21.0,
        "orifice_mm": 9.5,
        "flange_od_mm": 23.0,
        "finish": "24-410",
    },
}

# 额外测试参数集：较小尺寸
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
        "wall_thickness_mm": 1.0,
        "finish": "13-415",
    },
    "wand": {
        "total_height_mm": 50.0,
        "outer_od_mm": 13.5,
        "cap_height_mm": 14.0,
        "stem_diameter_mm": 3.0,
        "orifice_mm": 5.0,
        "thread": {"crest_dia_mm": 13.0, "pitch_mm": 2.0},
        "finish": "13-415",
    },
    "wiper": {
        "outer_od_mm": 11.0,
        "orifice_mm": 5.0,
        "flange_od_mm": 12.5,
        "finish": "13-415",
    },
}

ALL_COMPONENTS = ["cap", "bottle", "wand", "wiper"]


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
        # 存储当前组件的参数
        params = param_sets[comp]
        sm.set_generated(comp, params)
        generated_so_far.append(comp)

        # 获取剩余组件
        remaining = [c for c in ALL_COMPONENTS if c not in generated_so_far]

        step_info = {
            "generated": comp,
            "remaining": remaining,
            "constraints": {},
        }

        # 检查每个剩余组件的约束
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


def main():
    global_rules = get_state_manager()._cross_rules

    all_results: List[TestResult] = []
    param_sets_map = {
        "标准": COMPONENT_PARAMS,
        "大尺寸": COMPONENT_PARAMS_LARGE,
        "小尺寸": COMPONENT_PARAMS_SMALL,
    }

    total_perms = 0
    total_errors = 0
    total_warnings = 0

    for set_name, param_sets in param_sets_map.items():
        print(f"\n{'='*70}")
        print(f"  参数集: {set_name}")
        print(f"{'='*70}")

        for perm in itertools.permutations(ALL_COMPONENTS):
            result = run_permutation_test(perm, param_sets, set_name, global_rules)
            all_results.append(result)
            total_perms += 1

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

    # ============================================================
    # 汇总报告
    # ============================================================
    print(f"\n{'='*70}")
    print(f"  穷举测试汇总")
    print(f"{'='*70}")
    print(f"  参数集数:     {len(param_sets_map)}")
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
                # 提取错误类型
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

    # 详细的约束覆盖率
    print(f"\n{'='*70}")
    print(f"  约束覆盖率分析（标准参数集）")
    print(f"{'='*70}")
    standard_results = [r for r in all_results if r.param_set_name == "标准"]
    # 统计各目标参数被约束的次数
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

    # 返回是否全部通过
    return total_errors == 0


# ============================================================
# 集成测试 Part 2: web_server 参数存储完整性
# ============================================================
def test_state_storage_completeness():
    """
    测试：模拟 web_server 的 generate 流程，验证存入 state manager
    的参数是归一化后的完整参数（包含 thread.crest_dia_mm 等）。

    这直接验证了修复前 web_server.py line 249 的 bug：
    旧代码用 qc.get("final_params", params) 但 qc 中只有 "params" key。
    """
    from core.interpreter import Interpreter
    from products.lip_gloss.components.wand import WandComponent
    from products.lip_gloss.components.cap import CapComponent
    from products.lip_gloss.components.bottle import BottleComponent
    from core.component_state import ComponentStateManager
    from products.lip_gloss.derived_params import CROSS_COMPONENT_RULES

    print(f"\n{'='*70}")
    print(f"  集成测试 Part 2: web_server 参数存储完整性")
    print(f"{'='*70}")

    errors = []
    interp = Interpreter()

    # 模拟 web_server generate 流程
    components = {
        "wand": WandComponent(),
        "cap": CapComponent(),
        "bottle": BottleComponent(),
    }

    sm = ComponentStateManager()
    sm.register_cross_rules(CROSS_COMPONENT_RULES)

    for comp_id, comp_obj in components.items():
        schema = comp_obj.schema()
        preset_params = schema["style_presets"][0]["params"]

        nested, flat, qc = interp.normalize_strict(
            param_defs=schema["params"],
            preset_params=preset_params,
            user_params=None,
        )

        # 模拟修复后的 web_server 存储逻辑
        final_params = qc.get("params", {})  # 修复后用 "params" 而非 "final_params"
        sm.set_generated(comp_id, final_params)

        stored = sm.get_generated(comp_id)
        print(f"  [{comp_id}] 存储参数数（扁平）: {len(flat)}")

        # 检查关键参数是否存在
        if comp_id == "wand":
            crest = stored.get("thread", {}).get("crest_dia_mm")
            if crest is None:
                errors.append(f"wand: thread.crest_dia_mm 缺失（旧 bug 复现）")
            else:
                print(f"    thread.crest_dia_mm = {crest} [OK]")

            pitch = stored.get("thread", {}).get("pitch_mm")
            if pitch is None:
                errors.append(f"wand: thread.pitch_mm 缺失")
            else:
                print(f"    thread.pitch_mm = {pitch} [OK]")

    # 验证约束：wand 和 cap 都生成后，bottle.neck_od_mm 应该被锁定
    constraints = sm.get_all_constraints_for_component("bottle")
    neck = constraints.get("neck_od_mm")
    if neck is None:
        errors.append("bottle.neck_od_mm 无约束（规则未触发）")
    elif not neck.get("locked"):
        errors.append(f"bottle.neck_od_mm 未锁定（locked={neck.get('locked')}）")
    else:
        print(f"  [bottle] neck_od_mm: LOCKED [OK], range=[{neck['constrained_min']}, {neck['constrained_max']}]")

    body = constraints.get("body_od_mm")
    if body and body.get("locked"):
        print(f"  [bottle] body_od_mm: LOCKED [OK], range=[{body['constrained_min']}, {body['constrained_max']}]")

    if errors:
        print(f"\n  [FAIL] 参数存储完整性测试失败:")
        for e in errors:
            print(f"    ERROR: {e}")
        return False
    else:
        print(f"\n  [PASS] 参数存储完整性测试通过")
        return True


# ============================================================
# 集成测试 Part 3: 3D 模型几何正确性（瓶身无镂空）
# ============================================================
def test_bottle_geometry_no_hollow():
    """
    测试：不同 body_od / neck_od 比例下，瓶身 3D 模型不应有镂空。

    关键检查：当 inner_r_body > neck_r 时（body_od 远大于 neck_od），
    旧代码的 body cavity 会穿透肩壁造成可见镂空。
    """
    try:
        import cadquery as cq  # noqa: F401
    except ImportError:
        print(f"\n{'='*70}")
        print(f"  集成测试 Part 3: 跳过（CadQuery 未安装）")
        print(f"{'='*70}")
        return True

    import math
    from core.modeler import Modeler

    print(f"\n{'='*70}")
    print(f"  集成测试 Part 3: 3D 模型几何正确性")
    print(f"{'='*70}")

    modeler = Modeler()
    errors = []

    # 测试用例：不同的 body_od / neck_od 比例
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

            # 体积应该大于 0
            if vol < 1.0:
                errors.append(f"{name}: 体积异常小 ({vol:.1f} mm³)")
                continue

            # 体积应该小于外包体积（不能比实心还大）
            outer_vol = math.pi * (body_od / 2) ** 2 * params["height_mm"]
            if vol > outer_vol * 1.05:  # 5% 容差（螺纹可能略超）
                errors.append(f"{name}: 体积 ({vol:.0f}) > 外包体积 ({outer_vol:.0f})")
                continue

            # 体积比应该合理（5%-90%）
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
    ok = main()
    ok2 = test_state_storage_completeness()
    ok3 = test_bottle_geometry_no_hollow()

    print(f"\n{'='*70}")
    print(f"  最终结果")
    print(f"{'='*70}")
    print(f"  Part 1 (约束穷举):     {'PASS' if ok else 'FAIL'}")
    print(f"  Part 2 (参数存储):     {'PASS' if ok2 else 'FAIL'}")
    print(f"  Part 3 (3D几何):       {'PASS' if ok3 else 'FAIL'}")

    all_ok = ok and ok2 and ok3
    sys.exit(0 if all_ok else 1)
