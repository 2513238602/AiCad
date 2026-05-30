# -*- coding: utf-8 -*-
"""诊断 v2: 限制搜索范围 + 软 mask 分析。"""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import cv2
import numpy as np

from auto_pipeline import (
    _find_largest_contour, _classify_contour, _rotate_mask_upright,
    _measure_single_contour, _measure_bottle_profile, birefnet_mask,
)

IMG_PATH = os.path.join(os.path.dirname(__file__),
                        "picture", "A3_round_pointed", "cairui_cone_01.webp")
OUT_DIR = os.path.join(os.path.dirname(__file__), "diag_output")
os.makedirs(OUT_DIR, exist_ok=True)

color_img = cv2.imread(IMG_PATH)
mask = birefnet_mask(IMG_PATH)
if mask.shape[:2] != color_img.shape[:2]:
    mask = cv2.resize(mask, (color_img.shape[1], color_img.shape[0]),
                      interpolation=cv2.INTER_NEAREST)

contours = _find_largest_contour(mask)
bottle_c = None
for i, c in enumerate(contours[:5]):
    cls = _classify_contour(mask, color_img, c)
    if cls['type'] == 'standalone_bottle':
        bottle_c = c
        break

# 获取独立瓶身的旋转 mask
single = np.zeros_like(mask)
cv2.drawContours(single, [bottle_c], -1, 255, cv2.FILLED)
single_raw = cv2.bitwise_and(mask, single)  # 保留原始 0-255 值
rotated_raw, M, new_size, angle = _rotate_mask_upright(single_raw, bottle_c)

# 二值化对比
binary_128 = (rotated_raw > 128).astype(np.uint8) * 255
binary_64 = (rotated_raw > 64).astype(np.uint8) * 255
binary_32 = (rotated_raw > 32).astype(np.uint8) * 255
binary_16 = (rotated_raw > 16).astype(np.uint8) * 255

rows_any = np.any(binary_128 > 0, axis=1)
y_top = int(np.where(rows_any)[0][0])
y_bot = int(np.where(rows_any)[0][-1])
total_h = y_bot - y_top

ref_meas = _measure_single_contour(mask, color_img, bottle_c)
bp = _measure_bottle_profile(ref_meas)
print(f"Mask-based: neck_od={bp['neck_od_px']:.1f}px, body_od={bp['body_od_px']:.1f}px")

neck_end_offset = bp['neck_height_px']
neck_y_start = y_top
neck_y_end = y_top + neck_end_offset

print(f"\n=== 软 mask 阈值对比（颈部区域 y={neck_y_start}..{neck_y_end}）===")
for label, bimg in [("128", binary_128), ("64", binary_64),
                     ("32", binary_32), ("16", binary_16)]:
    wp = (bimg > 128).sum(axis=1).astype(np.float64)
    neck_ws = wp[neck_y_start:neck_y_end]
    body_ws = wp[y_top + total_h * 2 // 3 : y_bot]
    if len(neck_ws) > 0 and len(body_ws) > 0:
        neck_w = float(np.median(neck_ws))
        body_w = float(np.median(body_ws))
        print(f"  阈值>{label}: neck_w={neck_w:.1f}px ({neck_w/5.08:.1f}mm), "
              f"body_w={body_w:.1f}px ({body_w/5.08:.1f}mm), "
              f"ratio={neck_w/body_w:.3f}")

# 原始 mask 值直方图（颈部区域）
print(f"\n=== 颈部区域原始 mask 值分布 ===")
neck_region = rotated_raw[neck_y_start:neck_y_end, :]
# 找到 mask 中心附近的列
wp128 = (binary_128 > 128).sum(axis=1).astype(np.float64)
neck_center_cols = []
for y in range(neck_y_start, neck_y_end):
    cols = np.where(binary_128[y] > 128)[0]
    if len(cols) >= 2:
        neck_center_cols.append((int(cols[0]), int(cols[-1])))

if neck_center_cols:
    left_avg = int(np.mean([c[0] for c in neck_center_cols]))
    right_avg = int(np.mean([c[1] for c in neck_center_cols]))
    center = (left_avg + right_avg) // 2
    expand = 80  # 在 mask 边界外扩展 80px 搜索

    print(f"  Mask 颈部中心列: L={left_avg}, R={right_avg}, center={center}")
    print(f"  搜索范围: [{left_avg - expand}, {right_avg + expand}]")

    # 在 mask 附近区域的 raw 值分布
    search_left = max(0, left_avg - expand)
    search_right = min(rotated_raw.shape[1], right_avg + expand)

    print(f"\n  --- 各列的 raw mask 值（颈区中间行 y={neck_y_start + neck_end_offset // 2}）---")
    mid_y = neck_y_start + neck_end_offset // 2
    row_vals = rotated_raw[mid_y, search_left:search_right]
    # 找非零段
    nz = np.where(row_vals > 0)[0]
    if len(nz) > 0:
        nz_left = nz[0] + search_left
        nz_right = nz[-1] + search_left
        print(f"  非零范围: col={nz_left}..{nz_right} (宽度={nz_right - nz_left}px)")
        # 打印边界附近的值
        for offset_from_left in [-5, -3, -1, 0, 1, 3, 5, 10, 15]:
            col_l = left_avg + offset_from_left
            col_r = right_avg - offset_from_left
            if 0 <= col_l < rotated_raw.shape[1] and 0 <= col_r < rotated_raw.shape[1]:
                print(f"    L{offset_from_left:+d}(col={col_l}): val={rotated_raw[mid_y, col_l]}, "
                      f"R{-offset_from_left:+d}(col={col_r}): val={rotated_raw[mid_y, col_r]}")

    # ── 限制搜索范围的 Canny ──
    print(f"\n=== 限制范围的 Canny 边缘检测 ===")
    rotated_color = cv2.warpAffine(color_img, M, new_size, flags=cv2.INTER_LINEAR)
    gray = cv2.cvtColor(rotated_color, cv2.COLOR_BGR2GRAY)

    # 只在 mask 附近搜索
    for canny_lo, canny_hi in [(20, 60), (30, 80), (50, 150)]:
        edges = cv2.Canny(gray, canny_lo, canny_hi)
        widths = []
        for y in range(neck_y_start, neck_y_end):
            # 找 mask 的左右边界
            m_cols = np.where(binary_128[y] > 128)[0]
            if len(m_cols) < 2:
                continue
            ml, mr = int(m_cols[0]), int(m_cols[-1])
            # 在 mask 边界外 ±expand 范围搜索
            sl = max(0, ml - expand)
            sr = min(edges.shape[1], mr + expand)
            edge_cols = np.where(edges[y, sl:sr] > 0)[0] + sl
            if len(edge_cols) >= 2:
                widths.append(float(edge_cols[-1] - edge_cols[0]))
        if widths:
            print(f"  Canny({canny_lo},{canny_hi}): median_w={np.median(widths):.1f}px "
                  f"({np.median(widths)/5.08:.1f}mm), "
                  f"samples={len(widths)}, range=[{min(widths):.0f}, {max(widths):.0f}]")

    # ── 保存对比图 ──
    # 上下拼接：原始 mask vs 低阈值 mask
    compare = np.hstack([
        cv2.resize(binary_128[y_top - 10:y_bot + 10, search_left:search_right],
                   None, fx=2, fy=2),
        cv2.resize(binary_32[y_top - 10:y_bot + 10, search_left:search_right],
                   None, fx=2, fy=2),
    ])
    cv2.imwrite(os.path.join(OUT_DIR, "mask_128_vs_32.png"), compare)

    # 保存颈部区域的原始 mask 值热力图
    neck_raw_crop = rotated_raw[neck_y_start - 5:neck_y_end + 5,
                                search_left:search_right]
    heatmap = cv2.applyColorMap(neck_raw_crop, cv2.COLORMAP_JET)
    heatmap = cv2.resize(heatmap, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(os.path.join(OUT_DIR, "neck_heatmap.png"), heatmap)

    print(f"\nSaved: mask_128_vs_32.png, neck_heatmap.png")

print("\nDone!")
