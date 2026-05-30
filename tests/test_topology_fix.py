# -*- coding: utf-8 -*-
"""拓扑修复回归测试 — 14 Gallery 配置全检"""
import sys, os, json, time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from web_server import GALLERY_CATALOG
from core.vlm_extract import (
    build_bottle_params, derive_cap_params,
    derive_wand_params, derive_wiper_params,
    reconcile_all_params,
)
from core.assembly import compute_assembly_report, check_brep_assembly
from core.auto_repair import analyze_and_fix
from core.modeler import Modeler

def get_component(product, comp_id):
    from products.lip_gloss.components.bottle import BottleComponent
    from products.lip_gloss.components.cap import CapComponent
    from products.lip_gloss.components.wand import WandComponent
    from products.lip_gloss.components.wiper import WiperComponent
    return {"bottle": BottleComponent, "cap": CapComponent,
            "wand": WandComponent, "wiper": WiperComponent}[comp_id]()


GEN_ORDER = ["bottle", "cap", "wand", "wiper"]


def run_all():
    results = {}
    total = 0
    pass_count = 0
    fail_details = []
    # L7: 保留各配置的实体和参数用于 BRep 装配干涉检测
    all_solids = {}   # {cat_id: {comp_id: cq.Workplane}}
    all_cat_params = {}  # {cat_id: {comp_id: params}}

    for cat_id, spec in GALLERY_CATALOG.items():
        print(f"\n{'='*60}")
        print(f"  {cat_id}: {spec['desc']}")
        print(f"{'='*60}")

        # Phase 1: 参数合成
        try:
            bottle_p = build_bottle_params(spec["user_dims"], spec["vlm_shape"])
            cap_p = derive_cap_params(bottle_p, spec["vlm_shape"])
            wand_p = derive_wand_params(cap_p, bottle_p)
            wiper_p = derive_wiper_params(bottle_p, wand_p)
            all_params = {"bottle": bottle_p, "cap": cap_p,
                          "wand": wand_p, "wiper": wiper_p}
            all_params, _ = reconcile_all_params(all_params)
            all_cat_params[cat_id] = all_params
        except Exception as e:
            print(f"  [FAIL] 参数合成失败: {e}")
            for c in GEN_ORDER:
                results[f"{cat_id}/{c}"] = {"ok": False, "error": f"param: {e}"}
                total += 1
                fail_details.append(f"{cat_id}/{c}: 参数合成失败")
            continue

        # Phase 2: 逐组件建模
        for comp_id in GEN_ORDER:
            total += 1
            key = f"{cat_id}/{comp_id}"
            try:
                comp = get_component("lip_gloss", comp_id)
                params = all_params[comp_id]
                res = comp.generate(
                    preset_id=None,
                    user_params=params,
                    outroot="artifacts/topo_test",
                    title=f"topo_{cat_id}_{comp_id}",
                )

                if not res.get("ok"):
                    error = res.get("error", "unknown")
                    print(f"  [{comp_id}] FAIL generate: {error[:100]}")
                    results[key] = {"ok": False, "error": error[:200]}
                    fail_details.append(f"{key}: {error[:100]}")
                    continue

                # 提取 topology_qc
                meta = res.get("qc", {}).get("modeler_meta", {})
                topo = meta.get("topology_qc", {})
                solid_count = topo.get("solid_count", -1)
                is_single = topo.get("is_single_solid", False)
                neg_vol = topo.get("negative_volume", False)
                vol = topo.get("total_volume_mm3", 0)
                fixes = topo.get("fixes_applied", [])
                warnings = topo.get("warnings", [])

                ok = is_single and not neg_vol and solid_count == 1
                status = "PASS" if ok else "FAIL"

                if fixes:
                    status += " (fixed)"
                if warnings:
                    status += " (warn)"

                print(f"  [{comp_id}] {status}: solids={solid_count}, vol={vol:.1f}mm³"
                      + (f", fixes={fixes}" if fixes else "")
                      + (f", warnings={warnings}" if warnings else ""))

                results[key] = {
                    "ok": ok,
                    "solid_count": solid_count,
                    "volume": vol,
                    "is_single_solid": is_single,
                    "negative_volume": neg_vol,
                    "fixes": fixes,
                    "warnings": warnings,
                    "geometry_qc": meta.get("geometry_qc", {}),
                }

                # L7: 构建实体用于装配干涉检测
                if ok:
                    try:
                        _m = Modeler()
                        _meta7 = {}
                        _solid = _m.build(comp_id, all_params[comp_id], meta=_meta7)
                        all_solids.setdefault(cat_id, {})[comp_id] = _solid
                    except Exception:
                        pass  # 构建失败不影响拓扑测试

                if ok:
                    pass_count += 1
                else:
                    fail_details.append(f"{key}: solids={solid_count}, vol={vol:.1f}")

            except Exception as e:
                print(f"  [{comp_id}] ERROR: {e}")
                results[key] = {"ok": False, "error": str(e)[:200]}
                fail_details.append(f"{key}: exception: {str(e)[:80]}")

    # ═══════════════════════════════════════════════════════════════
    # L5: 语义验证 — 装配 QC 中的新增语义检查
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"  L5 语义验证")
    print(f"{'='*60}")

    semantic_total = 0
    semantic_pass = 0
    semantic_warns = []

    for cat_id, spec in GALLERY_CATALOG.items():
        try:
            bottle_p = build_bottle_params(spec["user_dims"], spec["vlm_shape"])
            cap_p = derive_cap_params(bottle_p, spec["vlm_shape"])
            wand_p = derive_wand_params(cap_p, bottle_p)
            wiper_p = derive_wiper_params(bottle_p, wand_p)
            all_p = {"bottle": bottle_p, "cap": cap_p,
                     "wand": wand_p, "wiper": wiper_p}
            all_p, _ = reconcile_all_params(all_p)

            report = compute_assembly_report(all_p)
            quality = report.get("quality", {})
            checks = quality.get("checks", [])

            # 检查语义项（⑬-⑯）+ 配合完整性（⑱-㉕）
            _sem_tags = ("⑬", "⑭", "⑮", "⑯", "⑱", "⑲", "⑳", "㉑", "㉒", "㉓", "㉔", "㉕")
            _hard_tags = ("⑬", "⑱", "⑲", "⑳", "㉑", "㉒", "㉓")  # HARD 级
            for check in checks:
                name = check.get("name", "")
                if any(t in name for t in _sem_tags):
                    semantic_total += 1
                    if check["pass"]:
                        semantic_pass += 1
                    else:
                        level = "FAIL" if any(t in name for t in _hard_tags) else "WARN"
                        msg = f"{cat_id}: {name} → {check['msg']}"
                        semantic_warns.append(f"[{level}] {msg}")
                        if level == "FAIL":
                            fail_details.append(f"L5 {msg}")
                        print(f"  [{cat_id}] {level}: {name}")
        except Exception as e:
            print(f"  [{cat_id}] L5 ERROR: {e}")

    print(f"\n  L5 语义: {semantic_pass}/{semantic_total} PASS")
    if semantic_warns:
        for w in semantic_warns:
            print(f"    {w}")

    # ═══════════════════════════════════════════════════════════════
    # L6: 几何验证 — BRep 成品 vs 参数
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"  L6 几何验证（BRep 级）")
    print(f"{'='*60}")

    geo_total = 0
    geo_pass = 0
    geo_warns = []

    for key, r in results.items():
        geo_qc = r.get("geometry_qc", {})
        for gc in geo_qc.get("checks", []):
            geo_total += 1
            if gc.get("pass", True):
                geo_pass += 1
            else:
                sev = gc.get("severity", "soft")
                level = "FAIL" if sev == "hard" else "WARN"
                msg = f"{key}: {gc.get('name', '?')} → {gc.get('msg', '')}"
                geo_warns.append(f"[{level}] {msg}")
                if level == "FAIL":
                    fail_details.append(f"L6 {msg}")
                print(f"  [{key}] {level}: {gc.get('name', '?')}")

    print(f"\n  L6 几何: {geo_pass}/{geo_total} PASS")
    if geo_warns:
        for w in geo_warns:
            print(f"    {w}")

    # ═══════════════════════════════════════════════════════════════
    # L7: BRep 装配干涉检测 — 成品级实体布尔交集
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"  L7 BRep 装配干涉检测")
    print(f"{'='*60}")

    brep_total = 0
    brep_pass = 0
    brep_warns = []

    for cat_id in GALLERY_CATALOG:
        cat_solids = all_solids.get(cat_id, {})
        cat_params = all_cat_params.get(cat_id, {})
        if len(cat_solids) < 4:
            # 不足 4 个实体，跳过
            continue
        try:
            brep = check_brep_assembly(cat_params, solids=cat_solids)
            pairs = brep.get("pairs", [])
            line_parts = []
            for p in pairs:
                brep_total += 1
                if p["ok"]:
                    brep_pass += 1
                    line_parts.append(f"{p['pair']}: {p['volume_mm3']:.1f}mm³ OK")
                else:
                    msg = f"{cat_id} {p['pair']}: {p['volume_mm3']:.1f}mm³ 干涉！"
                    brep_warns.append(f"[FAIL] {msg}")
                    fail_details.append(f"L7 {msg}")
                    line_parts.append(f"{p['pair']}: {p['volume_mm3']:.1f}mm³ FAIL")
            print(f"  [{cat_id}] {' | '.join(line_parts)}")
        except Exception as e:
            print(f"  [{cat_id}] L7 ERROR: {e}")

    print(f"\n  L7 BRep 装配: {brep_pass}/{brep_total} PASS")
    if brep_warns:
        for w in brep_warns:
            print(f"    {w}")

    # ═══════════════════════════════════════════════════════════════
    # L8: 自修复分析+验证 — 对 QC 失败项自动调整参数并重建
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print(f"  L8 自修复验证")
    print(f"{'='*60}")

    repair_need = 0     # 需要修复的配置数
    repair_fixed = 0    # 修复后全部通过的配置数
    repair_improved = 0 # 修复后有改善的配置数
    repair_log_all = []

    for cat_id in GALLERY_CATALOG:
        cat_params = all_cat_params.get(cat_id, {})
        if not cat_params:
            continue

        # 获取当前 QC 状态
        assy_report = compute_assembly_report(cat_params)
        cat_solids = all_solids.get(cat_id, {})
        brep_rpt = None
        if len(cat_solids) >= 4:
            brep_rpt = check_brep_assembly(cat_params, solids=cat_solids)

        assy_ok = assy_report.get("ok", True)
        brep_ok = brep_rpt.get("ok", True) if brep_rpt else True

        if assy_ok and brep_ok:
            continue  # 无失败，跳过

        repair_need += 1

        # ── 分析并修复（最多 3 轮） ──
        cur_params = cat_params
        total_log = []
        final_ok = False
        protected = set()

        for rd in range(1, 4):
            fixed, rd_log, protected = analyze_and_fix(
                cur_params, assy_report, brep_rpt, protected)
            if not rd_log:
                break
            for entry in rd_log:
                entry["round"] = rd
            total_log.extend(rd_log)

            # 重建 4 个实体验证修复效果
            new_solids = {}
            rebuild_ok = True
            for comp_id in GEN_ORDER:
                try:
                    comp = get_component("lip_gloss", comp_id)
                    res = comp.generate(
                        preset_id=None, user_params=fixed[comp_id],
                        outroot="artifacts/repair_test",
                        title=f"repair_{cat_id}_{comp_id}_r{rd}",
                    )
                    if res.get("ok"):
                        _m = Modeler()
                        _meta = {}
                        _solid = _m.build(comp_id, fixed[comp_id], meta=_meta)
                        new_solids[comp_id] = _solid
                    else:
                        rebuild_ok = False
                except Exception:
                    rebuild_ok = False

            if not rebuild_ok or len(new_solids) < 4:
                break

            # 重新检查
            assy_report = compute_assembly_report(fixed)
            brep_rpt = check_brep_assembly(fixed, solids=new_solids)
            cur_params = fixed

            if assy_report.get("ok", True) and brep_rpt.get("ok", True):
                final_ok = True
                break

        # 统计结果 — 前后干涉体积对比（per-pair）
        orig_brep = check_brep_assembly(cat_params, solids=all_solids.get(cat_id, {})) \
                    if len(cat_solids) >= 4 else {}
        vol_before = sum(p.get("volume_mm3", 0) for p in orig_brep.get("pairs", [])
                         if not p.get("ok", True))
        vol_after = sum(p.get("volume_mm3", 0) for p in (brep_rpt or {}).get("pairs", [])
                        if not p.get("ok", True))
        n_before = sum(1 for p in orig_brep.get("pairs", []) if not p.get("ok", True))
        n_after = sum(1 for p in (brep_rpt or {}).get("pairs", []) if not p.get("ok", True))

        # BRep 全通过 = FIXED（即使参数级 QC 仍有外观失败）
        brep_all_ok = brep_rpt.get("ok", True) if brep_rpt else True
        if final_ok or brep_all_ok:
            repair_fixed += 1
            status = "FIXED"
            if not assy_report.get("ok", True):
                status += " (BRep通过, 外观QC残余)"
        elif vol_after < vol_before * 0.5:
            repair_improved += 1
            pct = (1 - vol_after / max(vol_before, 1)) * 100
            status = f"IMPROVED ({vol_before:.0f}→{vol_after:.0f}mm³, -{pct:.0f}%)"
        elif n_after < n_before:
            repair_improved += 1
            status = f"IMPROVED ({n_before}→{n_after} 干涉对)"
        else:
            status = f"PARTIAL ({vol_after:.0f}mm³ 残余)"

        # Per-pair 对比详情
        pair_details = []
        orig_pairs = {p["pair"]: p for p in orig_brep.get("pairs", [])}
        new_pairs = {p["pair"]: p for p in (brep_rpt or {}).get("pairs", [])}
        for pair_name in orig_pairs:
            ov = orig_pairs[pair_name].get("volume_mm3", 0)
            nv = new_pairs.get(pair_name, {}).get("volume_mm3", 0)
            if ov > 0.1 or nv > 0.1:
                pair_details.append(f"{pair_name}: {ov:.0f}→{nv:.0f}")

        fixes_str = "; ".join(
            f"{r['component']}.{r['param']}={r['new']}"
            for r in total_log[:4]
        )
        if len(total_log) > 4:
            fixes_str += f" +{len(total_log)-4}项"

        detail_str = " | ".join(pair_details) if pair_details else ""
        print(f"  [{cat_id}] {status} ({len(total_log)}步)")
        if detail_str:
            print(f"    干涉: {detail_str}")
        if fixes_str:
            print(f"    修复: {fixes_str}")

        repair_log_all.append({"cat_id": cat_id, "status": status,
                                "rounds": total_log[-1]["round"] if total_log else 0,
                                "fixes": len(total_log)})

    print(f"\n  L8 自修复: {repair_fixed}/{repair_need} 完全修复, "
          f"{repair_improved}/{repair_need} 改善")

    # Summary
    print(f"\n{'='*60}")
    print(f"  拓扑测试结果: {pass_count}/{total} PASS ({100*pass_count/max(total,1):.0f}%)")
    print(f"  语义测试结果: {semantic_pass}/{semantic_total} PASS")
    print(f"  几何测试结果: {geo_pass}/{geo_total} PASS")
    print(f"  装配干涉结果: {brep_pass}/{brep_total} PASS")
    print(f"  自修复结果: {repair_fixed}/{repair_need} 完全修复, "
          f"{repair_improved}/{repair_need} 改善")
    print(f"{'='*60}")

    if fail_details:
        print("\n失败项:")
        for f in fail_details:
            print(f"  - {f}")

    # Save results
    out_path = os.path.join(os.path.dirname(__file__), "topology_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"pass": pass_count, "total": total,
                    "rate": round(pass_count/max(total,1), 3),
                    "details": results}, f, indent=2, ensure_ascii=False)
    print(f"\n结果已保存: {out_path}")

    return pass_count, total


if __name__ == "__main__":
    p, t = run_all()
    sys.exit(0 if p == t else 1)
