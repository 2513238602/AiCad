# -*- coding: utf-8 -*-
"""诊断: 可视化每个轮廓的 width_profile + 分类结果。"""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import cv2
import numpy as np

from auto_pipeline import (
    _find_largest_contour, _classify_contour, _rotate_mask_upright,
    _measure_single_contour, _measure_bottle_profile,
)

IMG_PATH = os.path.join(os.path.dirname(__file__),
                        "picture", "A3_round_pointed", "cairui_cone_01.webp")
OUT_DIR = os.path.join(os.path.dirname(__file__), "diag_output")
os.makedirs(OUT_DIR, exist_ok=True)

# ── 1. BiRefNet 去背景 ──
print("Loading BiRefNet...")
from auto_pipeline import birefnet_mask
color_img = cv2.imread(IMG_PATH)
if color_img is None:
    print(f"ERROR: cannot read {IMG_PATH}")
    sys.exit(1)
print(f"Image size: {color_img.shape}")

mask = birefnet_mask(IMG_PATH)
print(f"Mask size: {mask.shape}, unique vals: {len(np.unique(mask))}")

# Resize mask if needed
if mask.shape[:2] != color_img.shape[:2]:
    mask = cv2.resize(mask, (color_img.shape[1], color_img.shape[0]),
                      interpolation=cv2.INTER_NEAREST)
    print(f"Resized mask to {mask.shape}")

# ── 2. 找轮廓 + 分类 ──
contours = _find_largest_contour(mask)
print(f"\nFound {len(contours)} contours")

for i, c in enumerate(contours[:5]):
    cls = _classify_contour(mask, color_img, c)
    area = int(cv2.contourArea(c))
    x, y, w, h = cv2.boundingRect(c)
    print(f"\n{'='*60}")
    print(f"Contour #{i}: {cls['type']} (conf={cls['confidence']:.2f})")
    print(f"  Bounding rect: x={x}, y={y}, w={w}, h={h}")
    print(f"  Area: {area}px², Aspect: {cls.get('aspect', '?')}")
    print(f"  S_upper={cls.get('s_upper',0)}, S_lower={cls.get('s_lower',0)}")
    print(f"  V_upper={cls.get('v_upper',0)}, V_lower={cls.get('v_lower',0)}")

    # ── 3. 提取该轮廓的独立 mask + 旋转对齐 ──
    single = np.zeros_like(mask)
    cv2.drawContours(single, [c], -1, 255, cv2.FILLED)
    single = cv2.bitwise_and(mask, single)

    rotated, M, new_size, angle = _rotate_mask_upright(single, c)
    binary = (rotated > 128).astype(np.uint8) * 255

    # 保存旋转对齐后的 mask
    cv2.imwrite(os.path.join(OUT_DIR, f"contour_{i}_{cls['type']}_mask.png"), binary)

    # ── 4. Width profile ──
    width_profile = (binary > 128).sum(axis=1).astype(np.float64)
    rows_any = np.any(binary > 0, axis=1)
    if not rows_any.any():
        print("  No foreground rows!")
        continue
    y_top = int(np.where(rows_any)[0][0])
    y_bot = int(np.where(rows_any)[0][-1])

    # 画 width profile 图
    profile_h = y_bot - y_top
    max_w = float(width_profile.max())
    vis = np.zeros((binary.shape[0], 400, 3), dtype=np.uint8)
    for row in range(y_top, y_bot + 1):
        w_px = int(width_profile[row])
        bar_w = int(w_px / max_w * 380) if max_w > 0 else 0
        cv2.line(vis, (0, row), (bar_w, row), (0, 255, 0), 1)

    # 标注关键位置
    cv2.putText(vis, f"y_top={y_top}", (5, y_top + 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    cv2.putText(vis, f"y_bot={y_bot}", (5, y_bot - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    cv2.putText(vis, f"max_w={max_w:.0f}px", (5, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

    # 如果这是 standalone_bottle，运行 bottle profile
    if cls['type'] == 'standalone_bottle':
        ref_meas = _measure_single_contour(mask, color_img, c)
        if "error" not in ref_meas:
            bp = _measure_bottle_profile(ref_meas)
            if bp:
                print(f"  Bottle Profile: neck_od_px={bp['neck_od_px']:.1f}, "
                      f"body_od_px={bp['body_od_px']:.1f}, "
                      f"ratio={bp['neck_body_ratio']:.3f}")
                # 在 profile 图上标注 neck/shoulder/body 区域
                neck_end = bp['neck_height_px']
                shoulder_end = neck_end + bp['shoulder_height_px']
                if bp['orientation'] == 'neck_at_top':
                    # neck_end 和 shoulder_end 是从 y_top 开始的偏移
                    cv2.line(vis, (0, y_top + neck_end), (390, y_top + neck_end),
                             (0, 0, 255), 1)
                    cv2.putText(vis, f"neck_end (w={bp['neck_od_px']:.0f}px)",
                                (5, y_top + neck_end - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
                    cv2.line(vis, (0, y_top + shoulder_end), (390, y_top + shoulder_end),
                             (255, 0, 0), 1)
                    cv2.putText(vis, "shoulder_end",
                                (5, y_top + shoulder_end - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 0, 0), 1)
            else:
                print("  Bottle Profile: returned None")

    # 保存
    combined = np.hstack([binary[:, :min(binary.shape[1], 300)],
                          cv2.cvtColor(vis[:, :400], cv2.COLOR_BGR2GRAY)
                              .reshape(binary.shape[0], 400)])
    cv2.imwrite(os.path.join(OUT_DIR, f"contour_{i}_{cls['type']}_profile.png"), vis)
    print(f"  Saved: contour_{i}_{cls['type']}_mask.png + _profile.png")

# ── 5. 额外：在原图上标记每个轮廓 ──
annotated = color_img.copy()
colors = [(0, 255, 0), (0, 0, 255), (255, 0, 0), (255, 255, 0), (0, 255, 255)]
for i, c in enumerate(contours[:5]):
    cls = _classify_contour(mask, color_img, c)
    cv2.drawContours(annotated, [c], -1, colors[i % len(colors)], 2)
    x, y, w, h = cv2.boundingRect(c)
    cv2.putText(annotated, f"#{i} {cls['type']}", (x, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, colors[i % len(colors)], 2)
cv2.imwrite(os.path.join(OUT_DIR, "annotated_contours.png"), annotated)
print(f"\nSaved annotated_contours.png")
print("Done!")
