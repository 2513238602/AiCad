# -*- coding: utf-8 -*-
"""展览馆预生成脚本 — 离线构建所有 Gallery 配置的 STL + 装配数据。

复用 Web 高级模式的逐组件约束传播路径（ComponentStateManager + CrossComponentDerived），
确保 Gallery 产出与 Web 高级模式一致。

用法:
    python scripts/prebuild_gallery.py                           # 构建全部 14 个配置
    python scripts/prebuild_gallery.py A3_round_pointed          # 仅构建指定配置
    python scripts/prebuild_gallery.py A3_round_pointed --component cap   # 仅构建 cap
    python scripts/prebuild_gallery.py A3_round_pointed --component wand  # 读取已有 manifest → 构建 wand
"""
from __future__ import annotations

import io
import sys
# Windows GBK 终端兼容：强制 stdout/stderr 为 UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import json
import math
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from products.lip_gloss.components.registry import get_component
from core.component_state import get_state_manager
from core.assembly import compute_assembly_positions, compute_assembly_report
from core.param_system import get_nested_value, set_nested_value, get_derived_registry
from core.interpreter import _flatten
import products.lip_gloss.derived_params  # noqa: F401 — 注册派生规则


# 复用 web_server 的参数合成逻辑和 Gallery 目录
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from web_server import GALLERY_CATALOG, _fix_finish_spec

from core.vlm_extract import (
    build_bottle_params, derive_cap_params,
    derive_wand_params, derive_wiper_params,
)
from core.render_materials import (
    attach_render_metadata,
    build_gallery_render_metadata,
    strip_render_metadata,
)

ART_ROOT = PROJECT_ROOT / "artifacts"
PREBUILT_ROOT = ART_ROOT / "gallery_prebuilt"
VLM_CACHE_DIR = ART_ROOT / "vlm_cache"
DEFAULT_GEN_ORDER = ["bottle", "cap", "wand", "wiper"]


def _load_vlm_cache(cat_id: str) -> dict | None:
    """读取 VLM 缓存（由 rebuild_gallery.py 生成）。"""
    cache_file = VLM_CACHE_DIR / f"{cat_id}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _unflatten(flat: dict) -> dict:
    """将扁平格式参数转为嵌套格式（"thread.crest_dia_mm" → {"thread": {"crest_dia_mm": ...}}）。

    _fix_finish_spec 和 comp.generate() 期望嵌套格式来读取 thread 子参数。
    """
    nested: dict = {}
    for k, v in flat.items():
        set_nested_value(nested, k, v)
    return nested


def load_manifest(cat_id: str) -> dict | None:
    """读取已有的 manifest.json，返回 manifest dict 或 None。"""
    mf = PREBUILT_ROOT / cat_id / "manifest.json"
    if mf.exists():
        return json.loads(mf.read_text("utf-8"))
    return None


def _apply_web_constraints(
    comp_id: str, params: dict, state_mgr
) -> tuple[dict, set]:
    """复用 Web 高级模式的跨组件约束传播路径。

    模拟前端 useGenerate.ts 中的流程：
    1. fetchConstraints(comp_id) → state_mgr.get_all_constraints_for_component()
    2. applyCrossConstraints() → locked 参数设默认值，范围参数夹紧
    3. recalcAllDerivedParams() → 重算派生参数，跳过被锁定的

    Returns:
        (修正后的 params, 被锁定的参数键集合)
    """
    constraints = state_mgr.get_all_constraints_for_component(comp_id)
    locked_keys: set[str] = set()
    applied: list[str] = []

    for param_key, c in constraints.items():
        if c.get("locked"):
            old_val = params.get(param_key)
            new_val = c["constrained_default"]
            params[param_key] = new_val
            locked_keys.add(param_key)
            src = c.get("source_component", "?")
            if isinstance(new_val, (int, float)) and isinstance(old_val, (int, float)):
                applied.append(
                    f"{src} → {comp_id}.{param_key}={new_val:.1f} (locked)"
                )
            else:
                applied.append(
                    f"{src} → {comp_id}.{param_key}={new_val} (locked)"
                )
        else:
            lo = c.get("constrained_min")
            hi = c.get("constrained_max")
            if lo is not None and hi is not None:
                current = params.get(param_key)
                if current is not None and isinstance(current, (int, float)):
                    clamped = max(lo, min(hi, current))
                    if abs(clamped - current) > 0.01:
                        applied.append(
                            f"{comp_id}.{param_key}: {current:.1f} → {clamped:.1f} "
                            f"(范围 [{lo:.1f}, {hi:.1f}])"
                        )
                    params[param_key] = clamped

    # 重算派生参数（跳过被锁定的），复用 DerivedParamRegistry
    # 但保留已显式传入且在合法范围内的值（CV 精确测量优先于默认公式）
    registry = get_derived_registry()
    for pk, rule in registry.get_component_rules("lip_gloss", comp_id).items():
        if pk in locked_keys:
            continue
        master_val = params.get(rule.master_param)
        if master_val is None:
            continue
        existing = params.get(pk)
        if existing is None:
            # 参数不存在 → 该子功能未启用（如 cap.stem 关闭时无 thread/seal_ring），不强行添加
            continue
        try:
            lo, hi = rule.compute_range(float(master_val), params)
            # 如果已有值在合法范围内，保留（CV 精确测量优先于默认公式）
            if lo <= float(existing) <= hi:
                continue
            params[pk] = rule.compute_default(float(master_val), params)
        except Exception:
            pass

    if applied:
        for msg in applied:
            print(f"    [约束] {msg}")

    return params, locked_keys


def _guard_cap_taper(params: dict) -> None:
    """Cap 锥度几何可行性守卫 — 防止 taper × height 导致顶部退化。"""
    cap_od = params.get("outer_od_mm", 20)
    cap_h = params.get("height_mm", 30)
    cap_taper = params.get("taper_deg", 0)
    cs = params.get("cross_section", "round")

    if cap_taper > 0 and cap_h > 0:
        cap_top_od = cap_od - 2 * math.tan(math.radians(cap_taper)) * cap_h
        min_top = 10.0 if cs == "square" else (8.0 if cs != "round" else 6.0)
        if cap_top_od < min_top:
            safe_taper = math.degrees(math.atan((cap_od - min_top) / (2 * cap_h)))
            safe_taper = round(max(0.5, safe_taper), 1)
            print(
                f"    [守卫] cap.taper_deg: {cap_taper:.1f}→{safe_taper:.1f} "
                f"(顶部{cap_top_od:.1f}mm<{min_top}mm)"
            )
            params["taper_deg"] = safe_taper


def _guard_cap_grip(params: dict) -> None:
    """Cap grip 安全降级 — 壁太薄时自动减小 depth 或降级为 none。"""
    style = params.get("grip.style", "none")
    if style == "none":
        return
    depth = float(params.get("grip.depth_mm", 0.3))
    od = float(params.get("outer_od_mm", 20))
    inner_id = float(params.get("inner_id_mm", od - 1.6))
    wall = (od - inner_id) / 2.0
    max_depth = wall * 0.45  # 留5%余量到 50% 硬约束
    if depth > max_depth:
        if max_depth >= 0.1:
            new_depth = round(max_depth, 2)
            print(f"    [守卫] cap.grip.depth: {depth:.2f}→{new_depth:.2f}mm"
                  f" (壁厚{wall:.2f}mm)")
            params["grip.depth_mm"] = new_depth
        else:
            print(f"    [守卫] cap.grip: {style}→none (壁厚{wall:.2f}mm 不足)")
            params["grip.style"] = "none"
            params["grip.depth_mm"] = 0.0
            params["grip.count"] = 0


def _print_param_summary(comp_id: str, params: dict):
    """打印组件关键参数摘要。"""
    key_params = {
        "cap": ["outer_od_mm", "height_mm", "taper_deg", "inner_id_mm", "cavity_depth_mm"],
        "bottle": ["body_od_mm", "height_mm", "neck_od_mm", "neck_height_mm"],
        "wand": ["outer_od_mm", "cap_height_mm", "total_height_mm",
                  "thread.crest_dia_mm", "thread.enabled"],
        "wiper": ["outer_od_mm", "hole_id_mm", "flange_od_mm"],
    }
    keys = key_params.get(comp_id, [])
    parts = []
    for k in keys:
        v = get_nested_value(params, k)
        if v is not None:
            if isinstance(v, float):
                parts.append(f"{k}={v:.1f}")
            else:
                parts.append(f"{k}={v}")
    if parts:
        print(f"    参数: {', '.join(parts)}")


def build_one(cat_id: str, spec: dict, component: str | None = None) -> dict:
    """构建单个 Gallery 配置，返回 manifest dict。

    复用 Web 高级模式的约束传播路径：
    - 每生成一个组件，其输出参数存入 ComponentStateManager
    - 下一个组件生成前，通过 get_all_constraints_for_component() 获取约束
    - 约束应用 + 派生参数重算 → 与 Web 前端 useGenerate.ts 一致

    Args:
        cat_id: 配置 ID
        spec: 配置规格
        component: 如果指定，仅构建该组件（逐组件模式）
    """
    out_dir = PREBUILT_ROOT / cat_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: 初始参数合成 ──
    state_mgr = get_state_manager()
    state_mgr.clear()

    # 锚点加载（--component 模式：从 manifest 加载已构建组件到 state_mgr）
    existing_manifest = None
    if component:
        existing_manifest = load_manifest(cat_id)
        if existing_manifest:
            loaded = []
            for cid, cdata in existing_manifest.get("components", {}).items():
                if cid != component and cdata.get("params"):
                    state_mgr.set_generated(cid, strip_render_metadata(cdata["params"]))
                    loaded.append(cid)
            if loaded:
                print(f"    [锚点] 已加载: {', '.join(loaded)}")

    # 组件列表（配置可指定，默认 4 组件）
    gen_order = spec.get("components", DEFAULT_GEN_ORDER)

    # ★ 优先读 VLM 缓存（由 rebuild_gallery.py 生成）
    vlm_cache = _load_vlm_cache(cat_id)
    if vlm_cache:
        vlm_shape = vlm_cache["merged_vlm_shape"]
        print(f"    [缓存] 使用 VLM 缓存 (built_at={vlm_cache.get('built_at', '?')})")
    else:
        vlm_shape = spec.get("vlm_shape", {})

    render_metadata = build_gallery_render_metadata(
        PROJECT_ROOT,
        cat_id,
        ref_image=spec.get("ref_image"),
        hints=vlm_shape,
    )

    # 链式推导初始参数（锚点感知：已生成的组件用其实际输出参数）
    if state_mgr.is_generated("bottle"):
        bottle_p = _flatten(state_mgr.get_generated("bottle"))
    else:
        # user_dims 来源：VLM 缓存优先，否则从 spec 读取
        if vlm_cache:
            ud = dict(vlm_cache.get("user_dims", {}))
        else:
            ud = dict(spec.get("user_dims") or {})
        th = spec.get("total_height_mm", 100)

        # 无 VLM 缓存时：尝试 CV 推算补全 user_dims
        if not vlm_cache:
            need_cv = ("body_od_mm" not in ud or "neck_od_mm" not in ud)
            ref_image = spec.get("ref_image", "")
            if need_cv and ref_image:
                ref_path = PROJECT_ROOT / ref_image
                if ref_path.exists():
                    try:
                        from auto_pipeline import cv_quick_dims
                        cv_dims = cv_quick_dims(str(ref_path), th)
                        if cv_dims.get("body_od_mm", 0) > 0:
                            ud.setdefault("body_od_mm", cv_dims["body_od_mm"])
                            ud.setdefault("neck_od_mm", cv_dims.get("neck_od_mm", 0))
                            ud.setdefault("height_mm", cv_dims.get("height_mm", 0))
                            print(f"    [CV推算] body_od={ud['body_od_mm']:.1f}mm, "
                                  f"neck_od={ud['neck_od_mm']:.1f}mm")

                            # CV 覆盖 vlm_shape 定量参数
                            cv_cap_h = cv_dims.get("cap_height_mm", 0)
                            cv_taper = cv_dims.get("taper_deg", 0)
                            cv_cap_ratio = cv_dims.get("cap_ratio", 0)
                            cv_cap_od_ratio = cv_dims.get("cap_od_ratio", 1.0)

                            if cv_cap_h > 5:
                                old_cap = vlm_shape.get("cap_height_mm", "N/A")
                                vlm_shape["cap_height_mm"] = cv_cap_h
                                print(f"    [CV覆盖] cap_height: {old_cap} → {cv_cap_h:.1f}mm "
                                      f"(cap_ratio={cv_cap_ratio:.3f})")

                            if cv_taper > 0.3:
                                old_taper = vlm_shape.get("taper_deg", 0)
                                vlm_shape["taper_deg"] = cv_taper
                                vlm_shape["cap_taper_deg"] = cv_taper
                                vlm_shape["shape"] = "taper"
                                vlm_shape["cap_od_base"] = "body_top"
                                print(f"    [CV覆盖] 统一锥度: {old_taper} → {cv_taper:.1f}°")
                            elif cv_taper >= 0:
                                vlm_shape["taper_deg"] = 0
                                vlm_shape["cap_taper_deg"] = 0
                                vlm_shape["shape"] = "cyl"

                            if cv_cap_od_ratio < 0.98:
                                vlm_shape["cap_od_ratio"] = cv_cap_od_ratio

                    except Exception as e:
                        print(f"    [CV推算] 失败: {e}, 使用经验比例回退")

        # 最终回退：经验比例
        ud.setdefault("height_mm", round(th * 0.65, 1))
        ud.setdefault("body_od_mm", round(th * 0.22, 1))
        ud.setdefault("neck_od_mm", round(th * 0.16, 1))
        bottle_p = build_bottle_params(ud, vlm_shape)

    if state_mgr.is_generated("cap"):
        cap_p = _flatten(state_mgr.get_generated("cap"))
    else:
        # 当独立刷杆在构建顺序中时，杆件属于 wand 而非 cap
        # 强制关闭 cap 内置杆件，避免两者空间重叠导致 BRep 干涉
        if "wand" in gen_order and vlm_shape.get("cap_stem_enabled"):
            vlm_shape["cap_stem_enabled"] = False
        cap_p = derive_cap_params(bottle_p, vlm_shape)

    if "wand" in gen_order:
        if state_mgr.is_generated("wand"):
            wand_p = _flatten(state_mgr.get_generated("wand"))
        else:
            wand_p = derive_wand_params(cap_p, bottle_p)
    else:
        wand_p = {}

    if "wiper" in gen_order:
        if state_mgr.is_generated("wiper"):
            wiper_p = _flatten(state_mgr.get_generated("wiper"))
        else:
            # 无 wand 时用 cap stem 参数构造 wiper 所需的杆径/孔径信息
            if wand_p:
                wiper_p = derive_wiper_params(bottle_p, wand_p)
            else:
                stem_d = cap_p.get("stem.diameter_mm", 4.25)
                _pseudo_wand = {
                    "stem_diameter_mm": stem_d,
                    "orifice_mm": stem_d + 1.5,
                }
                wiper_p = derive_wiper_params(bottle_p, _pseudo_wand)
    else:
        wiper_p = {}

    initial_params = {}
    if "bottle" in gen_order:
        initial_params["bottle"] = bottle_p
    if "cap" in gen_order:
        initial_params["cap"] = cap_p
    if "wand" in gen_order:
        initial_params["wand"] = wand_p
    if "wiper" in gen_order:
        initial_params["wiper"] = wiper_p

    # cross_section 一致性广播（全局不变量）
    cs = bottle_p.get("cross_section", "round")
    cr = bottle_p.get("corner_radius_mm", 3.0)
    for cid in ("cap", "wand"):
        if cid in initial_params:
            initial_params[cid]["cross_section"] = cs
            initial_params[cid]["corner_radius_mm"] = cr

    # ── Phase 2: 逐组件生成（复用 Web 高级模式路径） ──
    build_order = [component] if component else gen_order

    components_manifest = {}
    build_solids = {}  # 内存实体，用于 BRep 干涉检测（避免 STEP 导出畸变）
    all_ok = True

    # 继承已有组件数据到 manifest
    if component and existing_manifest:
        for cid, cdata in existing_manifest.get("components", {}).items():
            if cid not in build_order:
                components_manifest[cid] = cdata

    for comp_id in build_order:
        comp = get_component("lip_gloss", comp_id)
        params = initial_params[comp_id]

        # ★ 核心统一点：通过 ComponentStateManager 获取并应用跨组件约束
        params, locked = _apply_web_constraints(comp_id, params, state_mgr)

        # 几何可行性守卫（cap 锥度退化检查 + grip 安全降级）
        if comp_id == "cap":
            _guard_cap_taper(params)
            _guard_cap_grip(params)

        # 扁平→嵌套转换（_fix_finish_spec 和 comp.generate 期望嵌套格式）
        params = _unflatten(params)
        params = _fix_finish_spec(params)

        res = comp.generate(
            preset_id=None,
            user_params=params,
            outroot=str(out_dir),
            title=comp_id,
        )

        if not res.get("ok"):
            err = res.get("error", "建模失败")
            print(f"    [{comp_id}] FAIL: {err}")
            all_ok = False
            continue

        # 打印降级特征（如有）
        meta = res.get("qc", {}).get("modeler_meta", {})
        degraded = meta.get("degraded", [])
        if degraded:
            for d in degraded:
                feat = d.get("feature", "?")
                err = str(d.get("error", ""))[:80]
                print(f"    [降级] {comp_id}.{feat}: {err}")
        thr_st = meta.get("thread_status", {})
        if thr_st:
            print(f"    [螺纹] requested={thr_st.get('requested')}, "
                  f"attempted={thr_st.get('attempted')}, "
                  f"degraded={thr_st.get('degraded')}")

        final_params = res.get("qc", {}).get("params", params)
        state_mgr.set_generated(comp_id, final_params)

        # 保留内存实体（避免 STEP 导出旋转面畸变导致虚假干涉）
        if res.get("solid") is not None:
            build_solids[comp_id] = res["solid"]

        # 收集产物文件（重命名为固定文件名）
        stl_src = res.get("stl")
        step_src = res.get("step")
        comp_files = {}

        if stl_src and os.path.exists(stl_src):
            stl_dst = out_dir / f"{comp_id}.stl"
            shutil.copy2(stl_src, stl_dst)
            comp_files["stl"] = f"{comp_id}.stl"

        if step_src and os.path.exists(step_src):
            step_dst = out_dir / f"{comp_id}.step"
            shutil.copy2(step_src, step_dst)
            comp_files["step"] = f"{comp_id}.step"

        components_manifest[comp_id] = {
            **comp_files,
            "params": attach_render_metadata(final_params, comp_id, render_metadata),
        }
        print(f"    [{comp_id}] OK")
        _print_param_summary(comp_id, final_params)

    # ── Phase 3: 装配 QC + BRep 检测 ──
    generated = state_mgr.get_all_generated()
    positions = {}
    qc_summary = {"ok": all_ok, "warnings": []}
    assembly = None

    if generated:
        try:
            pos = compute_assembly_positions(generated)
            for cid, pdata in pos.items():
                positions[cid] = {"dz": pdata.get("dz", 0.0),
                                  "description": pdata.get("description", "")}
        except Exception as e:
            print(f"    [assembly] 位置计算失败: {e}")

        try:
            assembly = compute_assembly_report(generated)
        except Exception:
            assembly = None

        # BRep 干涉检测（优先使用内存实体，避免 STEP 旋转面导出畸变）
        brep_report = {"ok": True}
        if len(build_solids) >= 2:
            try:
                from core.assembly import check_brep_assembly
                brep_report = check_brep_assembly(generated, solids=build_solids)
                if assembly:
                    assembly["brep_interference"] = brep_report
                if not brep_report.get("ok", True):
                    for pr in brep_report.get("pairs", []):
                        if not pr.get("ok", True):
                            vol = pr.get("volume_mm3", 0)
                            print(f"    [BRep] {pr.get('pair')}: 干涉 {vol:.1f}mm3")
            except Exception as e:
                print(f"    [BRep] 检测失败: {e}")

        # ── Phase 3b: 自修复循环（仅 BRep 干涉，最多 3 轮） ──
        brep_ok = brep_report.get("ok", True)
        if not brep_ok and generated:
            try:
                from core.auto_repair import analyze_and_fix
                print("    [自修复] 检测到 BRep 干涉，启动修复…")

                cur_params = dict(generated)
                repair_log_total = []
                _protected = set()

                for _rd in range(1, 4):
                    # 只传 brep_report，不传 assembly → 只修干涉，不动其他参数
                    _fixed, _rd_log, _protected = analyze_and_fix(
                        cur_params, None,
                        brep_report,
                        _protected)
                    if not _rd_log:
                        break
                    for rl in _rd_log:
                        rl["round"] = _rd
                    repair_log_total.extend(_rd_log)

                    # 重新生成修改过的组件
                    changed = set(r["component"] for r in _rd_log
                                  if r["component"] in build_order)
                    # 按 build_order 顺序重建（而非 set 无序遍历）
                    for _cid in build_order:
                        if _cid not in changed:
                            continue
                        try:
                            _comp = get_component("lip_gloss", _cid)
                            _p = _unflatten(_fixed[_cid])
                            _p = _fix_finish_spec(_p)
                            _res = _comp.generate(
                                preset_id=None, user_params=_p,
                                outroot=str(out_dir), title=_cid,
                            )
                            if _res.get("ok"):
                                _fp = _res.get("qc", {}).get("params", _fixed[_cid])
                                state_mgr.set_generated(_cid, _fp)
                                # 更新内存实体
                                if _res.get("solid") is not None:
                                    build_solids[_cid] = _res["solid"]
                                # 更新产物文件
                                for ext in ("stl", "step"):
                                    src = _res.get(ext)
                                    if src and os.path.exists(src):
                                        dst = out_dir / f"{_cid}.{ext}"
                                        shutil.copy2(src, dst)
                                components_manifest[_cid] = {
                                    "stl": f"{_cid}.stl",
                                    "step": f"{_cid}.step",
                                    "params": attach_render_metadata(_fp, _cid, render_metadata),
                                }
                                print(f"    [修复 R{_rd}] {_cid} 重新生成 OK")
                            else:
                                _err = _res.get("error", "未知错误")
                                print(f"    [修复 R{_rd}] {_cid} 生成失败: {_err}")
                        except Exception as e:
                            print(f"    [修复 R{_rd}] {_cid} 异常: {e}")

                    # 重新检查
                    generated = state_mgr.get_all_generated()
                    assembly = compute_assembly_report(generated)

                    # 重新 BRep 检测（使用内存实体）
                    if len(build_solids) >= 2:
                        brep_report = check_brep_assembly(generated, solids=build_solids)
                        assembly["brep_interference"] = brep_report

                    cur_params = dict(generated)
                    if brep_report.get("ok", True):
                        print(f"    [自修复] R{_rd} 后 BRep 通过 ✓")
                        break

                if repair_log_total:
                    n_fixes = len(repair_log_total)
                    n_rounds = max(r.get("round", 1) for r in repair_log_total)
                    print(f"    [自修复] 共 {n_rounds} 轮, {n_fixes} 项修复")
                    qc_summary["auto_repair"] = {
                        "rounds": n_rounds,
                        "fixes": n_fixes,
                        "log": [r.get("reason", "") for r in repair_log_total],
                    }
            except Exception as e:
                print(f"    [自修复] 失败: {e}")

        # 最终 QC 汇总
        if assembly and not assembly.get("ok", True):
            qc_summary["ok"] = False
            for c in assembly.get("quality", {}).get("checks", []):
                if isinstance(c, dict) and not c.get("ok", True):
                    qc_summary["warnings"].append(c.get("msg", ""))

        # 更新装配位置（可能因自修复而变化）
        try:
            generated = state_mgr.get_all_generated()
            pos = compute_assembly_positions(generated)
            positions = {}
            for cid, pdata in pos.items():
                positions[cid] = {"dz": pdata.get("dz", 0.0),
                                  "description": pdata.get("description", "")}
        except Exception:
            pass

    # ── Phase 4: 写入 manifest.json ──
    for _cid, _data in list(components_manifest.items()):
        if _data.get("params"):
            _data["params"] = attach_render_metadata(
                strip_render_metadata(_data["params"]),
                _cid,
                render_metadata,
            )

    manifest = {
        "cat_id": cat_id,
        "desc": vlm_cache["desc"] if vlm_cache and vlm_cache.get("desc") else spec["desc"],
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "components": components_manifest,
        "assembly_positions": positions,
        "qc_summary": qc_summary,
    }

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description="展览馆预生成脚本")
    parser.add_argument("cat_ids", nargs="*", help="要构建的配置 ID（默认全部）")
    parser.add_argument("--component", "-c", type=str, default=None,
                        choices=["bottle", "cap", "wand", "wiper"],
                        help="仅构建指定组件（逐组件模式）")
    args = parser.parse_args()

    targets = args.cat_ids if args.cat_ids else list(GALLERY_CATALOG.keys())
    invalid = [c for c in targets if c not in GALLERY_CATALOG]
    if invalid:
        print(f"未知配置: {', '.join(invalid)}")
        print(f"可用配置: {', '.join(GALLERY_CATALOG.keys())}")
        sys.exit(1)

    if args.component and not args.cat_ids:
        print("错误: --component 模式必须指定配置 ID")
        sys.exit(1)

    PREBUILT_ROOT.mkdir(parents=True, exist_ok=True)
    total = len(targets)
    ok_count = 0
    fail_list = []

    mode_desc = f"组件={args.component}" if args.component else "全部组件"
    print(f"{'='*60}")
    print(f"展览馆预生成 — {total} 个配置 [{mode_desc}]")
    print(f"输出目录: {PREBUILT_ROOT}")
    print(f"{'='*60}")

    t0 = time.time()
    for i, cat_id in enumerate(targets, 1):
        spec = GALLERY_CATALOG[cat_id]
        print(f"\n[{i}/{total}] {cat_id} — {spec['desc']}")
        t1 = time.time()
        try:
            manifest = build_one(cat_id, spec, component=args.component)
            comp_ok = sum(1 for v in manifest["components"].values()
                         if "stl" in v)
            elapsed = time.time() - t1
            if args.component:
                if args.component in manifest["components"] and \
                   "stl" in manifest["components"][args.component]:
                    print(f"    完成 ({elapsed:.1f}s)")
                    ok_count += 1
                else:
                    print(f"    失败 ({elapsed:.1f}s)")
                    fail_list.append(cat_id)
            else:
                expected = len(spec.get("components", DEFAULT_GEN_ORDER))
                if comp_ok == expected:
                    print(f"    完成 ({elapsed:.1f}s) — {comp_ok}/{expected} 组件成功")
                    ok_count += 1
                else:
                    print(f"    部分完成 ({elapsed:.1f}s) — {comp_ok}/{expected} 组件成功")
                    fail_list.append(cat_id)
        except Exception as e:
            elapsed = time.time() - t1
            print(f"    失败 ({elapsed:.1f}s): {e}")
            fail_list.append(cat_id)

    total_time = time.time() - t0
    print(f"\n{'='*60}")
    print(f"完成: {ok_count}/{total} 成功, 耗时 {total_time:.1f}s")
    if fail_list:
        print(f"失败: {', '.join(fail_list)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
