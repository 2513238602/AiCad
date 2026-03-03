# -*- coding: utf-8 -*-
"""
集成测试：web_server 参数存储完整性

验证 web_server generate 流程后存入 state manager 的参数
是归一化后的完整参数（包含 thread.crest_dia_mm 等）。

用法：
    python tests/lip_gloss/test_param_storage.py
"""
from __future__ import annotations

from typing import Any, Dict

from conftest import ALL_COMPONENTS

from core.interpreter import Interpreter
from core.component_state import ComponentStateManager
from products.lip_gloss.derived_params import CROSS_COMPONENT_RULES


def run_param_storage_test() -> bool:
    """测试参数存储完整性"""
    from products.lip_gloss.components.wand import WandComponent
    from products.lip_gloss.components.cap import CapComponent
    from products.lip_gloss.components.bottle import BottleComponent

    print(f"\n{'='*70}")
    print(f"  集成测试: web_server 参数存储完整性")
    print(f"{'='*70}")

    errors = []
    interp = Interpreter()

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

        final_params = qc.get("params", {})
        sm.set_generated(comp_id, final_params)

        stored = sm.get_generated(comp_id)
        print(f"  [{comp_id}] 存储参数数（扁平）: {len(flat)}")

        if comp_id == "wand":
            crest = stored.get("thread", {}).get("crest_dia_mm")
            if crest is None:
                errors.append(f"wand: thread.crest_dia_mm 缺失")
            else:
                print(f"    thread.crest_dia_mm = {crest} [OK]")

            pitch = stored.get("thread", {}).get("pitch_mm")
            if pitch is None:
                errors.append(f"wand: thread.pitch_mm 缺失")
            else:
                print(f"    thread.pitch_mm = {pitch} [OK]")

    # 验证约束：wand 和 cap 都生成后，bottle.neck_od_mm 应该被约束
    constraints = sm.get_all_constraints_for_component("bottle")
    neck = constraints.get("neck_od_mm")
    if neck is None:
        errors.append("bottle.neck_od_mm 无约束（规则未触发）")
    elif not neck.get("locked"):
        # neck_od_mm 可能不是锁定的（取决于约束类型），但应有约束
        print(f"  [bottle] neck_od_mm: constrained, range=[{neck.get('constrained_min')}, {neck.get('constrained_max')}] [OK]")
    else:
        print(f"  [bottle] neck_od_mm: LOCKED [OK], range=[{neck['constrained_min']}, {neck['constrained_max']}]")

    body = constraints.get("body_od_mm")
    if body and body.get("locked"):
        print(f"  [bottle] body_od_mm: LOCKED [OK], range=[{body['constrained_min']}, {body['constrained_max']}]")

    # 验证 stem_length_mm 约束（新规则 I1/I2）
    wand_constraints = sm.get_all_constraints_for_component("wand")
    stem = wand_constraints.get("stem_length_mm")
    if stem:
        print(f"  [wand] stem_length_mm: constrained, range=[{stem.get('constrained_min')}, {stem.get('constrained_max')}] [OK]")

    if errors:
        print(f"\n  [FAIL] 参数存储完整性测试失败:")
        for e in errors:
            print(f"    ERROR: {e}")
        return False
    else:
        print(f"\n  [PASS] 参数存储完整性测试通过")
        return True


if __name__ == "__main__":
    import sys
    ok = run_param_storage_test()
    sys.exit(0 if ok else 1)
