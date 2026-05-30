# -*- coding: utf-8 -*-
"""
图片输入 → VLM提取 → 4组件生成  端到端测试管线

每个分类目录取第一张图片，走完整管线：
  图片 → VLM两步提取 → 参数合成 → bottle/cap/wand/wiper 生成 → 合法性验证

用法:
    set GLM_API_KEY=xxx
    set PYTHONPATH=src
    python tests/test_image_pipeline.py [--category A1_round_flat] [--skip-vlm]
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
import traceback
from pathlib import Path

# 编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from core.vlm_extract import (
    extract_and_build_all,
    build_bottle_params,
    derive_cap_params,
    derive_wand_params,
    derive_wiper_params,
    vlm_describe,
    vlm_extract_shape,
)
from products.lip_gloss.components.registry import get_component
import products.lip_gloss.derived_params  # noqa: 确保派生规则注册

ART_ROOT = PROJECT_ROOT / "artifacts" / "test_pipeline"
PICTURE_ROOT = PROJECT_ROOT / "tests" / "picture"

# ════════════════════════════════════════════════════════════════════════
# 分类目录 & 默认用户尺寸
# ════════════════════════════════════════════════════════════════════════

CATEGORIES = [
    # (目录名, 描述, 默认用户尺寸)
    ("A1_round_flat",      "圆形直筒+平顶盖",   {"height_mm": 70, "body_od_mm": 24, "neck_od_mm": 18}),
    ("A2_round_dome",      "圆形直筒+圆顶盖",   {"height_mm": 70, "body_od_mm": 22, "neck_od_mm": 18}),
    ("A3_round_pointed",   "圆形直筒+尖顶盖",   {"height_mm": 65, "body_od_mm": 22, "neck_od_mm": 17}),
    ("B1_tapered",         "圆形锥形瓶身",       {"height_mm": 75, "body_od_mm": 24, "neck_od_mm": 18}),
    ("B2_barrel",          "桶形/鼓形瓶身",      {"height_mm": 55, "body_od_mm": 26, "neck_od_mm": 18}),
    ("B3_teardrop",        "水滴形瓶身",         {"height_mm": 65, "body_od_mm": 24, "neck_od_mm": 17}),
    ("B4_scurve",          "S形曲线瓶身",        {"height_mm": 70, "body_od_mm": 24, "neck_od_mm": 18}),
    ("C1_square_straight", "方形直筒",           {"height_mm": 70, "body_od_mm": 22, "neck_od_mm": 17}),
    ("C2_square_taper",    "方形锥度",           {"height_mm": 65, "body_od_mm": 22, "neck_od_mm": 17}),
    ("C3_square_rounded",  "大圆角方形",         {"height_mm": 65, "body_od_mm": 22, "neck_od_mm": 17}),
    ("D1_textured_cap",    "纹理盖",             {"height_mm": 70, "body_od_mm": 24, "neck_od_mm": 18}),
    ("D2_mushroom_cap",    "蘑菇盖/大头盖",     {"height_mm": 65, "body_od_mm": 22, "neck_od_mm": 17}),
    ("D3_taper_cap",       "锥度盖",             {"height_mm": 70, "body_od_mm": 24, "neck_od_mm": 18}),
    ("D4_smooth_cap",      "光面特殊形状盖",     {"height_mm": 68, "body_od_mm": 23, "neck_od_mm": 18}),
]


def list_images(cat_dir: str) -> list[Path]:
    """列出分类目录中所有图片"""
    d = PICTURE_ROOT / cat_dir
    if not d.is_dir():
        return []
    return sorted(f for f in d.iterdir()
                  if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))


def pick_image(cat_dir: str) -> Path | None:
    """取分类目录中的第一张图片"""
    imgs = list_images(cat_dir)
    return imgs[0] if imgs else None


def pick_sample_images(cat_dir: str) -> list[Path]:
    """抽检模式：>=10张取2张(首尾)，<10张取1张(首)"""
    imgs = list_images(cat_dir)
    if not imgs:
        return []
    if len(imgs) >= 10:
        # 取第1张和中间偏后的一张，避免风格雷同
        mid = len(imgs) // 2
        return [imgs[0], imgs[mid]]
    return [imgs[0]]


def load_image_b64(path: Path) -> str:
    """读取图片文件并转为 base64，大图自动压缩"""
    raw = path.read_bytes()
    # 对大图做压缩（> 500KB）
    if len(raw) > 500_000:
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(raw))
            w, h = img.size
            if max(w, h) > 800:
                ratio = 800 / max(w, h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
            raw = buf.getvalue()
        except ImportError:
            pass
    # webp → jpeg 转换（GLM 可能不支持 webp）
    if path.suffix.lower() == ".webp":
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(raw))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=85)
            raw = buf.getvalue()
        except ImportError:
            pass  # 没 Pillow 就直接传 webp，GLM 可能也接受
    return base64.b64encode(raw).decode("ascii")


# ════════════════════════════════════════════════════════════════════════
# 组件生成
# ════════════════════════════════════════════════════════════════════════

COMPONENT_ORDER = ["bottle", "cap", "wand", "wiper"]


def generate_component(comp_id: str, params: dict, run_dir: Path) -> dict:
    """调用组件 generate，返回结果 dict"""
    comp = get_component("lip_gloss", comp_id)
    outroot = str(run_dir)
    res = comp.generate(
        preset_id=None,
        user_params=params,
        outroot=outroot,
        title=f"pipeline_{comp_id}",
    )
    return res


def check_result(res: dict) -> tuple[bool, str]:
    """检查生成结果: (ok, reason)"""
    if not res:
        return False, "结果为空"
    if res.get("ok") is False:
        err = res.get("error", "未知错误")
        return False, f"生成失败: {err}"
    qc = res.get("qc", {})
    if isinstance(qc, dict) and qc.get("ok") is False:
        checks = qc.get("checks", [])
        hard_fails = [c["msg"] for c in checks
                      if isinstance(c, dict) and c.get("severity") == "hard" and not c.get("ok")]
        if hard_fails:
            return False, f"QC硬约束失败: {'; '.join(hard_fails)}"
        soft_fails = [c["msg"] for c in checks
                      if isinstance(c, dict) and not c.get("ok")]
        return False, f"QC失败: {'; '.join(soft_fails[:3])}"
    if not res.get("step") and not res.get("stl"):
        return False, "无STEP/STL输出文件"
    return True, "OK"


# ════════════════════════════════════════════════════════════════════════
# VLM 识别质量分析
# ════════════════════════════════════════════════════════════════════════

# 每个分类的预期特征
EXPECTED_FEATURES = {
    "A1_round_flat":      {"cross_section": "round", "shape": "cyl", "cap_top": "flat",    "profile_mode": "classic"},
    "A2_round_dome":      {"cross_section": "round", "shape": "cyl", "cap_top": "dome",    "profile_mode": "classic"},
    "A3_round_pointed":   {"cross_section": "round", "shape": "cyl", "cap_top": "pointed", "profile_mode": "classic"},
    "B1_tapered":         {"cross_section": "round", "shape": "taper", "profile_mode": "classic"},
    "B2_barrel":          {"cross_section": "round", "profile_mode": "spline"},
    "B3_teardrop":        {"cross_section": "round", "profile_mode": "spline"},
    "B4_scurve":          {"cross_section": "round", "profile_mode": "spline"},
    "C1_square_straight": {"cross_section": "square", "shape": "cyl", "profile_mode": "classic"},
    "C2_square_taper":    {"cross_section": "square", "shape": "taper"},
    "C3_square_rounded":  {"cross_section": "square"},
    "D1_textured_cap":    {"cross_section": "round", "cap_grip": ["knurl", "ribs", "stripe", "horizontal_grooves"]},
    "D2_mushroom_cap":    {"cross_section": "round", "cap_od_ratio_gt": 1.05},
    "D3_taper_cap":       {"cross_section": "round", "cap_taper_gt": 1.0},
    "D4_smooth_cap":      {"cross_section": "round"},
}


def analyze_vlm_quality(cat_dir: str, vlm_shape: dict) -> dict:
    """将 VLM 实际输出与分类预期特征对比，输出偏差"""
    expected = EXPECTED_FEATURES.get(cat_dir, {})
    issues = []
    matches = []

    # 截面形状
    if "cross_section" in expected:
        actual = vlm_shape.get("cross_section", "round")
        if actual != expected["cross_section"]:
            issues.append(f"截面形状: 预期={expected['cross_section']}, 实际={actual}")
        else:
            matches.append("截面形状正确")

    # 瓶身形状
    if "shape" in expected:
        actual = vlm_shape.get("shape", "cyl")
        if actual != expected["shape"]:
            issues.append(f"瓶身形状: 预期={expected['shape']}, 实际={actual}")
        else:
            matches.append("瓶身形状正确")

    # 轮廓模式
    if "profile_mode" in expected:
        actual = vlm_shape.get("profile_mode", "classic")
        if actual != expected["profile_mode"]:
            issues.append(f"轮廓模式: 预期={expected['profile_mode']}, 实际={actual}")
        else:
            matches.append("轮廓模式正确")

    # 盖顶形态
    if "cap_top" in expected:
        actual = vlm_shape.get("cap_top_shape", "flat")
        if actual != expected["cap_top"]:
            issues.append(f"盖顶形态: 预期={expected['cap_top']}, 实际={actual}")
        else:
            matches.append("盖顶形态正确")

    # 纹理
    if "cap_grip" in expected:
        actual = vlm_shape.get("cap_grip_style", "smooth")
        if actual not in expected["cap_grip"] and actual != "none":
            issues.append(f"盖纹理: 预期={expected['cap_grip']}, 实际={actual}")
        elif actual == "none" or actual == "smooth":
            issues.append(f"盖纹理: 预期有纹理, 实际={actual}")
        else:
            matches.append("盖纹理正确")

    # 蘑菇盖
    if "cap_od_ratio_gt" in expected:
        actual = vlm_shape.get("cap_od_ratio", 1.0)
        if actual <= expected["cap_od_ratio_gt"]:
            issues.append(f"蘑菇盖比例: 预期>{expected['cap_od_ratio_gt']}, 实际={actual}")
        else:
            matches.append("蘑菇盖比例正确")

    # 锥度盖
    if "cap_taper_gt" in expected:
        actual = vlm_shape.get("cap_taper_deg", 0)
        if actual < expected["cap_taper_gt"]:
            issues.append(f"盖锥度: 预期>{expected['cap_taper_gt']}°, 实际={actual}°")
        else:
            matches.append("盖锥度正确")

    return {"issues": issues, "matches": matches,
            "score": len(matches) / max(1, len(matches) + len(issues))}


# ════════════════════════════════════════════════════════════════════════
# 单分类测试
# ════════════════════════════════════════════════════════════════════════

def run_category_test(cat_dir: str, cat_desc: str, user_dims: dict,
                      skip_vlm: bool = False,
                      img_path: Path | None = None) -> dict:
    """对一个分类执行完整测试，返回结果 dict"""
    result = {
        "category": cat_dir,
        "description": cat_desc,
        "image": None,
        "vlm_ok": False,
        "vlm_time_s": 0,
        "vlm_description": "",
        "vlm_shape": {},
        "vlm_analysis": {},  # VLM 识别质量分析
        "components": {},
        "all_ok": False,
        "errors": [],
    }

    # 选图
    if img_path is None:
        img_path = pick_image(cat_dir)
    if img_path is None:
        result["errors"].append(f"目录 {cat_dir} 中无图片")
        return result
    result["image"] = str(img_path.name)
    print(f"\n  图片: {img_path.name} ({img_path.stat().st_size // 1024}KB)")

    # 加载 base64
    try:
        b64 = load_image_b64(img_path)
    except Exception as e:
        result["errors"].append(f"图片加载失败: {e}")
        return result
    print(f"  Base64: {len(b64) // 1024}KB")

    # VLM 提取
    if skip_vlm:
        # 跳过 VLM，注入分类特征参数以覆盖所有建模路径
        print("  [跳过VLM] 使用默认参数")
        vlm_shape = {
            "cross_section": "square" if "square" in cat_dir else "round",
            "corner_radius_mm": 3.0,
            "shape": "cyl",
            "taper_deg": 0.0,
            "profile_mode": "classic",
            "profile_points": [],
            "shoulder_style": "round",
            "shoulder_fillet_mm": 3.0,
            "bottom_style": "flat",
            "cap_height_ratio": 0.4,
            "cap_od_ratio": 1.0,
            "cap_taper_deg": 0.0,
            "cap_top_shape": "flat",
            "cap_grip_style": "smooth",
            "confidence": 1.0,
        }
        # 按分类注入特征覆盖，确保新建模路径被测试
        _cat_overrides = {
            "A2_round_dome":      {"cap_top_shape": "dome"},
            "A3_round_pointed":   {"cap_top_shape": "pointed"},
            "B1_tapered":         {"shape": "taper", "taper_deg": 3.0, "shoulder_style": "angular"},
            "B2_barrel":          {"profile_mode": "spline", "shoulder_style": "sloped"},
            "B3_teardrop":        {"profile_mode": "spline", "bottom_style": "convex", "bottom_concave_mm": 1.5},
            "B4_scurve":          {"profile_mode": "spline"},
            "C2_square_taper":    {"taper_deg": 2.0, "shoulder_style": "sloped"},
            "D1_textured_cap":    {"cap_grip_style": "ribs", "cap_grip_count": 24, "cap_grip_depth_mm": 0.3},
            "D2_mushroom_cap":    {"cap_od_ratio": 1.15},
            "D3_taper_cap":       {"cap_taper_deg": 4.0},
        }
        if cat_dir in _cat_overrides:
            vlm_shape.update(_cat_overrides[cat_dir])
        description = "(跳过VLM)"
        result["vlm_ok"] = True
    else:
        print("  [Step1] VLM 描述...")
        t0 = time.time()
        try:
            description = vlm_describe(b64)
            print(f"    描述: {description[:120]}...")
        except Exception as e:
            result["errors"].append(f"VLM描述失败: {e}")
            return result

        print("  [Step2] VLM 提取形状...")
        try:
            vlm_shape = vlm_extract_shape(description, user_dims)
            print(f"    形状: {vlm_shape.get('shape_description', '')[:80]}")
        except Exception as e:
            result["errors"].append(f"VLM形状提取失败: {e}")
            return result

        t_vlm = time.time() - t0
        result["vlm_time_s"] = round(t_vlm, 1)
        result["vlm_ok"] = True
        print(f"    VLM耗时: {t_vlm:.1f}s")

    result["vlm_description"] = description[:200]
    result["vlm_shape"] = vlm_shape

    # VLM 识别质量分析（与分类预期对比）
    if not skip_vlm:
        analysis = analyze_vlm_quality(cat_dir, vlm_shape)
        result["vlm_analysis"] = analysis
        if analysis.get("issues"):
            for issue in analysis["issues"]:
                print(f"    ⚠ VLM偏差: {issue}")

    # 参数合成
    print("  [Step3] 参数合成...")
    try:
        bottle_p = build_bottle_params(user_dims, vlm_shape)
        cap_p = derive_cap_params(bottle_p, vlm_shape)
        wand_p = derive_wand_params(cap_p, bottle_p)
        wiper_p = derive_wiper_params(bottle_p, wand_p)
    except Exception as e:
        result["errors"].append(f"参数合成失败: {e}")
        traceback.print_exc()
        return result

    all_params = {"bottle": bottle_p, "cap": cap_p, "wand": wand_p, "wiper": wiper_p}

    # 打印关键参数
    print(f"    bottle: h={bottle_p['height_mm']}, od={bottle_p['body_od_mm']}, "
          f"shape={bottle_p['shape']}, cross={bottle_p.get('cross_section','round')}, "
          f"profile={bottle_p['profile_mode']}")
    print(f"    cap: od={cap_p['outer_od_mm']}, h={cap_p['height_mm']}, "
          f"top={cap_p.get('top_shape','flat')}, grip={cap_p.get('grip.style','none')}")
    print(f"    wand: od={wand_p['outer_od_mm']:.1f}, total_h={wand_p['total_height_mm']:.1f}, "
          f"rod={wand_p['stem_diameter_mm']:.1f}")
    print(f"    wiper: od={wiper_p['outer_od_mm']}, h={wiper_p['height_mm']:.1f}, "
          f"orifice={wiper_p['orifice_mm']:.1f}")

    # 逐组件生成
    run_dir = ART_ROOT / cat_dir
    run_dir.mkdir(parents=True, exist_ok=True)

    comp_results = {}
    all_ok = True
    for comp_id in COMPONENT_ORDER:
        print(f"  [Gen] {comp_id}...", end=" ", flush=True)
        t0 = time.time()
        try:
            res = generate_component(comp_id, all_params[comp_id], run_dir)
            dt = time.time() - t0
            ok, reason = check_result(res)
            comp_results[comp_id] = {
                "ok": ok,
                "reason": reason,
                "time_s": round(dt, 2),
                "step": res.get("step"),
                "stl": res.get("stl"),
            }
            if ok:
                print(f"OK ({dt:.1f}s)")
            else:
                print(f"FAIL ({dt:.1f}s) — {reason[:100]}")
                all_ok = False
                result["errors"].append(f"{comp_id}: {reason}")
        except Exception as e:
            dt = time.time() - t0
            tb = traceback.format_exc()
            comp_results[comp_id] = {
                "ok": False,
                "reason": f"异常: {e}",
                "time_s": round(dt, 2),
            }
            print(f"ERROR ({dt:.1f}s) — {e}")
            all_ok = False
            result["errors"].append(f"{comp_id}: 异常 {e}")
            # 打印异常详情
            print(f"    {tb[-300:]}")

    result["components"] = comp_results
    result["all_ok"] = all_ok
    return result


# ════════════════════════════════════════════════════════════════════════
# 报告
# ════════════════════════════════════════════════════════════════════════

def print_report(results: list[dict]):
    """打印测试汇总报告"""
    print("\n")
    print("=" * 80)
    print("         图片输入管线 端到端测试报告")
    print("=" * 80)

    # 汇总表
    print(f"\n{'分类':<22} {'图片':<30} {'VLM':>4} {'bottle':>7} {'cap':>5} {'wand':>6} {'wiper':>6} {'结果':>6}")
    print("-" * 86)

    total = len(results)
    all_pass = 0
    comp_pass = {"bottle": 0, "cap": 0, "wand": 0, "wiper": 0}
    vlm_pass = 0

    for r in results:
        cat = r["category"]
        img = (r.get("image") or "N/A")[:28]
        vlm = "OK" if r["vlm_ok"] else "FAIL"
        if r["vlm_ok"]:
            vlm_pass += 1

        comps = r.get("components", {})
        comp_strs = {}
        for c in COMPONENT_ORDER:
            cr = comps.get(c, {})
            if cr.get("ok"):
                comp_strs[c] = "OK"
                comp_pass[c] += 1
            elif c in comps:
                comp_strs[c] = "FAIL"
            else:
                comp_strs[c] = "-"

        overall = "PASS" if r["all_ok"] else "FAIL"
        if r["all_ok"]:
            all_pass += 1

        print(f"{cat:<22} {img:<30} {vlm:>4} {comp_strs.get('bottle','-'):>7} "
              f"{comp_strs.get('cap','-'):>5} {comp_strs.get('wand','-'):>6} "
              f"{comp_strs.get('wiper','-'):>6} {overall:>6}")

    print("-" * 86)
    print(f"{'通过率':<22} {'':30} {vlm_pass:>3}/{total} "
          f"{comp_pass['bottle']:>6}/{total} "
          f"{comp_pass['cap']:>4}/{total} "
          f"{comp_pass['wand']:>5}/{total} "
          f"{comp_pass['wiper']:>5}/{total} "
          f"{all_pass:>5}/{total}")

    # 失败分析
    failures = [r for r in results if not r["all_ok"]]
    if failures:
        print(f"\n{'='*80}")
        print("失败原因分析")
        print("=" * 80)
        for r in failures:
            print(f"\n[{r['category']}] {r['description']}")
            print(f"  图片: {r.get('image', 'N/A')}")
            if r.get("vlm_description"):
                print(f"  VLM描述: {r['vlm_description'][:120]}")
            vlm_shape = r.get("vlm_shape", {})
            if vlm_shape:
                print(f"  VLM形状: shape={vlm_shape.get('shape')}, "
                      f"cross={vlm_shape.get('cross_section')}, "
                      f"profile={vlm_shape.get('profile_mode')}, "
                      f"taper={vlm_shape.get('taper_deg')}")
            for err in r.get("errors", []):
                print(f"  ERROR: {err}")

    # 总结
    print(f"\n{'='*80}")
    print("总结")
    print(f"  测试分类: {total}")
    print(f"  全部通过: {all_pass}/{total} ({all_pass/total*100:.0f}%)")
    print(f"  VLM提取:  {vlm_pass}/{total}")
    for c in COMPONENT_ORDER:
        print(f"  {c:>8}: {comp_pass[c]}/{total}")
    if all_pass == total:
        print("  结论: 所有分类图片均可成功走完管线，生成全部4组件。")
    else:
        print(f"  结论: {total - all_pass} 个分类失败，需修复。")
    print("=" * 80)


# ════════════════════════════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════════════════════════════

def print_vlm_analysis_report(results: list[dict]):
    """打印 VLM 识别质量分析报告"""
    vlm_results = [r for r in results if r.get("vlm_analysis")]
    if not vlm_results:
        return

    print(f"\n{'='*80}")
    print("         VLM 识别质量分析")
    print("=" * 80)

    all_issues = []
    scores = []
    for r in vlm_results:
        a = r["vlm_analysis"]
        scores.append(a.get("score", 0))
        cat = r["category"]
        img = r.get("image", "?")
        if a.get("issues"):
            print(f"\n  [{cat}] {img}")
            for issue in a["issues"]:
                print(f"    - {issue}")
                all_issues.append((cat, issue))
        if a.get("matches"):
            for m in a["matches"]:
                pass  # 正确的不打印，减少噪音

    avg_score = sum(scores) / len(scores) if scores else 0
    print(f"\n  VLM 识别准确率: {avg_score:.0%} (按特征维度)")
    print(f"  有偏差的测试: {len([s for s in scores if s < 1.0])}/{len(scores)}")

    # 按偏差类型汇总
    if all_issues:
        issue_types = {}
        for cat, issue in all_issues:
            key = issue.split(":")[0]
            issue_types.setdefault(key, []).append(cat)
        print(f"\n  偏差类型汇总:")
        for itype, cats in sorted(issue_types.items(), key=lambda x: -len(x[1])):
            print(f"    {itype}: {len(cats)}次 ({', '.join(cats)})")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="图片输入管线 端到端测试")
    parser.add_argument("--category", "-c", default=None,
                        help="只测试指定分类 (如 A1_round_flat)，可逗号分隔多个")
    parser.add_argument("--skip-vlm", action="store_true",
                        help="跳过VLM调用，使用默认参数直接测试生成")
    parser.add_argument("--sample", action="store_true",
                        help="抽检模式：>=10张取2张，<10张取1张")
    parser.add_argument("--save", default="tests/pipeline_results.json",
                        help="结果JSON保存路径")
    args = parser.parse_args()

    # 选择要测试的分类
    if args.category:
        selected = [c.strip() for c in args.category.split(",")]
        cats = [(d, desc, dims) for d, desc, dims in CATEGORIES if d in selected]
        if not cats:
            print(f"未找到分类: {args.category}")
            print(f"可用: {', '.join(d for d, _, _ in CATEGORIES)}")
            return
    else:
        cats = CATEGORIES

    # 构建测试任务列表
    tasks = []  # [(cat_dir, cat_desc, user_dims, img_path), ...]
    for cat_dir, cat_desc, user_dims in cats:
        if args.sample:
            imgs = pick_sample_images(cat_dir)
            for img in imgs:
                tasks.append((cat_dir, cat_desc, user_dims, img))
        else:
            tasks.append((cat_dir, cat_desc, user_dims, None))  # None = pick first

    print("=" * 80)
    print("图片输入管线 端到端测试")
    print(f"测试分类: {len(cats)}, 测试图片: {len(tasks)}")
    print(f"模式: {'抽检' if args.sample else '首图'} | "
          f"VLM: {'跳过' if args.skip_vlm else '启用 (glm-4.6v)'}")
    print(f"GLM_API_KEY: {'已设置' if os.environ.get('GLM_API_KEY') else '未设置'}")
    print("=" * 80)

    if not args.skip_vlm and not os.environ.get("GLM_API_KEY"):
        print("\nERROR: 需要设置 GLM_API_KEY 环境变量（或使用 --skip-vlm）")
        return

    results = []
    for i, (cat_dir, cat_desc, user_dims, img_path) in enumerate(tasks):
        suffix = f" [{img_path.name}]" if img_path else ""
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(tasks)}] [{cat_dir}] {cat_desc}{suffix}")
        print(f"{'='*60}")

        r = run_category_test(cat_dir, cat_desc, user_dims,
                              skip_vlm=args.skip_vlm, img_path=img_path)
        results.append(r)

        # API 限流间隔
        if not args.skip_vlm:
            time.sleep(2)

    print_report(results)
    print_vlm_analysis_report(results)

    # 保存详细结果（去掉不可序列化的内容）
    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        if isinstance(obj, (int, float, str, bool, type(None))):
            return obj
        return str(obj)

    out_path = Path(args.save)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(_clean(results), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n详细结果已保存: {out_path}")


if __name__ == "__main__":
    main()
