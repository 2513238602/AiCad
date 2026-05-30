# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
WEB_ROOT = PROJECT_ROOT / "web"
DIST_ROOT = PROJECT_ROOT / "web" / "dist"  # Vue build output
ART_ROOT = PROJECT_ROOT / "artifacts"
PREBUILT_ROOT = ART_ROOT / "gallery_prebuilt"
VLM_CACHE_DIR = ART_ROOT / "vlm_cache"
PICTURE_ROOT = PROJECT_ROOT / "tests" / "picture"

import sys
sys.path.insert(0, str(SRC_ROOT))

from products.lip_gloss.components.registry import schema as registry_schema, get_component
from core.param_system import get_derived_registry, get_nested_value, set_nested_value
from core.component_state import get_state_manager
from core.assembly import compute_assembly_positions, compute_assembly_report
from core.modeler import compute_profile_constraints
from core.drag_handles import compute_drag_handles
from core.render_materials import (
    attach_render_metadata,
    build_gallery_render_metadata,
    strip_render_metadata,
)
# 确保派生规则已注册（包含跨组件规则）
import products.lip_gloss.derived_params  # noqa: F401

SERVER_VERSION = "2026-03-30-v4"


# ════════════════════════════════════════════════════════════════════════
# Gallery 预生成 Manifest 加载
# ════════════════════════════════════════════════════════════════════════

def _load_gallery_manifests() -> dict:
    """扫描 gallery_prebuilt/ 目录，返回 {cat_id: manifest_dict}。"""
    manifests = {}
    if PREBUILT_ROOT.is_dir():
        for d in PREBUILT_ROOT.iterdir():
            if not d.is_dir():
                continue
            mf = d / "manifest.json"
            if mf.exists():
                try:
                    manifests[d.name] = json.loads(mf.read_text("utf-8"))
                except Exception:
                    pass
    return manifests


gallery_manifests: dict = _load_gallery_manifests()


def _fix_finish_spec(params: dict) -> dict:
    """生成前自动修复 finish 规格，使其与实际口径匹配。

    支持三种场景：
    - Wand: thread.crest_dia_mm 偏离 finish 标注 > 2mm → 更新 finish
    - Bottle: neck_od_mm 偏离 finish 标注 > 1mm → 更新 finish
    - Wiper: flange_od_mm 偏离 finish 标注 > 2mm → 更新 finish

    注意：不重算派生参数（由前端 updateDerivedParams 负责），
    避免覆盖跨组件约束锁定的值。
    """
    import copy
    params = copy.deepcopy(params)

    finish = get_nested_value(params, "finish")
    if not finish:
        return params

    # 确定实际口径：
    # - Wand: thread.crest_dia_mm（螺纹峰径）
    # - Bottle: neck_od_mm（颈外径）
    # - Wiper: flange_od_mm（凸环外径）
    thread = params.get("thread", {}) or {}
    crest = thread.get("crest_dia_mm")
    neck_od = params.get("neck_od_mm")
    flange_od = params.get("flange_od_mm")

    ref_dia = None
    threshold = 2.0
    if crest is not None:
        ref_dia = float(crest)
        threshold = 2.0
    elif neck_od is not None:
        ref_dia = float(neck_od)
        threshold = 1.0
    elif flange_od is not None:
        ref_dia = float(flange_od)
        threshold = 2.0

    if ref_dia is not None:
        try:
            parts = str(finish).split("-")
            spec_dia = float(parts[0])
            if abs(ref_dia - spec_dia) > threshold:
                parts[0] = str(int(round(ref_dia)))
                set_nested_value(params, "finish", "-".join(parts))
        except (ValueError, IndexError):
            pass

    return params


def _json_bytes(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _safe_join(root: Path, rel: str) -> Path:
    p = (root / rel.lstrip("/")).resolve()
    if not str(p).startswith(str(root.resolve())):
        raise ValueError("path escape")
    return p


def _file_url(abs_path: str | None) -> str | None:
    if not abs_path:
        return None
    p = Path(abs_path).resolve()
    if not str(p).startswith(str(ART_ROOT.resolve())):
        return None
    rel = p.relative_to(ART_ROOT)
    return "/artifacts/" + "/".join(rel.parts)


def _qc_fail_reason(res: dict) -> str | None:
    if not res:
        return "空结果"
    # 先检查顶层 ok 标志（建模/导出失败）
    if res.get("ok") is False:
        return res.get("error") or "建模失败"
    qc = res.get("qc") or {}
    if not isinstance(qc, dict):
        return None
    if qc.get("ok", True) is True:
        return None
    checks = qc.get("checks") or []
    for c in checks:
        if isinstance(c, dict) and c.get("severity") == "hard" and (c.get("ok") is False):
            return c.get("msg") or "QC hard fail"
    for c in checks:
        if isinstance(c, dict) and (c.get("ok") is False):
            return c.get("msg") or "QC fail"
    return "QC fail"



# ════════════════════════════════════════════════════════════════════════
# Gallery Catalog — 14 分类的 Ground Truth 参数
# ════════════════════════════════════════════════════════════════════════

# ── VLM 缓存加载（rebuild_gallery.py 生成的分析结果）──
def _load_vlm_cache(cat_id: str) -> dict | None:
    cache_file = VLM_CACHE_DIR / f"{cat_id}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


GALLERY_CATALOG = {
    "A1_round_flat": {
        "desc": "圆形直筒+竖纹装饰带+底座台阶+平顶光面盖",
        "ref_image": "tests/picture/A1_round_flat/01_huihe_LG056_round.png",
        "total_height_mm": 100,
    },
    "A2_round_dome": {
        "desc": "圆形直筒+圆顶盖",
        "ref_image": "tests/picture/A2_round_dome/01_topfeel_MA125A_dome.jpg",
        "total_height_mm": 100,
    },
    "A3_round_pointed": {
        "desc": "六边形锥形瓶身+竖纹装饰带+平顶条纹盖",
        "ref_image": "tests/picture/A3_round_pointed/cairui_cone_01.webp",
        "total_height_mm": 109,
        "components": ["bottle", "cap", "wiper"],
    },
    "B1_tapered": {
        "desc": "圆形锥形瓶身",
        "ref_image": "tests/picture/B1_tapered/01_huihe_LG041_taper.png",
        "total_height_mm": 105,
    },
    "B2_barrel": {
        "desc": "桶形/鼓形瓶身",
        "ref_image": "tests/picture/B2_barrel/01_huihe_LG048_barrel.png",
        "total_height_mm": 80,
    },
    "B3_teardrop": {
        "desc": "水滴形瓶身",
        "ref_image": "tests/picture/B3_teardrop/01_huihe_LG043_drop.png",
        "total_height_mm": 90,
    },
    "B4_scurve": {
        "desc": "S形曲线瓶身",
        "ref_image": "tests/picture/B4_scurve/01_huihe_LG047_curve.png",
        "total_height_mm": 100,
    },
    "C1_square_straight": {
        "desc": "方形直筒",
        "ref_image": "tests/picture/C1_square_straight/01_huihe_LG049_square.png",
        "total_height_mm": 100,
    },
    "C2_square_taper": {
        "desc": "方形锥度",
        "ref_image": "tests/picture/C2_square_taper/canda_square_01.webp",
        "total_height_mm": 95,
    },
    "C3_square_rounded": {
        "desc": "大圆角方形",
        "ref_image": "tests/picture/C3_square_rounded/huassin_gradient_01.webp",
        "total_height_mm": 95,
    },
    "D1_textured_cap": {
        "desc": "纹理盖",
        "ref_image": "tests/picture/D1_textured_cap/canda_diamond_01.webp",
        "total_height_mm": 100,
    },
    "D2_mushroom_cap": {
        "desc": "蘑菇盖/大头盖",
        "ref_image": "tests/picture/D2_mushroom_cap/01_kesiyu_pink_bigbrush.webp",
        "total_height_mm": 95,
    },
    "D3_taper_cap": {
        "desc": "锥度盖",
        "ref_image": "tests/picture/D3_taper_cap/canda_crown_01.webp",
        "total_height_mm": 100,
    },
    "D4_smooth_cap": {
        "desc": "光面特殊形状盖",
        "ref_image": "tests/picture/D4_smooth_cap/01_folover_matte_color.webp",
        "total_height_mm": 98,
    },
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, ctype: str, data: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, code: int, obj):
        self._send(code, "application/json; charset=utf-8", _json_bytes(obj))

    def _handle_rebuild(self):
        """一键重建前端（GET/POST 均可调用）"""
        print("[REBUILD] Starting npm run build...", flush=True)
        try:
            import os
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["CHCP"] = "65001"
            result = subprocess.run(
                "npm run build",
                cwd=str(WEB_ROOT),
                capture_output=True, timeout=120,
                shell=True,
                env=env,
            )

            def _safe_decode(b: bytes) -> str:
                if not b:
                    return ""
                for enc in ("utf-8", "gbk", "latin-1"):
                    try:
                        return b.decode(enc)
                    except (UnicodeDecodeError, LookupError):
                        continue
                return b.decode("utf-8", errors="replace")

            stdout = _safe_decode(result.stdout)
            stderr = _safe_decode(result.stderr)
            import re
            stdout = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', stdout)
            stderr = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', stderr)

            if result.returncode == 0:
                print("[REBUILD] Success!", flush=True)
                return self._send_json(200, {
                    "ok": True,
                    "message": "rebuild success",
                    "stdout": stdout[-500:],
                })
            else:
                print(f"[REBUILD] Failed (exit {result.returncode})", flush=True)
                return self._send_json(500, {
                    "ok": False,
                    "error": f"build failed (exit {result.returncode})",
                    "stderr": stderr[-1000:],
                    "stdout": stdout[-500:],
                })
        except subprocess.TimeoutExpired:
            return self._send_json(500, {"ok": False, "error": "build timeout (120s)"})
        except Exception as e:
            import traceback
            return self._send_json(500, {
                "ok": False,
                "error": f"rebuild exception: {e}",
                "traceback": traceback.format_exc()[-500:],
            })

    # ================================================================
    #  Gallery
    # ================================================================
    @staticmethod
    def _build_gallery_item(cat_id: str, spec: dict) -> dict:
        cat_dir = PICTURE_ROOT / cat_id
        thumb = None
        image_count = 0
        if cat_dir.is_dir():
            images = sorted(
                f for f in cat_dir.iterdir()
                if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp')
            )
            image_count = len(images)
            if images:
                thumb = f"/gallery/images/{cat_id}/{images[0].name}"
        # desc 优先级：VLM 缓存 > GALLERY_CATALOG
        vlm_c = _load_vlm_cache(cat_id)
        desc = (vlm_c["desc"] if vlm_c and vlm_c.get("desc") else spec["desc"])
        return {
            "cat_id": cat_id,
            "desc": desc,
            "thumbnail": thumb,
            "image_count": image_count,
            "prebuilt": (PREBUILT_ROOT / cat_id / "manifest.json").exists(),
        }

    def _handle_gallery_list(self):
        """GET /api/gallery — 返回展览馆分类列表（同 group_id 聚合为一个 item + variants）"""
        # 按 group_id 分组
        groups: dict[str, list[str]] = {}
        for cat_id, spec in GALLERY_CATALOG.items():
            gid = spec.get("group_id")
            if gid:
                groups.setdefault(gid, []).append(cat_id)

        items = []
        seen_groups: set[str] = set()
        for cat_id, spec in GALLERY_CATALOG.items():
            gid = spec.get("group_id")
            if gid:
                if gid in seen_groups:
                    continue
                seen_groups.add(gid)
                group_cats = groups[gid]
                primary = group_cats[0]
                primary_spec = GALLERY_CATALOG[primary]
                variants = []
                for vc in group_cats:
                    vs = GALLERY_CATALOG[vc]
                    variants.append({
                        "cat_id": vc,
                        "label": vs.get("variant_label", vc),
                        "desc": vs["desc"],
                        "prebuilt": (PREBUILT_ROOT / vc / "manifest.json").exists(),
                    })
                item = self._build_gallery_item(primary, primary_spec)
                item["variants"] = variants
                items.append(item)
            else:
                items.append(self._build_gallery_item(cat_id, spec))
        return self._send_json(200, {"items": items})

    def _handle_gallery_prebuilt(self, cat_id: str):
        """GET /api/gallery/prebuilt/{cat_id} — 返回预生成的 STL URL + 装配位置。"""
        global gallery_manifests
        # 每次请求都从磁盘读取，确保 prebuild_gallery 更新后刷新即可见
        mf = PREBUILT_ROOT / cat_id / "manifest.json"
        if mf.exists():
            try:
                manifest = json.loads(mf.read_text("utf-8"))
                gallery_manifests[cat_id] = manifest  # 同步更新缓存供列表接口用
            except Exception:
                manifest = gallery_manifests.get(cat_id)
        else:
            manifest = gallery_manifests.get(cat_id)
        if not manifest:
            return self._send_json(404, {"error": "预生成数据不存在", "cat_id": cat_id})

        spec = GALLERY_CATALOG.get(cat_id, {})
        vlm_cache = _load_vlm_cache(cat_id) or {}
        render_metadata = build_gallery_render_metadata(
            PROJECT_ROOT,
            cat_id,
            ref_image=spec.get("ref_image"),
            hints=vlm_cache.get("merged_vlm_shape") or spec.get("vlm_shape") or {},
        )

        results = {}
        for comp_id, comp_data in manifest.get("components", {}).items():
            stl_file = comp_data.get("stl")
            if not stl_file:
                continue
            stl_path = PREBUILT_ROOT / cat_id / stl_file
            if not stl_path.exists():
                continue
            results[comp_id] = {
                "ok": True,
                "stl_url": f"/artifacts/gallery_prebuilt/{cat_id}/{stl_file}",
                "qc": {
                    "params": attach_render_metadata(
                        strip_render_metadata(comp_data.get("params", {})),
                        comp_id,
                        render_metadata,
                    ),
                },
            }

        # 兼容旧格式（纯数字）和新格式（{dz, description}）
        raw_pos = manifest.get("assembly_positions", {})
        positions = {}
        for cid, val in raw_pos.items():
            if isinstance(val, dict):
                positions[cid] = val
            else:
                positions[cid] = {"dz": float(val), "description": ""}

        return self._send_json(200, {
            "ok": True,
            "cat_id": cat_id,
            "results": results,
            "assembly": {"positions": positions},
        })

    def _handle_gallery_generate(self, cat_id: str):
        """POST /api/gallery/generate/{cat_id}
        通过标准 comp.generate() 管线生成，与手动/VLM 完全一致。
        参数来源为 GALLERY_CATALOG 中的 Ground Truth。
        """
        if cat_id not in GALLERY_CATALOG:
            return self._send_json(404, {"error": f"unknown category: {cat_id}"})

        spec = GALLERY_CATALOG[cat_id]
        gen_order = ["bottle", "cap", "wand", "wiper"]

        # ── Phase 1: 参数合成（与 VLM 相同的链式合成 + 全局协调） ──
        from core.vlm_extract import (
            build_bottle_params, derive_cap_params,
            derive_wand_params, derive_wiper_params,
            reconcile_all_params,
        )

        # ★ 读 VLM 缓存（由 rebuild_gallery.py 生成）
        vlm_cache = _load_vlm_cache(cat_id)
        if vlm_cache:
            vlm_shape = vlm_cache["merged_vlm_shape"]
            ud = dict(vlm_cache.get("user_dims", {}))
        else:
            vlm_shape = {}
            ud = {}

        render_metadata = build_gallery_render_metadata(
            PROJECT_ROOT,
            cat_id,
            ref_image=spec.get("ref_image"),
            hints=vlm_shape,
        )

        th = spec.get("total_height_mm", 100)
        ud.setdefault("height_mm", round(th * 0.65, 1))
        ud.setdefault("body_od_mm", round(th * 0.22, 1))
        ud.setdefault("neck_od_mm", round(th * 0.16, 1))

        try:
            bottle_p = build_bottle_params(ud, vlm_shape)
            cap_p = derive_cap_params(bottle_p, vlm_shape)
            wand_p = derive_wand_params(cap_p, bottle_p)
            wiper_p = derive_wiper_params(bottle_p, wand_p)
            # 全局协调：复用 DerivedRule + CrossComponentDerived 规则
            all_params = {"bottle": bottle_p, "cap": cap_p,
                          "wand": wand_p, "wiper": wiper_p}
            all_params, reconcile_report = reconcile_all_params(all_params)
        except Exception as e:
            return self._send_json(500, {"error": f"参数合成失败: {e}"})

        # ── Phase 2: 逐组件标准管线（与 VLM/手动一致） ──
        state_mgr = get_state_manager()
        state_mgr.clear()  # 清空旧状态

        results = {}
        for comp_id in gen_order:
            try:
                comp = get_component("lip_gloss", comp_id)
                params = _fix_finish_spec(all_params[comp_id])
                res = comp.generate(
                    preset_id=None,
                    user_params=params,
                    outroot=str(ART_ROOT / "webui"),
                    title=f"gallery_{cat_id}_{comp_id}",
                )

                reason = _qc_fail_reason(res) if not res.get("ok") else None
                if reason:
                    results[comp_id] = {"ok": False, "error": reason}
                    continue

                final_params = res.get("qc", {}).get("params", params)
                state_mgr.set_generated(comp_id, final_params)
                qc = dict(res.get("qc") or {})
                qc["params"] = attach_render_metadata(final_params, comp_id, render_metadata)

                results[comp_id] = {
                    "ok": True,
                    "stl_url": _file_url(res.get("stl")),
                    "step_url": _file_url(res.get("step")),
                    "step_path": res.get("step"),  # 保留原始路径供 BRep 检测
                    "svg_url": _file_url(res.get("svg")),
                    "qc": qc,
                }
            except Exception as e:
                results[comp_id] = {"ok": False, "error": str(e)[:300]}

        # ── Phase 3: 装配报告（通过 state_mgr，标准路径） ──
        try:
            generated = state_mgr.get_all_generated()
            # 收集各组件 geometry_qc 元数据，传入装配报告
            geometry_meta = {}
            for _cid in gen_order:
                _meta = (results.get(_cid, {}).get("qc", {})
                         .get("modeler_meta", {}).get("geometry_qc"))
                if _meta:
                    geometry_meta[_cid] = _meta
            assembly = compute_assembly_report(
                generated, geometry_meta=geometry_meta or None
            ) if generated else {}
        except Exception:
            assembly = {}

        # ── Phase 3b: L7 BRep 装配干涉检测 ──
        try:
            import os as _os
            step_files = {}
            for _cid in gen_order:
                _sp = results.get(_cid, {}).get("step_path")
                if _sp and _os.path.exists(_sp):
                    step_files[_cid] = _sp
            if len(step_files) >= 2 and generated:
                from core.assembly import check_brep_assembly
                brep = check_brep_assembly(generated, step_files=step_files)
                assembly["brep_interference"] = brep
        except Exception:
            pass  # BRep 检测失败不阻塞整体流程

        # ── Phase 3c: 自修复循环（最多 3 轮） ──
        try:
            assy_ok = assembly.get("ok", True) if assembly else True
            brep_ok = assembly.get("brep_interference", {}).get("ok", True)

            if (not assy_ok or not brep_ok) and generated:
                from core.auto_repair import analyze_and_fix
                import os as _os2

                cur_params = dict(generated)
                repair_log_total = []
                _protected = set()

                for _rd in range(1, 4):
                    _fixed, _rd_log, _protected = analyze_and_fix(
                        cur_params, assembly,
                        assembly.get("brep_interference"),
                        _protected)
                    if not _rd_log:
                        break
                    repair_log_total.extend(_rd_log)

                    # 重新生成修改过的组件
                    changed = set(r["component"] for r in _rd_log
                                  if r["component"] in gen_order)
                    for _cid in changed:
                        try:
                            _comp = get_component("lip_gloss", _cid)
                            _p = _fix_finish_spec(_fixed[_cid])
                            _res = _comp.generate(
                                preset_id=None, user_params=_p,
                                outroot=str(ART_ROOT / "webui"),
                                title=f"gallery_{cat_id}_{_cid}_r{_rd}",
                            )
                            if _res.get("ok"):
                                _fp = _res.get("qc", {}).get("params", _p)
                                state_mgr.set_generated(_cid, _fp)
                                _qc = dict(_res.get("qc") or {})
                                _qc["params"] = attach_render_metadata(
                                    _fp,
                                    _cid,
                                    render_metadata,
                                )
                                results[_cid] = {
                                    "ok": True,
                                    "stl_url": _file_url(_res.get("stl")),
                                    "step_url": _file_url(_res.get("step")),
                                    "step_path": _res.get("step"),
                                    "svg_url": _file_url(_res.get("svg")),
                                    "qc": _qc,
                                    "repaired": True,
                                    "repair_round": _rd,
                                }
                        except Exception:
                            pass

                    # 重新检查
                    generated = state_mgr.get_all_generated()
                    _geo_meta = {}
                    for _c2 in gen_order:
                        _m2 = (results.get(_c2, {}).get("qc", {})
                               .get("modeler_meta", {}).get("geometry_qc"))
                        if _m2:
                            _geo_meta[_c2] = _m2
                    assembly = compute_assembly_report(
                        generated, geometry_meta=_geo_meta or None)

                    # 重新 BRep 检测
                    _brep2 = {"ok": True}
                    _sf2 = {}
                    for _c3 in gen_order:
                        _sp2 = results.get(_c3, {}).get("step_path")
                        if _sp2 and _os2.path.exists(_sp2):
                            _sf2[_c3] = _sp2
                    if len(_sf2) >= 2:
                        from core.assembly import check_brep_assembly as _cba
                        _brep2 = _cba(generated, step_files=_sf2)
                        assembly["brep_interference"] = _brep2

                    cur_params = dict(generated)
                    if assembly.get("ok") and _brep2.get("ok", True):
                        break

                if repair_log_total:
                    assembly["auto_repair"] = {
                        "rounds": repair_log_total[-1].get("round", 1)
                                  if "round" in repair_log_total[-1]
                                  else len(set(r.get("round", 1) for r in repair_log_total)),
                        "fixes": len(repair_log_total),
                        "log": repair_log_total,
                    }
        except Exception:
            pass  # 自修复失败不阻塞

        ok_count = sum(1 for v in results.values() if v.get("ok"))
        # 装配 QC：仅径向硬干涉判定为失败
        # 外观/语义 QC soft fail 不阻塞生成（作为 warnings 报告给前端）
        assy_hard_fail = assembly.get("hard_count", 0) > 0 if assembly else False
        overall_ok = ok_count > 0 and not assy_hard_fail
        return self._send_json(200, {
            "ok": overall_ok,
            "cat_id": cat_id,
            "results": results,
            "assembly": assembly,
        })

    # ================================================================
    #  异形瓶盖生成
    # ================================================================
    def _handle_exotic_cap_generate(self):
        """POST /api/exotic_cap/generate — 异形瓶盖完整管线"""
        try:
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n) if n > 0 else b"{}"
            req = json.loads(raw.decode("utf-8"))
        except Exception as e:
            return self._send_json(400, {"error": f"bad json: {e}"})

        preset_id = req.get("preset_id")
        if not preset_id:
            return self._send_json(400, {"error": "missing preset_id"})

        target_od_mm = float(req.get("target_od_mm", 24.0))
        target_height_mm = req.get("target_height_mm")
        if target_height_mm is not None:
            target_height_mm = float(target_height_mm)

        # 从已生成的 bottle / wand 参数自动推导内腔尺寸
        inner_radius_mm = req.get("inner_radius_mm")
        cavity_depth_mm = req.get("cavity_depth_mm")
        has_wand = bool(req.get("has_wand", False))

        state_mgr = get_state_manager()
        bottle_state = state_mgr.get_generated("bottle")
        wand_state = state_mgr.get_generated("wand")
        if wand_state:
            has_wand = True

        if bottle_state and inner_radius_mm is None:
            neck_od = bottle_state.get("neck_od_mm")
            if neck_od:
                if has_wand:
                    inner_radius_mm = float(neck_od) / 2 + 2.0   # 螺纹留空
                else:
                    inner_radius_mm = float(neck_od) / 2 + 0.15  # 摩擦配合
        # 无 bottle 时传 None，让 mesh_cap 用标准比例推算

        if inner_radius_mm is not None:
            inner_radius_mm = float(inner_radius_mm)
        if cavity_depth_mm is not None:
            cavity_depth_mm = float(cavity_depth_mm)
        simplify_to = req.get("simplify_to", None)
        if simplify_to is not None:
            simplify_to = int(simplify_to)

        # 内置杆参数：从 bottle 推导杆长，默认杆径 4mm
        stem_diameter_mm = float(req.get("stem_diameter_mm", 4.0))
        stem_length_mm = req.get("stem_length_mm")
        if stem_length_mm is not None:
            stem_length_mm = float(stem_length_mm)
        elif bottle_state:
            inner_depth = bottle_state.get("inner_depth_mm")
            if inner_depth:
                stem_length_mm = float(inner_depth) - 3.0  # 底部留 3mm 余量

        try:
            from core.mesh_cap import generate_exotic_cap
            result = generate_exotic_cap(
                ART_ROOT / "exotic_presets",
                preset_id,
                target_od_mm=target_od_mm,
                target_height_mm=target_height_mm,
                inner_radius_mm=inner_radius_mm,
                cavity_depth_mm=cavity_depth_mm,
                simplify_to=simplify_to,
                has_wand=has_wand,
                stem_diameter_mm=stem_diameter_mm,
                stem_length_mm=stem_length_mm,
                out_dir=ART_ROOT / "webui" / "exotic_cap",
            )
        except Exception as e:
            return self._send_json(500, {"error": f"generate failed: {e}"})

        # 成功后注册到状态管理器（让下游 wand/wiper 约束生效）
        if result.get("ok"):
            fp = result.get("final_params", {})
            state_mgr.set_generated("cap", {
                "outer_od_mm": fp.get("outer_od_mm", target_od_mm),
                "inner_id_mm": fp.get("inner_id_mm"),
                "cavity_depth_mm": fp.get("cavity_depth_mm"),
                "height_mm": fp.get("height_mm"),
                "exotic": True,
                "has_wand": has_wand,
                "stem": {
                    "enabled": True,
                    "diameter_mm": fp.get("stem_diameter_mm", 4.0),
                    "length_mm": fp.get("stem_length_mm", 55.0),
                },
                "brush": {"length_mm": 0},  # 异形盖暂无刷头网格
            })
            result["stl_url"] = _file_url(result.get("stl"))

            # 计算装配报告
            try:
                generated = state_mgr.get_all_generated()
                if generated:
                    result["assembly"] = compute_assembly_report(generated)
            except Exception:
                pass

        return self._send_json(200, result)

    # ================================================================
    #  GET
    # ================================================================
    def do_GET(self):
        u = urlparse(self.path)
        path = u.path

        if path == "/api/ping":
            return self._send_json(200, {"version": SERVER_VERSION})

        if path == "/api/rebuild":
            return self._handle_rebuild()

        if path == "/api/schema":
            return self._send_json(200, registry_schema())

        if path == "/api/derived_rules":
            registry = get_derived_registry()
            return self._send_json(200, registry.export_for_frontend())

        if path == "/api/state":
            state_mgr = get_state_manager()
            return self._send_json(200, state_mgr.export_state())

        if path == "/api/gallery":
            return self._handle_gallery_list()

        if path.startswith("/api/gallery/prebuilt/"):
            cat_id = path[len("/api/gallery/prebuilt/"):]
            return self._handle_gallery_prebuilt(cat_id)

        if path.startswith("/gallery/images/"):
            rel = unquote(path[len("/gallery/images/"):])
            try:
                p = _safe_join(PICTURE_ROOT, rel)
            except Exception as e:
                return self._send_json(400, {"error": str(e)})
            if not p.exists() or not p.is_file():
                return self._send_json(404, {"error": "image not found"})
            ctype, _ = mimetypes.guess_type(str(p))
            return self._send(200, (ctype or "image/jpeg"), p.read_bytes())

        # ── 异形瓶盖：预设列表 ──
        if path == "/api/exotic_cap/presets":
            from core.mesh_cap import list_presets
            presets = list_presets(ART_ROOT / "exotic_presets")
            return self._send_json(200, {"presets": presets})

        if path == "/api/assembly":
            state_mgr = get_state_manager()
            generated = state_mgr.get_all_generated()
            # 支持 ?components=bottle,cap 过滤：只计算 viewer 中实际存在的组件
            qs = parse_qs(u.query)
            comp_filter = qs.get("components", [None])[0]
            if comp_filter:
                wanted = set(c.strip() for c in comp_filter.split(",") if c.strip())
                generated = {k: v for k, v in generated.items() if k in wanted}
            if not generated:
                return self._send_json(200, {
                    "positions": {},
                    "interference": [],
                    "ok": True,
                    "hard_count": 0,
                    "soft_count": 0,
                    "summary": "无已生成组件",
                })
            report = compute_assembly_report(generated)
            return self._send_json(200, report)

        if path.startswith("/api/constraints/"):
            component = path[len("/api/constraints/"):]
            if not component:
                return self._send_json(400, {"error": "missing component"})
            state_mgr = get_state_manager()
            constraints = state_mgr.get_all_constraints_for_component(component)
            return self._send_json(200, {
                "component": component,
                "constraints": constraints,
                "generated": list(state_mgr.get_all_generated().keys()),
            })

        if path.startswith("/api/drag_handles/"):
            component = path[len("/api/drag_handles/"):]
            if not component:
                return self._send_json(400, {"error": "missing component"})
            qs = parse_qs(u.query)
            params_raw = qs.get("params", ["{}"])[0]
            try:
                params = json.loads(params_raw)
            except Exception as e:
                return self._send_json(400, {"error": f"bad params json: {e}"})
            handles = compute_drag_handles(component, params)
            return self._send_json(200, {"component": component, "handles": handles})

        if path.startswith("/api/profile_constraints/"):
            component = path[len("/api/profile_constraints/"):]
            if not component:
                return self._send_json(400, {"error": "missing component"})
            qs = parse_qs(u.query)
            params_raw = qs.get("params", ["{}"])[0]
            try:
                params = json.loads(params_raw)
            except Exception as e:
                return self._send_json(400, {"error": f"bad params json: {e}"})
            try:
                result = compute_profile_constraints(component, params)
                return self._send_json(200, result)
            except ValueError as e:
                return self._send_json(400, {"error": str(e)})
            except Exception as e:
                return self._send_json(500, {"error": f"compute failed: {e}"})

        if path == "/" or path == "/index.html":
            p = DIST_ROOT / "index.html"
            if not p.exists():
                p = WEB_ROOT / "index.html"
            if not p.exists():
                return self._send_json(404, {"error": "web/index.html not found"})
            return self._send(200, "text/html; charset=utf-8", p.read_bytes())

        # Vite 构建产物静态资源 (JS/CSS)
        if path.startswith("/assets/"):
            rel = unquote(path[len("/assets/"):])
            try:
                p = _safe_join(DIST_ROOT / "assets", rel)
            except Exception as e:
                return self._send_json(400, {"error": str(e)})
            if not p.exists() or not p.is_file():
                return self._send_json(404, {"error": "not found"})
            ctype, _ = mimetypes.guess_type(str(p))
            return self._send(200, (ctype or "application/octet-stream"), p.read_bytes())

        if path.startswith("/artifacts/"):
            rel = path[len("/artifacts/"):]
            try:
                p = _safe_join(ART_ROOT, rel)
            except Exception as e:
                return self._send_json(400, {"error": str(e)})
            if not p.exists() or not p.is_file():
                return self._send_json(404, {"error": "not found"})
            ctype, _ = mimetypes.guess_type(str(p))
            return self._send(200, (ctype or "application/octet-stream"), p.read_bytes())

        if path.startswith("/web/"):
            rel = unquote(path[len("/web/"):])
            try:
                p = _safe_join(WEB_ROOT, rel)
            except Exception as e:
                return self._send_json(400, {"error": str(e)})
            if not p.exists() or not p.is_file():
                return self._send_json(404, {"error": "not found"})
            ctype, _ = mimetypes.guess_type(str(p))
            return self._send(200, (ctype or "application/octet-stream"), p.read_bytes())

        return self._send_json(404, {"error": "unknown route"})

    # ================================================================
    #  DELETE
    # ================================================================
    def do_DELETE(self):
        u = urlparse(self.path)
        path = u.path

        if path == "/api/generated":
            state_mgr = get_state_manager()
            state_mgr.clear()
            return self._send_json(200, {"ok": True, "message": "all cleared"})

        if path.startswith("/api/generated/"):
            component = path[len("/api/generated/"):]
            if not component:
                return self._send_json(400, {"error": "missing component"})
            state_mgr = get_state_manager()
            state_mgr.clear(component)
            return self._send_json(200, {"ok": True, "component": component})

        return self._send_json(404, {"error": "unknown route"})

    # ================================================================
    #  POST
    # ================================================================
    def do_POST(self):
        u = urlparse(self.path)
        path = u.path

        # 一键重建前端
        if path == "/api/rebuild":
            return self._handle_rebuild()

        # 存储已生成组件的参数
        if path.startswith("/api/generated/"):
            component = path[len("/api/generated/"):]
            if not component:
                return self._send_json(400, {"error": "missing component"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(n) if n > 0 else b"{}"
                req = json.loads(raw.decode("utf-8"))
            except Exception as e:
                return self._send_json(400, {"error": f"bad json: {e}"})

            params = req.get("params", {})
            state_mgr = get_state_manager()
            state_mgr.set_generated(component, params)
            return self._send_json(200, {
                "ok": True,
                "component": component,
                "param_count": len(params),
            })

        # ── Gallery 即时生成 ────────────────────────────────────
        if path.startswith("/api/gallery/generate/"):
            cat_id = path[len("/api/gallery/generate/"):]
            return self._handle_gallery_generate(cat_id)

        # ── 异形瓶盖生成 ─────────────────────────────────────
        if path == "/api/exotic_cap/generate":
            return self._handle_exotic_cap_generate()

        # ── VLM 图片一键生成（SSE 流式进度）────────────────────
        if path == "/api/vlm/generate":
            return self._handle_vlm_generate()

        if path != "/api/generate":
            return self._send_json(404, {"error": "unknown route"})

        try:
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n) if n > 0 else b"{}"
            req = json.loads(raw.decode("utf-8"))
        except Exception as e:
            return self._send_json(400, {"error": f"bad json: {e}"})

        product = req.get("product", "lip_gloss")
        component = req.get("component", "cap")
        preset_id = req.get("preset_id", None)
        params = req.get("params", {}) or {}
        title = req.get("title", None)

        # 生成前自动修复 finish 规格（不重算派生参数，避免覆盖跨组件约束）
        params = _fix_finish_spec(params)

        try:
            comp = get_component(product, component)
        except Exception as e:
            return self._send_json(400, {"error": str(e)})

        # 重新生成前先清除该组件的旧状态，防止自身约束自身
        try:
            state_mgr = get_state_manager()
            state_mgr.clear(component)
        except Exception:
            pass

        t0 = None
        _time_mod = None
        try:
            import time as _time_mod
            t0 = _time_mod.perf_counter()
        except Exception:
            t0 = None
            _time_mod = None

        try:
            outroot = str(ART_ROOT / "webui")
            res = comp.generate(preset_id=preset_id, user_params=params, outroot=outroot, title=title)

            try:
                if t0 is not None and _time_mod is not None:
                    res["time_sec"] = round(_time_mod.perf_counter() - t0, 3)
            except Exception:
                pass

            # QC 不通过 => 强制 FAIL
            reason = _qc_fail_reason(res)
            if reason is not None:
                res["ok"] = False
                res["error"] = res.get("error") or f"QC_FAIL: {reason}"
                res["step"] = None
                res["stl"] = None
                res["svg"] = None
                res["step_url"] = None
                res["stl_url"] = None
                res["svg_url"] = None
                return self._send_json(200, res)

            res["step_url"] = _file_url(res.get("step"))
            res["stl_url"] = _file_url(res.get("stl"))
            res["svg_url"] = _file_url(res.get("svg"))

            # 自动存储组件参数到状态管理器
            try:
                state_mgr = get_state_manager()
                final_params = res.get("qc", {}).get("params", params)
                state_mgr.set_generated(component, final_params)
                res["state_saved"] = True
            except Exception:
                res["state_saved"] = False

            # 计算装配位置和干涉报告
            try:
                state_mgr = get_state_manager()
                generated = state_mgr.get_all_generated()
                if generated:
                    assembly = compute_assembly_report(generated)
                    res["assembly"] = assembly
            except Exception:
                pass

            # 移除不可序列化的 CadQuery 对象
            res.pop("solid", None)

            return self._send_json(200, res)

        except Exception as e:
            return self._send_json(500, {"error": f"generate failed: {e}"})

    # ================================================================
    #  VLM 图片一键生成（SSE 流式进度推送）
    # ================================================================
    def _handle_vlm_generate(self):
        """图片 → auto_pipeline(CV+VLM) → 4 组件生成 → 装配，全程 SSE 推送进度"""
        import time as _t

        try:
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n) if n > 0 else b"{}"
            req = json.loads(raw.decode("utf-8"))
        except Exception as e:
            return self._send_json(400, {"error": f"bad json: {e}"})

        image_b64 = req.get("image_b64", "")
        if not image_b64:
            return self._send_json(400, {"error": "missing image_b64"})

        # height_mm = 总产品高度（盖+瓶），auto_pipeline 从中推算瓶身/盖子各自高度
        total_height_mm = float(req.get("height_mm", 100))
        # 前端滑条值作为 CV 自动推算的兜底/校验参照
        user_body_od = float(req.get("body_od_mm", 0))
        user_neck_od = float(req.get("neck_od_mm", 0))

        # SSE 头
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        def sse(data: dict):
            line = f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()

        results = {}  # 收集各组件结果

        try:
            # 进度映射: vlm=0~15%, bottle=15~40%, cap=40~60%, wand=60~75%, wiper=75~90%, assembly=90~100%
            PROG = {"vlm": (0, 15), "bottle": (15, 40), "cap": (40, 60),
                    "wand": (60, 75), "wiper": (75, 90), "assembly": (90, 100)}

            def sse_p(step, status, message, **kw):
                """带进度百分比的 SSE 推送"""
                lo, hi = PROG.get(step, (0, 0))
                pct = hi if status == "done" else lo
                sse({"step": step, "status": status, "message": message,
                     "progress": pct, **kw})

            # ── Phase 1: auto_pipeline (BiRefNet + CV + VLM) ──
            sse_p("vlm", "running", "① BiRefNet 背景剔除 + CV 定量 + VLM 定性分析...")

            import tempfile, base64 as b64mod, os as _os
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png")
            try:
                with _os.fdopen(tmp_fd, "wb") as f:
                    f.write(b64mod.b64decode(image_b64))

                # 导入 auto_pipeline（scripts/ 目录）
                _scripts_dir = str(PROJECT_ROOT / "scripts")
                if _scripts_dir not in sys.path:
                    sys.path.insert(0, _scripts_dir)
                from auto_pipeline import run_pipeline

                def _pipeline_progress(msg, pct):
                    sse({"step": "vlm", "status": "running",
                         "message": msg, "progress": pct})

                # 传入用户滑条值：CV 优先，滑条值作为兜底
                pipeline_result = run_pipeline(
                    tmp_path, total_height_mm,
                    body_od_mm=user_body_od, neck_od_mm=user_neck_od,
                    progress_cb=_pipeline_progress)

                if "error" in pipeline_result:
                    sse_p("vlm", "error",
                          f"Pipeline 失败: {pipeline_result['error']}")
                    sse({"step": "complete", "status": "done",
                         "message": "分析失败", "results": {}, "progress": 100})
                    return

                sse({"step": "vlm", "status": "running",
                     "message": "合成组件参数...", "progress": 12})

                # 从 pipeline 结果构建组件参数
                ud = pipeline_result["user_dims"]
                merged_vs = pipeline_result["merged_vlm_shape"]
                vlm_desc = pipeline_result.get("vlm_description", "")

                from core.vlm_extract import (
                    build_bottle_params, derive_cap_params,
                    derive_wand_params, derive_wiper_params,
                    reconcile_all_params)

                bottle_p = build_bottle_params(ud, merged_vs)
                cap_p = derive_cap_params(bottle_p, merged_vs)
                wand_p = derive_wand_params(cap_p, bottle_p)
                wiper_p = derive_wiper_params(bottle_p, wand_p)

                all_p = {"bottle": bottle_p, "cap": cap_p,
                         "wand": wand_p, "wiper": wiper_p}
                all_p, _ = reconcile_all_params(all_p)

                all_params = {
                    "description": vlm_desc,
                    "vlm_shape": merged_vs,
                    "bottle": all_p["bottle"],
                    "cap": all_p["cap"],
                    "wand": all_p["wand"],
                    "wiper": all_p["wiper"],
                }

            except Exception as e:
                sse_p("vlm", "error", f"Pipeline 失败: {e}")
                sse({"step": "complete", "status": "done",
                     "message": "分析失败", "results": {}, "progress": 100})
                return
            finally:
                try:
                    _os.unlink(tmp_path)
                except OSError:
                    pass

            desc = all_params.get("description", "")[:150]
            vlm_shape = all_params.get("vlm_shape", {})
            confidence = vlm_shape.get("confidence", 0)
            shape_desc = vlm_shape.get("shape_description", desc[:60])
            sse_p("vlm", "done", shape_desc,
                  description=desc, confidence=confidence)

            # ── Phase 2: 逐组件生成 ──
            gen_order = ["bottle", "cap", "wand", "wiper"]
            state_mgr = get_state_manager()
            state_mgr.clear()  # 清空旧状态

            for comp_id in gen_order:
                sse_p(comp_id, "running", f"正在生成 {comp_id}...")
                t0 = _t.perf_counter()
                try:
                    comp = get_component("lip_gloss", comp_id)
                    params = _fix_finish_spec(all_params[comp_id])
                    res = comp.generate(
                        preset_id=None,
                        user_params=params,
                        outroot=str(ART_ROOT / "webui"),
                        title=f"vlm_{comp_id}",
                    )
                    dt = round(_t.perf_counter() - t0, 2)
                    reason = _qc_fail_reason(res)
                    if reason is not None:
                        sse_p(comp_id, "error",
                              f"QC 失败: {reason}", time_sec=dt)
                        results[comp_id] = {"ok": False, "error": reason}
                        continue

                    stl_url = _file_url(res.get("stl"))
                    step_url = _file_url(res.get("step"))

                    # 存储到状态管理器（用于跨组件约束）
                    final_params = res.get("qc", {}).get("params", params)
                    state_mgr.set_generated(comp_id, final_params)

                    results[comp_id] = {
                        "ok": True,
                        "stl_url": stl_url,
                        "step_url": step_url,
                        "svg_url": _file_url(res.get("svg")),
                        "qc": res.get("qc"),
                        "time_sec": dt,
                    }
                    sse_p(comp_id, "done",
                          f"{comp_id} 生成完成 ({dt}s)",
                          stl_url=stl_url, step_url=step_url, time_sec=dt)

                except Exception as e:
                    dt = round(_t.perf_counter() - t0, 2)
                    sse_p(comp_id, "error",
                          str(e)[:200], time_sec=dt)
                    results[comp_id] = {"ok": False, "error": str(e)}

            # ── Phase 3: 装配 ──
            sse_p("assembly", "running", "装配检查...")
            try:
                generated = state_mgr.get_all_generated()
                assembly = compute_assembly_report(generated) if generated else {}
                results["assembly"] = assembly
                sse_p("assembly", "done", "装配检查完成",
                      assembly=assembly)
            except Exception as e:
                sse_p("assembly", "error", str(e)[:200])

            # ── 完成 ──
            ok_count = sum(1 for k in gen_order if results.get(k, {}).get("ok"))
            sse({"step": "complete", "status": "done", "progress": 100,
                 "message": f"完成！{ok_count}/4 组件生成成功",
                 "results": results})

        except Exception as e:
            sse({"step": "error", "status": "error", "message": str(e)[:300]})


def _kill_old_processes_on_port(port: int):
    """启动前自动杀掉占用同一端口的旧进程（Windows）"""
    import os
    try:
        result = subprocess.run(
            f'netstat -ano | findstr ":{port}.*LISTENING"',
            shell=True, capture_output=True, text=True, timeout=5,
        )
        my_pid = os.getpid()
        killed = []
        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5:
                try:
                    pid = int(parts[-1])
                    if pid != my_pid and pid > 0:
                        subprocess.run(f"taskkill /F /PID {pid}", shell=True,
                                       capture_output=True, timeout=5)
                        killed.append(pid)
                except (ValueError, subprocess.TimeoutExpired):
                    pass
        if killed:
            print(f"[WEB] Killed old processes on port {port}: {killed}")
            import time
            time.sleep(0.5)  # 等待端口释放
    except Exception as e:
        print(f"[WEB] Warning: could not check port {port}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8010)
    args = ap.parse_args()

    # 自动清理占用端口的旧进程
    _kill_old_processes_on_port(args.port)

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[WEB] http://{args.host}:{args.port}")
    print(f"[WEB] Server version: {SERVER_VERSION}")
    print(f"[WEB] DIST_ROOT: {DIST_ROOT} exists={DIST_ROOT.exists()}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
