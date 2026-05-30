# -*- coding: utf-8 -*-
"""测试 _measure_bottle_profile：合成 bottle 宽度剖面 + 缓存 mask 验证。"""
import sys
import os
os.environ["PYTHONIOENCODING"] = "utf-8"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from auto_pipeline import _measure_bottle_profile

# ═══════════════════════════════════════════════════════════
# Test 1: 合成 bottle 宽度剖面（已知参数）
# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("Test 1: 合成 bottle 宽度剖面")
print("=" * 60)

# 模拟：总高 500px, neck at top
# neck: 0-70px, width=340 (= 17mm * 20px/mm)
# shoulder: 70-130px, width 340→480 (线性)
# body: 130-500px, width ~480 (= 24mm * 20px/mm, slight taper)
total_px = 500
wp = np.zeros(600)  # 含 50px padding
y_top, y_bot = 50, 550

# neck zone (y_top to y_top+70): ~340px wide
for y in range(y_top, y_top + 70):
    wp[y] = 340 + np.random.normal(0, 2)

# shoulder transition (y_top+70 to y_top+130): 340→480 linear
for i, y in enumerate(range(y_top + 70, y_top + 130)):
    frac = i / 60.0
    wp[y] = 340 + (480 - 340) * frac + np.random.normal(0, 2)

# body zone (y_top+130 to y_bot): ~480px, slight taper
for i, y in enumerate(range(y_top + 130, y_bot)):
    taper_w = 480 + i * 0.05  # very slight widening
    wp[y] = taper_w + np.random.normal(0, 2)

ref_meas = {
    "_width_profile": wp,
    "_y_top": y_top,
    "_y_bot": y_bot,
}

result = _measure_bottle_profile(ref_meas)
if result:
    print(f"  neck_od_px: {result['neck_od_px']:.1f} (expected ~340)")
    print(f"  body_od_px: {result['body_od_px']:.1f} (expected ~480+)")
    print(f"  neck_body_ratio: {result['neck_body_ratio']:.3f} (expected ~0.71)")
    print(f"  neck_height_px: {result['neck_height_px']} (expected ~70)")
    print(f"  shoulder_height_px: {result['shoulder_height_px']} (expected ~60)")
    print(f"  orientation: {result['orientation']}")

    # 验证 mm 换算
    px_per_mm = 20.0
    neck_od_mm = result["neck_od_px"] / px_per_mm
    print(f"\n  neck_od_mm: {neck_od_mm:.1f} (expected ~17.0)")
    print(f"  body_od_mm: {result['body_od_px'] / px_per_mm:.1f} (expected ~24.0)")

    # 精度检查
    ok = True
    if abs(neck_od_mm - 17.0) > 2.0:
        print(f"  FAIL: neck_od_mm deviation > 2mm")
        ok = False
    if result["neck_body_ratio"] < 0.6 or result["neck_body_ratio"] > 0.8:
        print(f"  FAIL: neck_body_ratio out of [0.6, 0.8]")
        ok = False
    print(f"\n  {'PASS' if ok else 'FAIL'}")
else:
    print("  FAIL: _measure_bottle_profile returned None")

# ═══════════════════════════════════════════════════════════
# Test 2: 合成 bottle (neck at bottom, 反向)
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 2: 合成 bottle (neck at bottom)")
print("=" * 60)

wp2 = np.zeros(600)
y_top2, y_bot2 = 50, 550

# body zone (top): ~480px
for i, y in enumerate(range(y_top2, y_top2 + 370)):
    wp2[y] = 500 - i * 0.05 + np.random.normal(0, 2)

# shoulder transition: 480→340
for i, y in enumerate(range(y_top2 + 370, y_top2 + 430)):
    frac = i / 60.0
    wp2[y] = 480 - (480 - 340) * frac + np.random.normal(0, 2)

# neck zone (bottom): ~340px
for y in range(y_top2 + 430, y_bot2):
    wp2[y] = 340 + np.random.normal(0, 2)

ref_meas2 = {
    "_width_profile": wp2,
    "_y_top": y_top2,
    "_y_bot": y_bot2,
}

result2 = _measure_bottle_profile(ref_meas2)
if result2:
    print(f"  orientation: {result2['orientation']} (expected neck_at_bottom)")
    print(f"  neck_od_px: {result2['neck_od_px']:.1f} (expected ~340)")
    print(f"  neck_body_ratio: {result2['neck_body_ratio']:.3f} (expected ~0.68)")
    print(f"  {'PASS' if result2['orientation'] == 'neck_at_bottom' else 'FAIL'}")
else:
    print("  FAIL: returned None")

# ═══════════════════════════════════════════════════════════
# Test 3: 非 bottle 轮廓（纯锥形，无颈部）
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 3: 非 bottle 轮廓（纯锥形）")
print("=" * 60)

wp3 = np.zeros(600)
for i, y in enumerate(range(50, 550)):
    wp3[y] = 100 + i * 0.8  # 线性增宽，无明显颈部

ref_meas3 = {
    "_width_profile": wp3,
    "_y_top": 50,
    "_y_bot": 550,
}

result3 = _measure_bottle_profile(ref_meas3)
print(f"  Result: {result3}")
print(f"  {'PASS' if result3 is None else 'FAIL'} (expected None for non-bottle)")
