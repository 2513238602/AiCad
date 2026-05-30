# -*- coding: utf-8 -*-
"""诊断: 在独立瓶身颈部区域用 Canny 边缘检测测量真实外径。"""
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

# 找 standalone_bottle 轮廓
bottle_c = None
bottle_idx = None
for i, c in enumerate(contours[:5]):
    cls = _classify_contour(mask, color_img, c)
    if cls['type'] == 'standalone_bottle':
        bottle_c = c
        bottle_idx = i
        break

if bottle_c is None:
    print("ERROR: no standalone_bottle found")
    sys.exit(1)

print(f"Using contour #{bottle_idx} as standalone_bottle")

# 获取旋转参数
single = np.zeros_like(mask)
cv2.drawContours(single, [bottle_c], -1, 255, cv2.FILLED)
single = cv2.bitwise_and(mask, single)
rotated_mask, M, new_size, angle = _rotate_mask_upright(single, bottle_c)
binary = (rotated_mask > 128).astype(np.uint8) * 255

# 获取 bottle profile（mask 基础）
ref_meas = _measure_single_contour(mask, color_img, bottle_c)
bp = _measure_bottle_profile(ref_meas)
print(f"\nMask-based profile:")
print(f"  neck_od_px={bp['neck_od_px']:.1f}, body_od_px={bp['body_od_px']:.1f}")
print(f"  ratio={bp['neck_body_ratio']:.3f}, orientation={bp['orientation']}")

# ── 旋转彩色图到对齐坐标系 ──
rotated_color = cv2.warpAffine(color_img, M, new_size, flags=cv2.INTER_LINEAR)
gray = cv2.cvtColor(rotated_color, cv2.COLOR_BGR2GRAY)

# 获取关键 Y 坐标
rows_any = np.any(binary > 0, axis=1)
y_top = int(np.where(rows_any)[0][0])
y_bot = int(np.where(rows_any)[0][-1])
total_h = y_bot - y_top

# 颈部区域 Y 范围（从 mask profile 获取）
neck_end_offset = bp['neck_height_px']
if bp['orientation'] == 'neck_at_top':
    neck_y_start = y_top
    neck_y_end = y_top + neck_end_offset
else:
    neck_y_start = y_bot - neck_end_offset
    neck_y_end = y_bot

print(f"\nNeck region: y={neck_y_start}..{neck_y_end} (height={neck_end_offset}px)")

# ── 方法1: Canny 边缘检测 ──
print("\n=== Method 1: Canny edge detection ===")

# 扩展颈部区域 + 周围空间（从颈区上方到肩区）
expand_y_start = max(0, neck_y_start - 10)
expand_y_end = min(gray.shape[0], neck_y_end + bp['shoulder_height_px'] // 2)

# 在颈部区域周围做 Canny
for canny_lo, canny_hi in [(20, 60), (30, 80), (40, 120), (50, 150)]:
    edges = cv2.Canny(gray, canny_lo, canny_hi)

    # 只看颈部区域的行
    widths = []
    for y in range(neck_y_start, neck_y_end):
        edge_cols = np.where(edges[y] > 0)[0]
        if len(edge_cols) >= 2:
            widths.append(float(edge_cols[-1] - edge_cols[0]))

    if widths:
        median_w = np.median(widths)
        print(f"  Canny({canny_lo},{canny_hi}): median_w={median_w:.1f}px, "
              f"samples={len(widths)}, range=[{min(widths):.0f}, {max(widths):.0f}]")
    else:
        print(f"  Canny({canny_lo},{canny_hi}): no edges found in neck region")

# ── 方法2: 水平 Sobel + 阈值 ──
print("\n=== Method 2: Horizontal Sobel ===")
sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
sobel_abs = np.abs(sobel_x)

for thresh in [10, 20, 30, 50]:
    widths2 = []
    for y in range(neck_y_start, neck_y_end):
        cols = np.where(sobel_abs[y] > thresh)[0]
        if len(cols) >= 2:
            widths2.append(float(cols[-1] - cols[0]))
    if widths2:
        median_w2 = np.median(widths2)
        print(f"  Sobel thresh={thresh}: median_w={median_w2:.1f}px, "
              f"samples={len(widths2)}")
    else:
        print(f"  Sobel thresh={thresh}: no edges found")

# ── 方法3: 原始灰度亮度阈值（背景通常比玻璃亮或暗） ──
print("\n=== Method 3: Brightness threshold ===")
# 背景区域亮度（mask 外区域）
bg_region = gray[neck_y_start:neck_y_end].copy()
fg_mask_rows = binary[neck_y_start:neck_y_end] > 128
bg_pixels = bg_region[~fg_mask_rows]
if len(bg_pixels) > 0:
    bg_median = np.median(bg_pixels)
    print(f"  Background brightness: {bg_median:.0f}")
else:
    bg_median = 200  # 假设白色背景
    print(f"  Background brightness: assumed {bg_median}")

# 对每行，找亮度明显不同于背景的区域
for offset in [20, 30, 40, 50]:
    thresh_low = bg_median - offset
    thresh_high = bg_median + offset
    widths3 = []
    for y in range(neck_y_start, neck_y_end):
        row = gray[y].astype(np.float64)
        # 与背景差异 > offset 的像素
        diff = np.abs(row - bg_median)
        cols = np.where(diff > offset)[0]
        if len(cols) >= 2:
            widths3.append(float(cols[-1] - cols[0]))
    if widths3:
        median_w3 = np.median(widths3)
        print(f"  bg_diff>{offset}: median_w={median_w3:.1f}px, "
              f"samples={len(widths3)}")
    else:
        print(f"  bg_diff>{offset}: no significant region")

# ── 方法4: 对肩部-体部区域测量 mask 宽度用于验证 ──
print("\n=== Method 4: Mask width at shoulder/body transition ===")
wp = (binary > 128).sum(axis=1).astype(np.float64)
if bp['orientation'] == 'neck_at_top':
    shoulder_start_y = y_top + neck_end_offset
    shoulder_end_y = shoulder_start_y + bp['shoulder_height_px']
    body_start_y = shoulder_end_y
    body_end_y = y_bot
else:
    body_start_y = y_top
    body_end_y = y_top + (total_h - neck_end_offset - bp['shoulder_height_px'])
    shoulder_start_y = body_end_y
    shoulder_end_y = shoulder_start_y + bp['shoulder_height_px']

# 肩顶宽度 = 接近颈部的宽度
if shoulder_start_y < shoulder_end_y:
    shoulder_top_w = float(np.median(wp[shoulder_start_y:min(shoulder_start_y + 5, shoulder_end_y)]))
    shoulder_bot_w = float(np.median(wp[max(shoulder_end_y - 5, shoulder_start_y):shoulder_end_y]))
    print(f"  Shoulder top (near neck): {shoulder_top_w:.1f}px")
    print(f"  Shoulder bottom (near body): {shoulder_bot_w:.1f}px")
if body_start_y < body_end_y:
    body_median_w = float(np.median(wp[body_start_y:body_end_y]))
    print(f"  Body median: {body_median_w:.1f}px")

# ── 保存可视化 ──
# 在旋转后的彩色图上标记颈部区域
vis = rotated_color.copy()
cv2.rectangle(vis, (0, neck_y_start), (new_size[0], neck_y_end), (0, 0, 255), 2)
cv2.putText(vis, "neck region", (5, neck_y_start - 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

# 也标注 mask 边界
for y in range(neck_y_start, neck_y_end):
    cols = np.where(binary[y] > 128)[0]
    if len(cols) >= 2:
        cv2.circle(vis, (int(cols[0]), y), 1, (255, 0, 0), -1)  # 左边界
        cv2.circle(vis, (int(cols[-1]), y), 1, (255, 0, 0), -1)  # 右边界

# Canny 边缘
edges = cv2.Canny(gray, 30, 80)
for y in range(neck_y_start, neck_y_end):
    edge_cols = np.where(edges[y] > 0)[0]
    for c in edge_cols:
        cv2.circle(vis, (c, y), 1, (0, 255, 0), -1)  # 绿色 = Canny 边缘

cv2.imwrite(os.path.join(OUT_DIR, "neck_edge_debug.png"), vis)

# 保存颈部区域放大图
neck_crop = rotated_color[max(0, neck_y_start - 20):neck_y_end + 20, :]
neck_crop = cv2.resize(neck_crop, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
cv2.imwrite(os.path.join(OUT_DIR, "neck_region_zoomed.png"), neck_crop)

print(f"\nSaved debug images to {OUT_DIR}/")
print("Expected neck_od: ~86px (17mm * 5.08px/mm)")
print(f"Mask-based neck_od: {bp['neck_od_px']:.1f}px ({bp['neck_od_px']/5.08:.1f}mm)")
