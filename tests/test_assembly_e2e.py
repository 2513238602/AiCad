#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
装配逻辑端到端验证测试

验证：生成各组件后，零件尺寸是否满足物理装配关系。
测试所有生成顺序，使用约束系统提供的默认值。
"""
import sys
import json
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8010"


def api_get(path):
    req = urllib.request.Request(f"{BASE}{path}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def api_post(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=body,
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def api_delete(path):
    req = urllib.request.Request(f"{BASE}{path}", method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def clear_all():
    """清除所有已生成组件"""
    api_delete("/api/generated")


def get_constraints(component):
    """获取组件约束"""
    return api_get(f"/api/constraints/{component}")


def generate(component, params=None, preset_id=None):
    """生成组件"""
    data = {
        "product": "lip_gloss",
        "component": component,
    }
    if preset_id:
        data["preset_id"] = preset_id
    if params:
        data["params"] = params
    return api_post("/api/generate", data)


def apply_constraint_defaults(constraints_data):
    """从约束数据中提取默认值，构建参数字典"""
    params = {}
    constraints = constraints_data.get("constraints", {})
    for param_key, info in constraints.items():
        default = info.get("constrained_default")
        if default is not None:
            # 处理嵌套参数 (如 thread.pitch_mm)
            parts = param_key.split(".")
            target = params
            for p in parts[:-1]:
                if p not in target:
                    target[p] = {}
                target = target[p]
            target[parts[-1]] = default
    return params


def extract_params(gen_result):
    """从生成结果中提取最终参数"""
    qc = gen_result.get("qc", {})
    return qc.get("params", {})


def get_nested(d, key):
    """从嵌套字典中获取值，支持 dot 记法"""
    parts = key.split(".")
    for p in parts:
        if isinstance(d, dict):
            d = d.get(p)
        else:
            return None
    return d


# ═══════════════════════════════════════════════════════════════════
# 装配关系检查函数
# ═══════════════════════════════════════════════════════════════════

def check_assembly(all_params, order_name):
    """检查所有4个组件的装配关系"""
    cap = all_params.get("cap", {})
    bottle = all_params.get("bottle", {})
    wand = all_params.get("wand", {})
    wiper = all_params.get("wiper", {})

    errors = []
    warnings = []

    def err(msg):
        errors.append(msg)

    def warn(msg):
        warnings.append(msg)

    # ─── Cap ⊃ Wand (盖壳容纳刷杆盖部) ───
    cap_inner_id = get_nested(cap, "inner_id_mm")
    wand_outer_od = get_nested(wand, "outer_od_mm")
    if cap_inner_id and wand_outer_od:
        gap = cap_inner_id - wand_outer_od
        if gap < 0.3:
            err(f"Cap⊃Wand: 瓶盖内径({cap_inner_id}) - 刷杆外径({wand_outer_od}) = {gap:.2f}mm < 0.3mm（太紧/干涉）")
        elif gap > 2.0:
            warn(f"Cap⊃Wand: 间隙({gap:.2f}mm)过大，可能松动")

    cap_cavity = get_nested(cap, "cavity_depth_mm")
    wand_cap_h = get_nested(wand, "cap_height_mm")
    if cap_cavity and wand_cap_h:
        gap = cap_cavity - wand_cap_h
        if gap < 2.0:
            err(f"Cap⊃Wand: 腔深({cap_cavity}) - 盖高({wand_cap_h}) = {gap:.2f}mm < 2mm（盖装不进/太紧）")
        elif gap > 10.0:
            warn(f"Cap⊃Wand: 深度余量({gap:.2f}mm)过大")

    # ─── Cap 外径 ≈ Bottle 瓶身外径 (平齐外观) ───
    cap_outer = get_nested(cap, "outer_od_mm")
    bottle_body = get_nested(bottle, "body_od_mm")
    if cap_outer and bottle_body:
        diff = abs(cap_outer - bottle_body)
        if diff > 1.0:
            err(f"外观: |瓶盖外径({cap_outer}) - 瓶身外径({bottle_body})| = {diff:.2f}mm > 1mm（不平齐）")

    # ─── 螺纹配合: Wand crest_dia ≈ Bottle neck_od ───
    wand_crest = get_nested(wand, "thread.crest_dia_mm")
    bottle_neck = get_nested(bottle, "neck_od_mm")
    if wand_crest and bottle_neck:
        diff = abs(wand_crest - bottle_neck)
        if diff > 1.0:
            err(f"螺纹: |刷杆峰径({wand_crest}) - 瓶颈外径({bottle_neck})| = {diff:.2f}mm > 1mm（螺纹无法啮合）")
        elif diff > 0.3:
            warn(f"螺纹: 峰径差({diff:.2f}mm)偏大")

    # ─── 螺纹参数一致性 ───
    for param in ["thread.pitch_mm", "thread.turns", "thread.depth_mm",
                   "thread.lead_angle_deg", "thread.segmented"]:
        wv = get_nested(wand, param)
        bv = get_nested(bottle, param)
        if wv is not None and bv is not None and wv != bv:
            err(f"螺纹不一致: wand.{param}={wv} ≠ bottle.{param}={bv}")

    # ─── Wand crest_dia > Wand outer_od 不允许（螺纹不能比盖壳还宽）───
    if wand_crest and wand_outer_od:
        if wand_crest > wand_outer_od:
            err(f"刷杆结构: 螺纹峰径({wand_crest}) > 盖部外径({wand_outer_od})（物理不可能，螺纹比盖壳宽）")
        elif wand_outer_od - wand_crest < 2.0:
            warn(f"刷杆结构: 盖部到螺纹直径差({wand_outer_od - wand_crest:.2f}mm)偏小")

    # ─── Finish 一致性 ───
    finishes = {}
    for comp_name, comp_params in [("cap", cap), ("bottle", bottle), ("wand", wand), ("wiper", wiper)]:
        f = get_nested(comp_params, "finish")
        if f:
            finishes[comp_name] = f
    unique = set(finishes.values())
    if len(unique) > 1:
        err(f"Finish 不一致: {finishes}")

    # ─── Finish 规格匹配 ───
    finish = get_nested(cap, "finish") or get_nested(bottle, "finish") or "18-415"
    try:
        spec_od = float(str(finish).split("-")[0])
    except Exception:
        spec_od = 18.0

    if bottle_neck:
        if abs(bottle_neck - spec_od) > 1.0:
            err(f"Finish: 瓶颈外径({bottle_neck}) 偏离规格({spec_od}mm) > 1mm")

    if wand_crest:
        if abs(wand_crest - spec_od) > 2.0:
            err(f"Finish: 刷杆峰径({wand_crest}) 偏离规格({spec_od}mm) > 2mm")

    # ─── Bottle 内深 > Wand 杆长 + 刷头 + 余量 ───
    bottle_inner_depth = get_nested(bottle, "inner_depth_mm")
    wand_stem_len = get_nested(wand, "stem_length_mm")
    wand_brush_len = get_nested(wand, "brush.length_mm") or 12.0
    if bottle_inner_depth and wand_stem_len:
        needed = wand_stem_len + wand_brush_len
        margin = bottle_inner_depth - needed
        if margin < 1.0:
            err(f"杆长: 瓶身内深({bottle_inner_depth}) < 杆长({wand_stem_len})+刷头({wand_brush_len})+1mm余量 (余量={margin:.1f}mm)")
        elif margin > 30.0:
            warn(f"杆长: 瓶内余量({margin:.1f}mm)过大，刷头到不了瓶底")

    # ─── Wiper ⊂ Bottle 颈部 ───
    wiper_outer = get_nested(wiper, "outer_od_mm")
    wiper_flange = get_nested(wiper, "flange_od_mm")
    bottle_lip_t = get_nested(bottle, "lip_thickness_mm") or 1.0
    bottle_neck_inner = (bottle_neck - 2 * bottle_lip_t) if bottle_neck else None

    if wiper_outer and bottle_neck_inner:
        if wiper_outer > bottle_neck_inner:
            err(f"Wiper⊂Bottle: 内塞外径({wiper_outer}) > 瓶颈内径({bottle_neck_inner:.1f})（装不进）")

    if wiper_flange and bottle_neck:
        if wiper_flange > bottle_neck:
            err(f"Wiper⊂Bottle: 内塞凸环({wiper_flange}) > 瓶颈外径({bottle_neck})（凸环露出）")

    wiper_height = get_nested(wiper, "height_mm")
    bottle_neck_h = get_nested(bottle, "neck_height_mm")
    if wiper_height and bottle_neck_h:
        if wiper_height > bottle_neck_h:
            err(f"Wiper⊂Bottle: 内塞高({wiper_height}) > 颈高({bottle_neck_h})（装不进瓶颈）")

    # ─── Wiper 孔径 > Wand 杆径 ───
    wiper_orifice = get_nested(wiper, "orifice_mm")
    wand_stem_d = get_nested(wand, "stem_diameter_mm")
    if wiper_orifice and wand_stem_d:
        gap = wiper_orifice - wand_stem_d
        if gap < 0.5:
            err(f"Wiper⊃Wand杆: 孔径({wiper_orifice}) - 杆径({wand_stem_d}) = {gap:.2f}mm < 0.5mm（杆穿不过）")

    # ─── Cap 密封塞穿过 Wiper 孔 ───
    cap_plug = get_nested(cap, "seal.plug_od_mm")
    if cap_plug and wiper_orifice:
        if cap_plug > wiper_orifice:
            err(f"密封塞: 塞外径({cap_plug}) > 内塞孔径({wiper_orifice})（塞穿不过内塞）")

    # ─── Cap 内径 > Bottle 颈外径 (瓶盖要套在瓶颈外) ───
    if cap_inner_id and bottle_neck:
        gap = cap_inner_id - bottle_neck
        if gap < 2.0:
            err(f"Cap⊃Bottle颈: 盖内径({cap_inner_id}) - 颈外径({bottle_neck}) = {gap:.2f}mm < 2mm（螺纹空间不够）")

    # ─── Wand outer_od 应能装入 cap 同时螺纹能配合 bottle ───
    # 即 cap_inner_id > wand_outer_od > wand_crest_dia，且 wand_crest_dia ≈ bottle_neck_od
    if all([cap_inner_id, wand_outer_od, wand_crest, bottle_neck]):
        chain = f"cap.inner_id({cap_inner_id}) > wand.outer_od({wand_outer_od}) > wand.crest({wand_crest}) ≈ bottle.neck({bottle_neck})"
        if not (cap_inner_id > wand_outer_od > wand_crest):
            err(f"尺寸链断裂: 期望 {chain}")

    return errors, warnings


# ═══════════════════════════════════════════════════════════════════
# 测试执行
# ═══════════════════════════════════════════════════════════════════

GENERATION_ORDERS = [
    ["cap", "bottle", "wand", "wiper"],
    ["cap", "wand", "bottle", "wiper"],
    ["bottle", "cap", "wand", "wiper"],
    ["bottle", "wand", "cap", "wiper"],
    ["wand", "cap", "bottle", "wiper"],
    ["wand", "bottle", "cap", "wiper"],
]


def test_generation_order(order):
    """按指定顺序生成组件并检查装配"""
    order_name = " → ".join(order)
    print(f"\n{'═'*60}")
    print(f"  测试顺序: {order_name}")
    print(f"{'═'*60}")

    clear_all()
    all_params = {}

    for i, comp in enumerate(order):
        # 获取约束
        cons_data = get_constraints(comp)
        constraints = cons_data.get("constraints", {})
        generated = cons_data.get("generated", [])

        # 构建参数：先用约束默认值
        constraint_params = apply_constraint_defaults(cons_data)

        print(f"\n  [{i+1}] 生成 {comp} (已有: {generated})")
        if constraints:
            for pk, info in sorted(constraints.items()):
                locked = "🔒" if info.get("locked") else "  "
                cmin = info.get("constrained_min")
                cmax = info.get("constrained_max")
                cdef = info.get("constrained_default")
                if cmin is not None:
                    print(f"      {locked} {pk}: [{cmin}, {cmax}] → {cdef}")
                else:
                    print(f"      {locked} {pk}: → {cdef}")

        # 生成
        result = generate(comp, params=constraint_params)

        if not result.get("ok", True):
            print(f"      ❌ 生成失败: {result.get('error', 'unknown')}")
            return None, None

        # 检查QC
        qc = result.get("qc", {})
        if not qc.get("ok", True):
            fails = [c for c in qc.get("checks", []) if not c.get("ok")]
            for f in fails:
                print(f"      ⚠️ QC失败: [{f.get('severity')}] {f.get('msg')}")

        final = extract_params(result)
        all_params[comp] = final

        # 打印关键尺寸
        key_dims = {
            "cap": ["outer_od_mm", "inner_id_mm", "height_mm", "cavity_depth_mm", "seal.plug_od_mm", "finish"],
            "bottle": ["body_od_mm", "neck_od_mm", "neck_height_mm", "height_mm", "inner_depth_mm",
                       "lip_thickness_mm", "thread.pitch_mm", "thread.turns", "finish"],
            "wand": ["outer_od_mm", "cap_height_mm", "total_height_mm", "stem_length_mm",
                     "stem_diameter_mm", "thread.crest_dia_mm", "thread.pitch_mm", "thread.turns",
                     "orifice_mm", "finish"],
            "wiper": ["outer_od_mm", "orifice_mm", "flange_od_mm", "height_mm", "finish"],
        }
        print(f"      最终参数:")
        for k in key_dims.get(comp, []):
            v = get_nested(final, k)
            if v is not None:
                print(f"        {k} = {v}")

    # 检查装配
    print(f"\n  装配检查:")
    errors, warnings = check_assembly(all_params, order_name)

    for e in errors:
        print(f"    ❌ {e}")
    for w in warnings:
        print(f"    ⚠️ {w}")

    if not errors:
        print(f"    ✅ 所有装配关系正确")

    return errors, warnings


def main():
    print("=" * 60)
    print("  AiCad 装配逻辑端到端测试")
    print("=" * 60)

    # 验证服务器可达
    try:
        api_get("/api/schema")
    except Exception as e:
        print(f"❌ 无法连接到服务器: {e}")
        sys.exit(1)

    total_errors = 0
    total_warnings = 0
    order_results = {}

    for order in GENERATION_ORDERS:
        errors, warnings = test_generation_order(order)
        order_name = " → ".join(order)

        if errors is None:
            order_results[order_name] = "FAIL (generation error)"
            total_errors += 1
        else:
            ne = len(errors)
            nw = len(warnings)
            total_errors += ne
            total_warnings += nw
            order_results[order_name] = f"{ne} errors, {nw} warnings"

    # 汇总
    print(f"\n\n{'='*60}")
    print(f"  汇总")
    print(f"{'='*60}")
    for name, result in order_results.items():
        status = "❌" if "error" in result.lower() or result.startswith("FAIL") else "✅"
        print(f"  {status} {name}: {result}")

    print(f"\n  总计: {total_errors} errors, {total_warnings} warnings")
    return total_errors


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
