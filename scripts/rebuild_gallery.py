# -*- coding: utf-8 -*-
"""Gallery VLM 缓存重建脚本 — 对每张参考图运行自动管线，缓存 VLM+CV 结果。

两阶段解耦设计：
  1. rebuild_gallery.py（本脚本）：VLM 分析 + CV 定量 → 写缓存
  2. prebuild_gallery.py：读缓存 → 构建 STL/STEP

VLM 缓存策略：
  - 首次运行：调 GLM-4v API → 存 artifacts/vlm_cache/{cat_id}.json
  - 后续运行：读缓存（skip_vlm=True），仅重跑 CV 定量
  - --force-vlm：强制刷新 VLM（重新调 API）

用法:
    python scripts/rebuild_gallery.py                  # 重建所有（用已有缓存）
    python scripts/rebuild_gallery.py A1_round_flat    # 重建单个
    python scripts/rebuild_gallery.py --force-vlm      # 强制刷新 VLM
    python scripts/rebuild_gallery.py --dry-run        # 只打印结果，不写缓存
"""
from __future__ import annotations

import io
import sys

# Windows GBK 终端兼容
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from web_server import GALLERY_CATALOG

VLM_CACHE_DIR = PROJECT_ROOT / "artifacts" / "vlm_cache"


# ═══════════════════════════════════════════════════════════════════
# VLM 缓存读写
# ═══════════════════════════════════════════════════════════════════

def _load_cache(cat_id: str) -> dict | None:
    cache_file = VLM_CACHE_DIR / f"{cat_id}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _save_cache(cat_id: str, data: dict) -> None:
    VLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = VLM_CACHE_DIR / f"{cat_id}.json"
    cache_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# ═══════════════════════════════════════════════════════════════════
# 自动描述生成
# ═══════════════════════════════════════════════════════════════════

def auto_desc(vlm_shape: dict) -> str:
    """从 vlm_shape 自动生成中文描述。"""
    parts = []

    # 截面
    cs = vlm_shape.get("cross_section", "round")
    cs_map = {
        "round": "圆形", "square": "方形",
        "hexagon": "六边形", "octagon": "八边形",
    }
    cs_name = cs_map.get(cs, cs)

    # 瓶身形状
    shape = vlm_shape.get("shape", "cyl")
    profile = vlm_shape.get("profile_mode", "classic")
    if shape == "taper":
        parts.append(f"{cs_name}锥形瓶身")
    elif profile == "spline":
        parts.append(f"{cs_name}曲线瓶身")
    else:
        parts.append(f"{cs_name}直筒")

    # 装饰特征
    collar = vlm_shape.get("bottle_collar_style", "none")
    if collar != "none":
        collar_map = {
            "ribs": "竖纹装饰带", "grooves": "横纹装饰带",
            "smooth_band": "光面环带",
        }
        parts.append(collar_map.get(collar, "装饰带"))

    if vlm_shape.get("bottle_base_ring"):
        parts.append("底座台阶")

    # 盖描述
    cap_top = vlm_shape.get("cap_top_shape", "flat")
    grip = vlm_shape.get("cap_grip_style", "smooth")
    top_map = {"flat": "平顶", "dome": "圆顶", "pointed": "尖顶"}
    grip_map = {
        "smooth": "光面", "none": "光面", "stripe": "条纹",
        "ribs": "竖纹", "knurl": "滚花",
    }
    cap_top_desc = top_map.get(cap_top, cap_top)
    grip_desc = grip_map.get(grip, grip)
    parts.append(f"{cap_top_desc}{grip_desc}盖")

    return "+".join(parts)


# ═══════════════════════════════════════════════════════════════════
# 差异报告
# ═══════════════════════════════════════════════════════════════════

def _diff_report(label: str, old: dict, new: dict, max_show: int = 10) -> int:
    all_keys = sorted(set(list(old.keys()) + list(new.keys())))
    diffs = []
    for k in all_keys:
        ov = old.get(k)
        nv = new.get(k)
        if ov != nv and k != "confidence":
            diffs.append(f"    {k}: {ov!r} → {nv!r}")
    if diffs:
        print(f"  [{label}] {len(diffs)} 项差异:")
        for d in diffs[:max_show]:
            print(d)
        if len(diffs) > max_show:
            print(f"    ... 及 {len(diffs) - max_show} 项更多")
    return len(diffs)


# ═══════════════════════════════════════════════════════════════════
# 单条目重建
# ═══════════════════════════════════════════════════════════════════

def rebuild_one(
    cat_id: str,
    spec: dict,
    force_vlm: bool = False,
    dry_run: bool = False,
) -> dict | None:
    """对单个 gallery 条目运行自动管线，返回缓存数据。"""
    from auto_pipeline import run_pipeline, merge_cv_vlm

    ref_image = spec.get("ref_image", "")
    total_h = spec.get("total_height_mm", 100)

    if not ref_image:
        print(f"  [跳过] 无 ref_image")
        return None

    ref_path = PROJECT_ROOT / ref_image
    if not ref_path.exists():
        print(f"  [跳过] 参考图不存在: {ref_path}")
        return None

    # 检查 VLM 缓存
    cached = None
    if not force_vlm:
        cached = _load_cache(cat_id)
        if cached:
            print(f"  [缓存] 已有 VLM 缓存 (built_at={cached.get('built_at', '?')})")

    skip_vlm = cached is not None

    # 运行 auto_pipeline（body_od/neck_od=0 → 由 CV 推算）
    print(f"  [管线] 运行 auto_pipeline (skip_vlm={skip_vlm})")
    try:
        result = run_pipeline(
            str(ref_path), total_h,
            body_od_mm=0, neck_od_mm=0,
            skip_vlm=skip_vlm,
        )
    except Exception as e:
        print(f"  [失败] auto_pipeline 异常: {e}")
        import traceback
        traceback.print_exc()
        return None

    # 如果用了缓存，用缓存的 vlm_raw 重新 merge（CV 定量仍然是最新的）
    if cached and cached.get("vlm_raw"):
        try:
            merged = merge_cv_vlm(
                result["cv_measurement"],
                cached["vlm_raw"],
                result["user_dims"],
                total_height_mm=result.get("total_height_mm", 0),
            )
            result["gallery_entry"]["vlm_shape"] = merged
            result["merged_vlm_shape"] = merged
        except Exception as e:
            print(f"  [警告] 缓存 merge 失败: {e}，使用管线默认值")

    # 提取结果
    entry = result["gallery_entry"]
    merged_shape = entry.get("vlm_shape", result.get("merged_vlm_shape", {}))
    user_dims = entry.get("user_dims", result.get("user_dims", {}))
    desc = auto_desc(merged_shape)

    # 构建缓存数据
    cache_data = {
        "cat_id": cat_id,
        "vlm_raw": result.get("vlm_raw", {}),
        "vlm_description": result.get("vlm_description", ""),
        "merged_vlm_shape": merged_shape,
        "user_dims": user_dims,
        "desc": desc,
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }

    # 打印摘要
    print(f"  [结果] desc: {desc}")
    print(f"  [结果] body_od={user_dims.get('body_od_mm', '?')}mm, "
          f"neck_od={user_dims.get('neck_od_mm', '?')}mm, "
          f"height={user_dims.get('height_mm', '?')}mm")
    print(f"  [结果] cross_section={merged_shape.get('cross_section', '?')}, "
          f"shape={merged_shape.get('shape', '?')}, "
          f"cap_top={merged_shape.get('cap_top_shape', '?')}, "
          f"grip={merged_shape.get('cap_grip_style', '?')}")

    # 与旧配置差异对比
    old_vlm = spec.get("vlm_shape", {})
    if old_vlm:
        _diff_report("vlm_shape", old_vlm, merged_shape)

    old_dims = spec.get("user_dims", {})
    if old_dims:
        _diff_report("user_dims", old_dims, user_dims)

    # 写缓存
    if not dry_run:
        _save_cache(cat_id, cache_data)
        print(f"  [缓存] 已写入 vlm_cache/{cat_id}.json")

    return cache_data


# ═══════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Gallery VLM 缓存重建")
    parser.add_argument("cat_ids", nargs="*", help="要重建的 cat_id（默认全部）")
    parser.add_argument("--force-vlm", action="store_true",
                        help="强制刷新 VLM（重新调 API，忽略缓存）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印结果，不写缓存文件")
    args = parser.parse_args()

    targets = args.cat_ids if args.cat_ids else list(GALLERY_CATALOG.keys())
    invalid = [c for c in targets if c not in GALLERY_CATALOG]
    if invalid:
        print(f"未知配置: {', '.join(invalid)}")
        print(f"可用配置: {', '.join(GALLERY_CATALOG.keys())}")
        sys.exit(1)

    total = len(targets)
    ok_count = 0
    fail_list = []

    mode = "强制 VLM" if args.force_vlm else "缓存优先"
    if args.dry_run:
        mode += " (dry-run)"

    print(f"{'=' * 60}")
    print(f"Gallery VLM 重建 — {total} 个配置 [{mode}]")
    print(f"缓存目录: {VLM_CACHE_DIR}")
    print(f"{'=' * 60}")

    t0 = time.time()
    for i, cat_id in enumerate(targets, 1):
        spec = GALLERY_CATALOG[cat_id]
        print(f"\n{'─' * 60}")
        print(f"[{i}/{total}] {cat_id} — {spec.get('desc', '?')}")

        t1 = time.time()
        cache_data = rebuild_one(cat_id, spec,
                                 force_vlm=args.force_vlm,
                                 dry_run=args.dry_run)
        elapsed = time.time() - t1

        if cache_data:
            print(f"  完成 ({elapsed:.1f}s)")
            ok_count += 1
        else:
            print(f"  失败 ({elapsed:.1f}s)")
            fail_list.append(cat_id)

    total_time = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"完成: {ok_count}/{total} 成功, 耗时 {total_time:.1f}s")
    if fail_list:
        print(f"失败: {', '.join(fail_list)}")
    if args.dry_run:
        print("(dry-run 模式，未写入任何文件)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
