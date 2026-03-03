#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
装配逻辑极端值测试

在每种生成顺序下，把受约束参数推到极端（MIN/MAX），
验证装配关系是否仍然成立。
"""
import sys
import json
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8010"


def api_get(path):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=30) as resp:
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
    api_delete("/api/generated")


def get_nested(d, key):
    parts = key.split(".")
    for p in parts:
        if isinstance(d, dict):
            d = d.get(p)
        else:
            return None
    return d


def apply_constraints(constraints_data, mode="default"):
    """
    从约束中提取参数值
    mode: "default" | "min" | "max"
    """
    params = {}
    constraints = constraints_data.get("constraints", {})
    for pk, info in constraints.items():
        if mode == "default":
            val = info.get("constrained_default")
        elif mode == "min":
            val = info.get("constrained_min")
            if val is None:
                val = info.get("constrained_default")
        elif mode == "max":
            val = info.get("constrained_max")
            if val is None:
                val = info.get("constrained_default")
        else:
            val = info.get("constrained_default")

        if val is not None:
            parts = pk.split(".")
            target = params
            for p in parts[:-1]:
                if p not in target:
                    target[p] = {}
                target = target[p]
            target[parts[-1]] = val
    return params


def extract_params(result):
    return result.get("qc", {}).get("params", {})


def check_assembly_brief(all_params):
    """简短版装配检查，只返回错误列表"""
    cap = all_params.get("cap", {})
    bottle = all_params.get("bottle", {})
    wand = all_params.get("wand", {})
    wiper = all_params.get("wiper", {})
    errors = []

    cap_inner = get_nested(cap, "inner_id_mm")
    wand_outer = get_nested(wand, "outer_od_mm")
    if cap_inner and wand_outer:
        gap = cap_inner - wand_outer
        if gap < 0.3:
            errors.append(f"Cap⊃Wand外径: gap={gap:.2f}mm<0.3")

    cap_cavity = get_nested(cap, "cavity_depth_mm")
    wand_cap_h = get_nested(wand, "cap_height_mm")
    if cap_cavity and wand_cap_h:
        gap = cap_cavity - wand_cap_h
        if gap < 2.0:
            errors.append(f"Cap⊃Wand盖高: gap={gap:.2f}mm<2")

    cap_outer = get_nested(cap, "outer_od_mm")
    bottle_body = get_nested(bottle, "body_od_mm")
    if cap_outer and bottle_body and abs(cap_outer - bottle_body) > 1.0:
        errors.append(f"外径不齐: |{cap_outer}-{bottle_body}|={abs(cap_outer-bottle_body):.2f}>1")

    wand_crest = get_nested(wand, "thread.crest_dia_mm")
    bottle_neck = get_nested(bottle, "neck_od_mm")
    if wand_crest and bottle_neck and abs(wand_crest - bottle_neck) > 1.0:
        errors.append(f"螺纹: |{wand_crest}-{bottle_neck}|={abs(wand_crest-bottle_neck):.2f}>1")

    if wand_crest and wand_outer and wand_crest > wand_outer:
        errors.append(f"Wand结构: crest({wand_crest})>outer({wand_outer})")

    # Thread consistency
    for p in ["thread.pitch_mm", "thread.turns", "thread.depth_mm"]:
        wv = get_nested(wand, p)
        bv = get_nested(bottle, p)
        if wv is not None and bv is not None and wv != bv:
            errors.append(f"螺纹不一致: wand.{p}={wv}≠bottle.{p}={bv}")

    # Finish consistency
    finishes = set()
    for comp in [cap, bottle, wand, wiper]:
        f = get_nested(comp, "finish")
        if f:
            finishes.add(str(f))
    if len(finishes) > 1:
        errors.append(f"Finish不一致: {finishes}")

    # Wand fits in bottle
    bottle_depth = get_nested(bottle, "inner_depth_mm")
    wand_stem = get_nested(wand, "stem_length_mm")
    brush_len = get_nested(wand, "brush.length_mm") or 12.0
    if bottle_depth and wand_stem:
        margin = bottle_depth - wand_stem - brush_len
        if margin < 1.0:
            errors.append(f"杆长溢出: depth={bottle_depth}-stem={wand_stem}-brush={brush_len}={margin:.1f}<1")

    # Wiper fits in bottle neck
    wiper_outer = get_nested(wiper, "outer_od_mm")
    lip_t = get_nested(bottle, "lip_thickness_mm") or 1.0
    neck_inner = (bottle_neck - 2 * lip_t) if bottle_neck else None
    if wiper_outer and neck_inner and wiper_outer > neck_inner:
        errors.append(f"Wiper⊂Bottle: outer({wiper_outer})>neck_inner({neck_inner:.1f})")

    wiper_flange = get_nested(wiper, "flange_od_mm")
    if wiper_flange and bottle_neck and wiper_flange > bottle_neck:
        errors.append(f"Wiper凸环: flange({wiper_flange})>neck({bottle_neck})")

    wiper_h = get_nested(wiper, "height_mm")
    bottle_neck_h = get_nested(bottle, "neck_height_mm")
    if wiper_h and bottle_neck_h and wiper_h > bottle_neck_h:
        errors.append(f"Wiper高: h({wiper_h})>neck_h({bottle_neck_h})")

    wiper_orifice = get_nested(wiper, "orifice_mm")
    wand_stem_d = get_nested(wand, "stem_diameter_mm")
    if wiper_orifice and wand_stem_d and wiper_orifice - wand_stem_d < 0.5:
        errors.append(f"杆穿内塞: gap={wiper_orifice-wand_stem_d:.2f}<0.5")

    cap_plug = get_nested(cap, "seal.plug_od_mm")
    if cap_plug and wiper_orifice and cap_plug > wiper_orifice:
        errors.append(f"密封塞: plug({cap_plug})>orifice({wiper_orifice})")

    if cap_inner and bottle_neck and cap_inner - bottle_neck < 2.0:
        errors.append(f"Cap⊃Bottle颈: gap={cap_inner-bottle_neck:.2f}<2")

    return errors


ORDERS = [
    ["cap", "bottle", "wand", "wiper"],
    ["cap", "wand", "bottle", "wiper"],
    ["bottle", "cap", "wand", "wiper"],
    ["bottle", "wand", "cap", "wiper"],
    ["wand", "cap", "bottle", "wiper"],
    ["wand", "bottle", "cap", "wiper"],
]

MODES = ["default", "min", "max"]


def run_test(order, mode):
    """生成一组组件并检查装配"""
    clear_all()
    all_params = {}

    for comp in order:
        cons = api_get(f"/api/constraints/{comp}")
        params = apply_constraints(cons, mode=mode)
        result = api_post("/api/generate", {
            "product": "lip_gloss",
            "component": comp,
            "params": params,
        })
        if not result.get("ok", True):
            return [f"生成{comp}失败: {result.get('error', '?')}"], all_params

        final = extract_params(result)
        all_params[comp] = final

    return check_assembly_brief(all_params), all_params


def main():
    print("=" * 60)
    print("  AiCad 装配逻辑极端值测试")
    print("=" * 60)

    try:
        api_get("/api/schema")
    except Exception as e:
        print(f"无法连接服务器: {e}")
        sys.exit(1)

    total_errors = 0
    total_tests = 0
    failed_tests = []

    for order in ORDERS:
        for mode in MODES:
            total_tests += 1
            name = f"{' → '.join(order)} [{mode}]"
            try:
                errors, params = run_test(order, mode)
            except Exception as ex:
                errors = [f"Exception: {ex}"]
                params = {}

            ne = len(errors)
            total_errors += ne
            status = "✅" if ne == 0 else "❌"
            print(f"  {status} {name}: {ne} errors")

            if ne > 0:
                for e in errors:
                    print(f"       {e}")
                # Print key dimensions for debugging
                for comp_name in order:
                    p = params.get(comp_name, {})
                    dims = []
                    for k in ["outer_od_mm", "inner_id_mm", "body_od_mm", "neck_od_mm",
                              "cavity_depth_mm", "cap_height_mm", "thread.crest_dia_mm",
                              "height_mm", "inner_depth_mm", "stem_length_mm",
                              "flange_od_mm", "orifice_mm", "stem_diameter_mm"]:
                        v = get_nested(p, k)
                        if v is not None:
                            dims.append(f"{k}={v}")
                    if dims:
                        print(f"       {comp_name}: {', '.join(dims)}")
                failed_tests.append(name)

    print(f"\n{'='*60}")
    print(f"  结果: {total_tests} 测试, {total_errors} 错误")
    if failed_tests:
        print(f"  失败:")
        for ft in failed_tests:
            print(f"    - {ft}")
    print(f"{'='*60}")
    return total_errors


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
