# -*- coding: utf-8 -*-
"""测试 CV 参数提取模块 — 对 A3 参考图运行并与 Gallery 配置对比"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.cv_extract import cv_extract_shape, cv_extract_debug

# ---- A3 参考图 ----
IMAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "tests", "picture", "A3_round_pointed")
IMAGES = [
    "cairui_cone_01.webp",
    "canda_mini_01.webp",
    "canda_mini_02.webp",
    "canda_silver_01.webp",
    "canda_silver_02.webp",
    "canda_silver_03.webp",
]
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "tests", "cv_output")

# ---- 当前 Gallery A3 硬编码 vlm_shape ----
GALLERY_VLM = {
    "shape": "taper",
    "taper_deg": 3.0,
    "shoulder_style": "angular",
    "cap_od_base": "body_top",
    "cap_od_ratio": 1.0,
    "cap_height_mm": 35,
    "cap_taper_deg": 0.5,
    "cap_top_shape": "flat",
}

# ---- A3 用户尺寸 ----
USER_DIMS = {"height_mm": 65, "body_od_mm": 24, "neck_od_mm": 17}


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_results = {}

    print("=" * 60)
    print("CV 参数提取测试 — A3_round_pointed 参考图")
    print("=" * 60)

    for img_name in IMAGES:
        img_path = os.path.join(IMAGE_DIR, img_name)
        if not os.path.exists(img_path):
            print(f"\n[跳过] {img_name} — 文件不存在")
            continue

        print(f"\n--- {img_name} ---")
        try:
            result = cv_extract_debug(img_path, user_dims=USER_DIMS, output_dir=OUTPUT_DIR)
            all_results[img_name] = result
            for key in ["shape", "taper_deg", "cap_height_ratio", "cap_height_mm",
                         "cap_od_ratio", "cap_od_base", "cap_taper_deg",
                         "cap_top_shape", "shoulder_style", "confidence"]:
                val = result.get(key, "N/A")
                if isinstance(val, float):
                    print(f"  {key:>20s}: {val:.2f}")
                else:
                    print(f"  {key:>20s}: {val}")
        except Exception as e:
            print(f"  [错误] {e}")
            import traceback
            traceback.print_exc()

    # ---- 与 Gallery 配置对比 ----
    if all_results:
        print("\n" + "=" * 60)
        print("CV 提取 vs Gallery 硬编码参数对比")
        print("=" * 60)

        # 使用第一张图（cairui_cone_01）作为主要对比
        primary = all_results.get("cairui_cone_01.webp")
        if primary is None:
            primary = list(all_results.values())[0]

        print(f"\n{'参数':>20s}  {'CV提取':>12s}  {'Gallery':>12s}  匹配")
        print("-" * 65)
        for key, gal_val in GALLERY_VLM.items():
            cv_val = primary.get(key, "N/A")
            if isinstance(cv_val, float) and isinstance(gal_val, (int, float)):
                match = "~" if abs(cv_val - gal_val) / max(abs(gal_val), 0.1) < 0.3 else "X"
                print(f"  {key:>20s}  {cv_val:>12.2f}  {gal_val:>12}  {match}")
            elif isinstance(cv_val, str) and isinstance(gal_val, str):
                match = "OK" if cv_val == gal_val else "X"
                print(f"  {key:>20s}  {cv_val:>12s}  {gal_val:>12s}  {match}")
            else:
                print(f"  {key:>20s}  {str(cv_val):>12s}  {str(gal_val):>12s}  ?")

    print(f"\n调试图片已保存到: {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
