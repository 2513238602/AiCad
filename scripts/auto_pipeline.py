# -*- coding: utf-8 -*-
"""
BiRefNet + CV + VLM 自动化 Pipeline
从参考图片自动提取唇釉瓶 CAD 参数，用于 Gallery 预构建。

三职分工（自动版）：
  - BiRefNet: 背景剔除 → 产品轮廓 mask（替代 GrabCut，支持透明瓶身）
  - CV: 定量测量 — 锥度角、cap/bottle 比例、宽径比
  - VLM: 定性分类 — 截面形状、顶面形态、肩部风格、纹理

用法 (Python 3.11，需安装 rembg / opencv-python / Pillow):
  python scripts/auto_pipeline.py tests/picture/A3_round_pointed/cairui_cone_01.webp \
    --total-height 108.7 --body-od 24 --neck-od 17

输出:
  artifacts/auto_pipeline/<name>_result.json  — Gallery-ready vlm_shape
  artifacts/auto_pipeline/<name>_debug.png    — 调试可视化
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "artifacts" / "auto_pipeline"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# VLM API
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault(
    "GLM_API_KEY", "0d44fbe7c576473c8d89b85046b1edc3.MWR2xsYm7EIVbpZW"
)


# ════════════════════════════════════════════════════════════════════════
# Stage 1: BiRefNet 背景剔除
# ════════════════════════════════════════════════════════════════════════

_birefnet_session = None  # 全局缓存，避免每次请求重新加载模型


def _detect_solid_background(color_img: np.ndarray) -> dict:
    """检测图片是否为纯色背景，返回 {is_solid, bg_color, bg_value}"""
    h, w = color_img.shape[:2]
    # 采样四条边缘（各取 5px 宽的条带）
    border = 5
    strips = [
        color_img[:border, :],          # 上
        color_img[h - border:, :],      # 下
        color_img[:, :border],          # 左
        color_img[:, w - border:],      # 右
    ]
    pixels = np.concatenate([s.reshape(-1, 3) for s in strips], axis=0)
    median_color = np.median(pixels, axis=0).astype(np.uint8)
    # 判断纯色：所有边缘像素与中位色的距离 < 阈值
    diffs = np.sqrt(np.sum((pixels.astype(np.float32) - median_color.astype(np.float32)) ** 2, axis=1))
    uniform_ratio = np.mean(diffs < 30)  # 90% 以上像素色差 < 30
    is_solid = uniform_ratio > 0.85
    bg_value = float(np.mean(median_color))  # 0=纯黑, 255=纯白
    return {
        "is_solid": is_solid,
        "bg_color": median_color,
        "bg_value": bg_value,
        "uniformity": round(float(uniform_ratio), 3),
    }


def _threshold_mask_for_solid_bg(color_img: np.ndarray, bg_info: dict) -> np.ndarray:
    """对纯色背景图片，用颜色阈值生成补充 mask（捕获透明玻璃的高光/折射）"""
    bg_color = bg_info["bg_color"].astype(np.float32)
    img_f = color_img.astype(np.float32)
    # 每像素与背景色的欧氏距离
    diff = np.sqrt(np.sum((img_f - bg_color) ** 2, axis=2))
    # 阈值：与背景色差距 > threshold 的视为前景
    # 暗背景用较低阈值（玻璃高光微弱但可见），亮背景稍高
    if bg_info["bg_value"] < 80:
        threshold = 18  # 黑色背景：微弱高光也要捞
    elif bg_info["bg_value"] > 200:
        threshold = 25  # 白色背景：阈值稍高避免噪点
    else:
        threshold = 22
    fg = (diff > threshold).astype(np.uint8) * 255
    # 形态学操作：闭合小空洞 + 去噪
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, kernel, iterations=2)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, kernel, iterations=1)
    return fg


def birefnet_mask(image_path: str, color_img: np.ndarray = None) -> np.ndarray:
    """使用 BiRefNet 生成前景 mask（灰度 0-255），纯色背景时自动补充"""
    global _birefnet_session
    from rembg import new_session, remove

    if _birefnet_session is None:
        print("  [BiRefNet] 首次加载模型（后续复用）...")
        _birefnet_session = new_session("birefnet-general")
    else:
        print("  [BiRefNet] 复用已缓存模型")

    img = Image.open(image_path)
    print(f"  [BiRefNet] 处理 {img.size[0]}x{img.size[1]} 图片...")
    mask_pil = remove(img, session=_birefnet_session, only_mask=True)
    mask = np.array(mask_pil)
    fg_pct = np.sum(mask > 128) / mask.size * 100
    print(f"  [BiRefNet] 完成, 前景占比 {fg_pct:.1f}%")

    # ── 纯色背景补充分割 ──
    if color_img is not None:
        bg_info = _detect_solid_background(color_img)
        if bg_info["is_solid"]:
            print(f"  [背景检测] 纯色背景 (亮度={bg_info['bg_value']:.0f}, "
                  f"均匀度={bg_info['uniformity']:.3f})")
            supp_mask = _threshold_mask_for_solid_bg(color_img, bg_info)
            supp_pct = np.sum(supp_mask > 128) / supp_mask.size * 100
            # 合并：BiRefNet ∪ 补充掩码
            combined = np.maximum(mask, supp_mask)
            combined_pct = np.sum(combined > 128) / combined.size * 100
            gain = combined_pct - fg_pct
            if gain > 0.5:
                print(f"  [补充分割] 前景: {fg_pct:.1f}% → {combined_pct:.1f}% "
                      f"(+{gain:.1f}%, 补充={supp_pct:.1f}%)")
                mask = combined
            else:
                print(f"  [补充分割] 增益不足({gain:.1f}%), 保持BiRefNet原始掩码")
        else:
            print(f"  [背景检测] 非纯色背景 (均匀度={bg_info['uniformity']:.3f}), 跳过补充")

    return mask


# ════════════════════════════════════════════════════════════════════════
# Stage 2: CV 定量测量
# ════════════════════════════════════════════════════════════════════════

def _find_largest_contour(mask: np.ndarray, min_area_ratio: float = 0.005):
    """从 mask 中找到所有独立产品轮廓，按面积排序"""
    binary = (mask > 128).astype(np.uint8) * 255
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    total_area = mask.shape[0] * mask.shape[1]
    contours = [c for c in contours if cv2.contourArea(c) > total_area * min_area_ratio]
    contours.sort(key=cv2.contourArea, reverse=True)
    return contours


def _rotate_mask_upright(mask: np.ndarray, contour: np.ndarray):
    """用 minAreaRect 将轮廓旋转到垂直方向"""
    rect = cv2.minAreaRect(contour)
    rect_center, (rect_w, rect_h), rect_angle = rect
    rotation_angle = rect_angle + 90 if rect_w > rect_h else rect_angle

    h, w = mask.shape[:2]
    center = (float(rect_center[0]), float(rect_center[1]))
    M = cv2.getRotationMatrix2D(center, rotation_angle, 1.0)
    cos_a, sin_a = abs(M[0, 0]), abs(M[0, 1])
    new_w = int(h * sin_a + w * cos_a)
    new_h = int(h * cos_a + w * sin_a)
    M[0, 2] += (new_w - w) / 2
    M[1, 2] += (new_h - h) / 2
    rotated = cv2.warpAffine(mask, M, (new_w, new_h), flags=cv2.INTER_LINEAR)
    return rotated, M, (new_w, new_h), rotation_angle


def _find_color_boundary(color_img, M, new_size, binary, y_top, y_bot) -> dict:
    """颜色法检测 cap/bottle 边界（HSV 饱和度+亮度梯度）"""
    rotated_color = cv2.warpAffine(color_img, M, new_size, flags=cv2.INTER_LINEAR)
    rotated_hsv = cv2.cvtColor(rotated_color, cv2.COLOR_BGR2HSV).astype(np.float64)

    length = y_bot - y_top
    if length < 30:
        return {"boundary_y": (y_top + y_bot) // 2, "confidence": 0.0}

    s_profile = np.zeros(length)
    v_profile = np.zeros(length)
    valid = np.zeros(length, dtype=bool)

    for i, y in enumerate(range(y_top, y_bot)):
        fg = np.where(binary[y] > 128)[0]
        if len(fg) < 3:
            continue
        margin = max(1, len(fg) // 5)
        center_cols = fg[margin:-margin] if margin < len(fg) // 2 else fg
        if len(center_cols) == 0:
            continue
        s_profile[i] = np.median(rotated_hsv[y, center_cols, 1])
        v_profile[i] = np.median(rotated_hsv[y, center_cols, 2])
        valid[i] = True

    if valid.sum() < 20:
        return {"boundary_y": (y_top + y_bot) // 2, "confidence": 0.0}

    k = max(5, length // 20)
    if k % 2 == 0:
        k += 1
    s_smooth = np.convolve(s_profile, np.ones(k) / k, mode="same")
    v_smooth = np.convolve(v_profile, np.ones(k) / k, mode="same")

    ds = np.gradient(s_smooth)
    dv = np.gradient(v_smooth)
    color_change = np.abs(ds) + np.abs(dv) * 0.5

    margin_t = max(10, length // 7)
    margin_b = max(10, length // 7)
    search = color_change[margin_t : length - margin_b]
    if len(search) == 0:
        return {"boundary_y": (y_top + y_bot) // 2, "confidence": 0.0}

    k2 = max(3, len(search) // 20)
    if k2 % 2 == 0:
        k2 += 1
    search_smooth = np.convolve(search, np.ones(k2) / k2, mode="same")

    peak_local = np.argmax(search_smooth)
    peak_val = search_smooth[peak_local]
    mean_val = search_smooth.mean()

    boundary_idx = margin_t + peak_local
    boundary_y = y_top + boundary_idx

    if mean_val > 0:
        peak_ratio = peak_val / mean_val
        confidence = min(0.95, (peak_ratio - 1) / 5)
    else:
        confidence = 0.0

    return {
        "boundary_y": boundary_y,
        "boundary_ratio": boundary_idx / length,
        "confidence": confidence,
        "method": "color_change",
    }


def _find_geometric_boundary(width_profile, y_top, y_bot) -> dict:
    """几何法检测 cap/bottle 边界（分段线性拟合变点检测）"""
    segment = width_profile[y_top : y_bot + 1]
    length = len(segment)
    if length < 30:
        return {"boundary_y": (y_top + y_bot) // 2, "confidence": 0.0}

    kernel_size = max(7, length // 20)
    if kernel_size % 2 == 0:
        kernel_size += 1
    smoothed = np.convolve(segment, np.ones(kernel_size) / kernel_size, mode="same")

    margin = max(10, length // 7)
    s_start, s_end = margin, length - margin
    y_vals = np.arange(len(smoothed), dtype=np.float64)

    best_bic = float("inf")
    best_bp = length // 2
    best_left_slope = 0.0
    best_right_slope = 0.0

    step = max(1, (s_end - s_start) // 80)
    for bp in range(s_start + 10, s_end - 10, step):
        left_y = y_vals[s_start : bp + 1]
        left_w = smoothed[s_start : bp + 1]
        right_y = y_vals[bp : s_end + 1]
        right_w = smoothed[bp : s_end + 1]
        if len(left_y) < 5 or len(right_y) < 5:
            continue
        lc = np.polyfit(left_y, left_w, 1)
        rc = np.polyfit(right_y, right_w, 1)
        l_sse = np.sum((left_w - np.polyval(lc, left_y)) ** 2)
        r_sse = np.sum((right_w - np.polyval(rc, right_y)) ** 2)
        n = len(left_y) + len(right_y)
        bic = n * np.log((l_sse + r_sse) / n + 1e-10) + 4 * np.log(n)
        if bic < best_bic:
            best_bic = bic
            best_bp = bp
            best_left_slope = lc[0]
            best_right_slope = rc[0]

    slope_change = abs(best_left_slope - best_right_slope)
    max_slope = max(abs(best_left_slope), abs(best_right_slope), 0.01)
    slope_ratio = slope_change / max_slope

    return {
        "boundary_y": y_top + best_bp,
        "boundary_ratio": best_bp / length,
        "confidence": min(0.95, slope_ratio),
        "method": "piecewise_linear",
    }


def _measure_taper(binary, y_start, y_end) -> float:
    """测量指定 y 范围内的锥度角（度），两侧平均"""
    rows = np.arange(y_start, y_end + 1)
    left_edges, right_edges = [], []
    for y in rows:
        fg = np.where(binary[y] > 128)[0]
        if len(fg) < 3:
            continue
        left_edges.append((y, fg[0]))
        right_edges.append((y, fg[-1]))
    if len(left_edges) < 10:
        return 0.0

    def _fit_slope(arr):
        a = np.array(arr)
        if len(a) < 5:
            return 0.0
        c = np.polyfit(a[:, 0].astype(np.float64), a[:, 1].astype(np.float64), 1)
        return c[0]

    ls = abs(math.degrees(math.atan(abs(_fit_slope(left_edges)))))
    rs = abs(math.degrees(math.atan(abs(_fit_slope(right_edges)))))
    return (ls + rs) / 2


def _classify_contour(
    mask: np.ndarray, color_img: np.ndarray, contour: np.ndarray
) -> dict:
    """
    用 HSV 饱和度+亮度分类轮廓类型。

    先验：图中所有物件是同一产品的不同展示形态。
    返回:
      type: "assembly" | "standalone_bottle" | "open_cap" | "unknown"
      confidence: 0-1
      s_upper/s_lower: 上下段饱和度中位数（调试用）
    """
    single = np.zeros_like(mask)
    cv2.drawContours(single, [contour], -1, 255, cv2.FILLED)
    single = cv2.bitwise_and(mask, single)
    rotated, M, new_size, _ = _rotate_mask_upright(single, contour)
    binary = (rotated > 128).astype(np.uint8) * 255

    rows_any = np.any(binary > 0, axis=1)
    if not rows_any.any():
        return {"type": "unknown", "confidence": 0}
    y_top, y_bot = int(rows_any.nonzero()[0][0]), int(rows_any.nonzero()[0][-1])
    height = y_bot - y_top
    if height < 20:
        return {"type": "unknown", "confidence": 0}

    # HSV 分析
    rotated_color = cv2.warpAffine(color_img, M, new_size, flags=cv2.INTER_LINEAR)
    rotated_hsv = cv2.cvtColor(rotated_color, cv2.COLOR_BGR2HSV)

    seg = max(1, height // 3)

    def _median_sv(y_start, y_end):
        region_bin = binary[y_start:y_end]
        fg_mask = region_bin > 128
        if fg_mask.sum() < 10:
            return 0.0, 0.0
        hsv_region = rotated_hsv[y_start:y_end]
        s = float(np.median(hsv_region[:, :, 1][fg_mask]))
        v = float(np.median(hsv_region[:, :, 2][fg_mask]))
        return s, v

    s_up, v_up = _median_sv(y_top, y_top + seg)
    s_mid, v_mid = _median_sv(y_top + seg, y_top + 2 * seg)
    s_low, v_low = _median_sv(y_bot - seg, y_bot)

    # 宽度特征
    width_profile = (binary > 128).sum(axis=1).astype(np.float64)
    max_w = float(width_profile.max())
    aspect = height / max_w if max_w > 0 else 999

    has_color_upper = s_up > 40 or v_up > 200
    has_color_lower = s_low > 40 or v_low > 200
    low_s_overall = s_up < 30 and s_mid < 30 and s_low < 30

    info = {"s_upper": round(s_up, 1), "s_lower": round(s_low, 1),
            "v_upper": round(v_up, 1), "v_lower": round(v_low, 1),
            "aspect": round(aspect, 1)}

    if has_color_upper and not has_color_lower:
        # 上段有色、下段无色 → 装配体 or 开盖
        mid_w = float(np.median(width_profile[y_top + seg : y_top + 2 * seg]))
        if mid_w < max_w * 0.3 and aspect > 5:
            return {**info, "type": "open_cap", "confidence": 0.85}
        return {**info, "type": "assembly", "confidence": 0.9}
    elif low_s_overall and v_up < 180 and v_low < 180:
        return {**info, "type": "standalone_bottle", "confidence": 0.8}
    elif has_color_upper and has_color_lower:
        # 补充检查：如果有大段极细区域（刷杆特征），实际是打开的盖
        thin_count = int(np.sum(width_profile[y_top:y_bot + 1] < max_w * 0.2))
        if thin_count > height * 0.25:
            return {**info, "type": "open_cap", "confidence": 0.8}
        return {**info, "type": "assembly", "confidence": 0.6}
    else:
        return {**info, "type": "unknown", "confidence": 0.3}


def _measure_single_contour(
    mask: np.ndarray, color_img: np.ndarray, contour: np.ndarray
) -> dict:
    """
    对单个轮廓做完整 CV 测量，返回像素级原始数据。
    不做 mm 换算（由调用者根据校准策略决定）。
    """
    single = np.zeros_like(mask)
    cv2.drawContours(single, [contour], -1, 255, cv2.FILLED)
    single = cv2.bitwise_and(mask, single)

    rotated, M, new_size, angle = _rotate_mask_upright(single, contour)
    binary = (rotated > 128).astype(np.uint8) * 255

    rows_any = np.any(binary > 0, axis=1)
    if not rows_any.any():
        return {"error": "no_foreground"}
    y_top = int(np.where(rows_any)[0][0])
    y_bot = int(np.where(rows_any)[0][-1])
    total_height_px = y_bot - y_top
    if total_height_px < 20:
        return {"error": "too_small"}

    width_profile = (binary > 128).sum(axis=1).astype(np.float64)

    # 边界检测: 颜色法 + 几何法融合
    color_bd = _find_color_boundary(color_img, M, new_size, binary, y_top, y_bot)
    geo_bd = _find_geometric_boundary(width_profile, y_top, y_bot)
    if color_bd["confidence"] > 0.3 and color_bd["confidence"] >= geo_bd["confidence"]:
        boundary = color_bd
    else:
        boundary = geo_bd

    boundary_y = boundary["boundary_y"]
    cap_height_px = boundary_y - y_top
    bottle_height_px = y_bot - boundary_y

    # 宽度
    cap_bottom_w = float(width_profile[boundary_y])
    bottle_seg = width_profile[boundary_y : y_bot + 1]
    bottle_max_w = float(bottle_seg.max()) if len(bottle_seg) > 0 else 0
    max_width = float(width_profile.max())

    # 锥度
    cap_margin = max(1, cap_height_px // 10)
    cap_taper = _measure_taper(binary, y_top + cap_margin, boundary_y - cap_margin)
    bottle_margin = max(1, bottle_height_px // 5)
    bottle_taper = _measure_taper(
        binary, boundary_y + bottle_margin, y_bot - max(1, bottle_height_px // 10)
    )

    # 整件轮廓统一锥度（不分 cap/bottle，对连续锥面产品更准确）
    unified_margin = max(3, total_height_px // 8)
    unified_taper = _measure_taper(binary, y_top + unified_margin, y_bot - unified_margin)

    # 底部宽度（瓶底直径像素，用于比例推算 body_od）
    bottom_zone = width_profile[max(0, y_bot - max(3, total_height_px // 15)):y_bot + 1]
    bottom_w = float(np.median(bottom_zone)) if len(bottom_zone) > 0 else max_width

    return {
        "total_height_px": total_height_px,
        "cap_height_px": cap_height_px,
        "bottle_height_px": bottle_height_px,
        "cap_bottom_w_px": cap_bottom_w,
        "bottle_max_w_px": bottle_max_w,
        "max_width_px": max_width,
        "bottom_w_px": bottom_w,
        "cap_taper_deg": round(cap_taper, 2),
        "bottle_taper_deg": round(bottle_taper, 2),
        "unified_taper_deg": round(unified_taper, 2),
        "cap_ratio": round(cap_height_px / total_height_px, 3) if total_height_px > 0 else 0,
        "boundary_method": boundary.get("method", "unknown"),
        "boundary_confidence": round(boundary.get("confidence", 0), 2),
        "_binary": binary, "_width_profile": width_profile,
        "_y_top": y_top, "_y_bot": y_bot, "_boundary_y": boundary_y,
        "_M": M, "_new_size": new_size,
    }


def _measure_bottle_profile(ref_meas: dict) -> dict | None:
    """
    从独立 bottle 轮廓提取颈部特征（颈径、颈高、肩高）。

    输入: _measure_single_contour() 的返回值（像素级）。
    返回: {neck_od_px, neck_height_px, shoulder_height_px, body_od_px, orientation}
           或 None（数据不足）。
    """
    wp = ref_meas.get("_width_profile")
    y_top = ref_meas.get("_y_top", 0)
    y_bot = ref_meas.get("_y_bot", 0)
    if wp is None or y_bot - y_top < 40:
        return None

    total_h = y_bot - y_top
    seg = max(5, total_h // 8)

    # ── 1. 确定朝向：窄端 = 颈部 ──
    top_w = float(np.median(wp[y_top : y_top + seg]))
    bot_w = float(np.median(wp[y_bot - seg : y_bot]))
    neck_at_top = top_w < bot_w

    # 建立从颈→体方向的宽度序列
    if neck_at_top:
        profile = wp[y_top : y_bot + 1].copy()
    else:
        profile = wp[y_top : y_bot + 1][::-1].copy()

    n = len(profile)
    if n < 40:
        return None

    # ── 2. 平滑 ──
    kern = max(3, n // 30) | 1  # 奇数核
    smoothed = np.convolve(profile, np.ones(kern) / kern, mode="same")

    body_max_w = float(smoothed.max())
    if body_max_w < 10:
        return None

    # ── 3. 导数法找颈-肩边界 ──
    # 颈部特征：宽度几乎不变（导数≈0）
    # 肩部特征：宽度快速增大（导数显著为正）
    # 用一阶导数从≈0变为明显正值的拐点作为颈-肩边界
    grad = np.gradient(smoothed)
    grad_kern = max(5, n // 15) | 1
    grad_smooth = np.convolve(grad, np.ones(grad_kern) / grad_kern, mode="same")

    start = max(2, n // 20)
    neck_w_est = float(np.median(smoothed[start : max(start + 5, n // 5)]))
    if neck_w_est < 5:
        return None

    # 导数阈值：每像素宽度增量 > 体最大宽度的 0.15%（适应不同尺寸）
    grad_thresh = body_max_w * 0.0015
    # 需要连续多个像素超过阈值才确认（避免噪声触发）
    run_needed = max(3, n // 40)
    neck_end = n // 3  # 兜底
    run_count = 0
    for i in range(start, n * 2 // 3):
        if grad_smooth[i] > grad_thresh:
            run_count += 1
            if run_count >= run_needed:
                neck_end = i - run_needed + 1
                break
        else:
            run_count = 0

    # ── 4. 三角函数法算肩高 ──
    # 瓶身锥度段是一条直线。拟合它，得到斜率和截距。
    # 拟合线向上外推到瓶底，得到瓶身底部宽度；向上外推到它"退出"轮廓的位置
    # （即拟合线宽度 > 实际宽度的点），那就是瓶身顶端。
    # 瓶身长度 = 底端 - 顶端。肩高 = 总高 - 颈高 - 瓶身长度。
    light_kern = 3
    light_smooth = np.convolve(profile, np.ones(light_kern) / light_kern, mode="same")
    # 在确认的锥度段（40%-85%）拟合直线
    fit_lo = n * 40 // 100
    fit_hi = n * 85 // 100
    body_region = light_smooth[fit_lo:fit_hi]
    shoulder_end = min(n - 1, neck_end + n // 3)  # 兜底
    neck_const_end = neck_end  # 恒定宽度段末端（默认 = 导数法检测的颈端）
    if len(body_region) > 10:
        x_fit = np.arange(len(body_region), dtype=float)
        taper_slope, intercept = np.polyfit(x_fit, body_region, 1)
        # 拟合线在绝对位置 i 的预期宽度
        def _line_at(i):
            return taper_slope * (i - fit_lo) + intercept
        # 瓶身底端：取轮廓 90% 处（避开底部圆角）
        body_bottom_idx = n * 90 // 100
        # 瓶身顶端：从拟合区顶部向颈部扫描，
        # 找到拟合线宽度首次 > 实际宽度的位置（线"离开"轮廓）
        body_top_idx = fit_lo  # 默认：拟合区顶部
        tol = body_max_w * 0.02  # 2% 容差
        for i in range(fit_lo, neck_end, -1):
            line_w = _line_at(i)
            actual_w = light_smooth[i]
            deviation = line_w - actual_w
            if deviation > tol:
                body_top_idx = i + 1
                break
        else:
            body_top_idx = neck_end  # 直线一路延伸到颈部
        # 连续锥形瓶：锥度线以上全部归为颈部，肩高=0
        # body_top_idx = 瓶身顶端 = 颈部底端
        # 颈高 = body_top_idx，肩高 = 0
        if body_top_idx > neck_end:
            neck_end = body_top_idx   # 扩展颈部到锥度线起点
            shoulder_end = neck_end   # 肩高 = 0
        else:
            shoulder_end = neck_end

    # ── 5. 提取测量值 ──
    # 颈区宽度：取恒定宽度段（排除顶端唇口）的中位数
    neck_margin = max(2, neck_const_end // 10)
    neck_zone = smoothed[neck_margin : neck_const_end]
    if len(neck_zone) < 3:
        return None
    neck_od_px = float(np.median(neck_zone))

    neck_height_px = neck_end
    shoulder_height_px = shoulder_end - neck_end
    body_od_px = body_max_w

    orientation = "neck_at_top" if neck_at_top else "neck_at_bottom"

    # ── 6. 健壮性检查 ──
    neck_body_ratio = neck_od_px / body_od_px if body_od_px > 0 else 0
    # 唇釉瓶颈/体比通常在 0.4~0.9 之间；太低说明误检了非 bottle 轮廓
    if neck_body_ratio < 0.35 or neck_body_ratio > 0.95:
        return None
    # 颈高至少占总高 2%（锥形瓶颈部很短）
    if neck_height_px < total_h * 0.02:
        return None

    return {
        "neck_od_px": round(neck_od_px, 1),
        "neck_height_px": neck_height_px,
        "shoulder_height_px": shoulder_height_px,
        "body_od_px": round(body_od_px, 1),
        "neck_body_ratio": round(neck_body_ratio, 3),
        "orientation": orientation,
    }


def _detect_decorative_bands(
    color_img: np.ndarray, M, new_size: tuple,
    binary: np.ndarray, width_profile: np.ndarray,
    y_top: int, y_boundary: int, y_bot: int, px_per_mm: float,
) -> dict:
    """
    检测 collar（装饰环带）和 base_ring（底座台阶）。

    关键洞察：当 collar 与 cap 同色时（如玫瑰金），颜色边界 boundary_y
    实际落在 collar/body 交界处。因此 collar 在 boundary_y 之上的 "cap 段" 中。

    方法:
      - collar: 用 Canny 边缘密度在 cap 段中找光滑→纹理的过渡（cap/collar 边界）
      - base_ring: 用 width_profile 在底部找宽度突变
      - 颜色法: 作为辅助验证
    """
    cap_len = y_boundary - y_top
    bottle_len = y_bot - y_boundary
    if (cap_len < 30 and bottle_len < 30) or px_per_mm <= 0:
        return {"collar": {"detected": False}, "base_ring": {"detected": False}}

    rotated_color = cv2.warpAffine(color_img, M, new_size, flags=cv2.INTER_LINEAR)
    rotated_gray = cv2.cvtColor(rotated_color, cv2.COLOR_BGR2GRAY)

    collar_result = {"detected": False}
    base_ring_result = {"detected": False}

    # ═══════════════════════════════════════════════════════
    # Collar 检测：Canny 边缘密度法 —— 在 "cap 段" 中找纹理过渡
    # 光滑 cap 区域 edge density 低，竖纹 collar 区域 edge density 高
    # ═══════════════════════════════════════════════════════
    if cap_len >= 30:
        # Canny 边缘检测
        cap_region = rotated_gray[y_top:y_boundary, :]
        edges = cv2.Canny(cap_region, 30, 100)

        # 逐行计算边缘密度（边缘像素数 / 前景宽度）
        edge_density = np.zeros(cap_len)
        for i in range(cap_len):
            fg = np.where(binary[y_top + i] > 128)[0]
            fg_w = len(fg)
            if fg_w < 3:
                continue
            edge_count = np.sum(edges[i, fg] > 0)
            edge_density[i] = edge_count / fg_w

        # 平滑
        ek = max(5, cap_len // 15) | 1
        ed_smooth = np.convolve(edge_density, np.ones(ek) / ek, mode="same")

        # 跳过顶部 15% 和底部 5%（避免边界效应）
        search_start = max(3, cap_len // 7)
        search_end = cap_len - max(2, cap_len // 20)

        if search_end > search_start + 10:
            search_seg = ed_smooth[search_start:search_end]

            # 找密度最大梯度上升点（smooth cap → textured collar）
            d_ed = np.gradient(search_seg)
            dk = max(3, len(d_ed) // 15) | 1
            d_smooth = np.convolve(d_ed, np.ones(dk) / dk, mode="same")

            # 正梯度峰值 = 密度突然升高 = cap/collar 过渡
            rise_peak = np.argmax(d_smooth)
            rise_val = d_smooth[rise_peak]

            # 验证：过渡点两侧密度差异
            cap_collar_boundary_local = search_start + rise_peak
            above_mean = float(np.mean(ed_smooth[search_start:cap_collar_boundary_local]))
            below_mean = float(np.mean(ed_smooth[cap_collar_boundary_local:search_end]))

            density_ratio = below_mean / (above_mean + 1e-6)

            if density_ratio > 1.5 and rise_val > 0.005:
                # collar 区域：从 cap_collar_boundary 到 boundary_y
                collar_h_px = cap_len - cap_collar_boundary_local
                collar_h_mm = collar_h_px / px_per_mm

                # 置信度：基于密度比
                conf = min(0.95, (density_ratio - 1.0) / 3.0)
                conf = max(0.15, conf)

                # 宽度对比
                collar_w_median = float(np.median(
                    width_profile[y_top + cap_collar_boundary_local: y_boundary]))
                body_mid_s = y_boundary + int(bottle_len * 0.3)
                body_mid_e = y_boundary + int(bottle_len * 0.65)
                if body_mid_e > body_mid_s:
                    body_w_median = float(np.median(
                        width_profile[body_mid_s:body_mid_e]))
                else:
                    body_w_median = collar_w_median
                width_excess = (collar_w_median - body_w_median) / px_per_mm

                if collar_h_mm >= 2.0:
                    collar_result = {
                        "detected": True,
                        "height_mm": round(collar_h_mm, 1),
                        "height_px": collar_h_px,
                        "width_excess_mm": round(width_excess, 1),
                        "confidence": round(conf, 2),
                        "method": "edge_density",
                        "density_ratio": round(density_ratio, 2),
                        "corrected_cap_height_px": cap_collar_boundary_local,
                    }

    # ═══════════════════════════════════════════════════════
    # Base ring 检测：宽度突变法
    # ═══════════════════════════════════════════════════════
    if bottle_len >= 20:
        body_mid_start = int(bottle_len * 0.3)
        body_mid_end = int(bottle_len * 0.6)
        body_seg = width_profile[y_boundary + body_mid_start: y_boundary + body_mid_end]
        if len(body_seg) > 0:
            body_median_w = float(np.median(body_seg))
        else:
            body_median_w = 0

        # 从底部向上扫描，找宽度回落到 body_median_w 的位置
        base_ring_h_px = 0
        base_w_threshold = body_median_w * 1.02  # 宽 2% 以上视为 base_ring
        for i in range(bottle_len - 1, max(0, bottle_len - bottle_len // 3), -1):
            row_w = float(width_profile[y_boundary + i])
            if row_w < base_w_threshold:
                base_ring_h_px = bottle_len - 1 - i
                break

        if base_ring_h_px > 0:
            base_ring_h_mm = base_ring_h_px / px_per_mm
            bottom_w = float(np.median(
                width_profile[y_bot - base_ring_h_px: y_bot]))
            base_excess = (bottom_w - body_median_w) / px_per_mm

            if base_ring_h_mm >= 1.0 and base_excess >= 0.1:
                width_conf = min(0.7, base_excess / 2.0)
                conf = min(0.95, 0.2 + width_conf)

                base_ring_result = {
                    "detected": True,
                    "height_mm": round(base_ring_h_mm, 1),
                    "height_px": base_ring_h_px,
                    "width_excess_mm": round(base_excess, 1),
                    "confidence": round(conf, 2),
                }

    return {"collar": collar_result, "base_ring": base_ring_result}


# ════════════════════════════════════════════════════════════════════════
# 方形瓶投影宽度修正 — 棱线检测
# ════════════════════════════════════════════════════════════════════════

def _detect_square_rotation_correction(
    color_img: np.ndarray, contour: np.ndarray
) -> tuple[float, float]:
    """检测方形瓶拍摄旋转角度，返回 (修正系数, 棱线相对位置)。

    方形瓶旋转 θ 角拍照时，投影宽度 W = 棱长 s × (cosθ + sinθ)。
    通过 Sobel 竖向边缘检测找到瓶身上的棱线位置，
    将 W 分为正面分量 W_f 和侧面分量 W_s，
    用勾股定理还原真实棱长: s = √(W_f² + W_s²)。

    圆形瓶无内部竖向棱线 → 返回 (1.0, -1)，不修正。

    Returns:
        (correction_factor, edge_relative_position)
        correction_factor: 0.707~1.0, 乘以投影宽度得到棱长
        edge_relative_position: 棱线在宽度中的比例 (0~1), -1=未检测到
    """
    x, y, w, h = cv2.boundingRect(contour)
    if w < 20 or h < 40:
        return 1.0, -1

    # 聚焦瓶身区域（高度 35%~90%，避开顶部颈部/盖和底边）
    body_y0 = y + int(h * 0.35)
    body_y1 = y + int(h * 0.90)
    if body_y1 - body_y0 < 20:
        return 1.0, -1

    # 轮廓填充遮罩
    cmask = np.zeros(color_img.shape[:2], dtype=np.uint8)
    cv2.drawContours(cmask, [contour], -1, 255, -1)

    # 灰度 + 竖向 Sobel（检测水平方向亮度变化 = 竖向棱线）
    gray = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY) if len(color_img.shape) == 3 else color_img
    sobel_x = np.abs(cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3))

    # 裁剪到瓶身区域
    body_sobel = sobel_x[body_y0:body_y1, x:x + w].copy()
    body_cmask = cmask[body_y0:body_y1, x:x + w]
    body_sobel[body_cmask == 0] = 0

    # 列均值：每列在所有瓶身行上的平均 Sobel 响应
    col_count = (body_cmask > 0).sum(axis=0).astype(np.float64)
    col_count[col_count == 0] = 1
    col_mean = body_sobel.sum(axis=0) / col_count

    # 排除边界 12%（轮廓边缘自身的 Sobel 响应不是棱线）
    margin = max(4, int(w * 0.12))
    if w - 2 * margin < 10:
        return 1.0, -1
    inner = col_mean[margin:w - margin].copy()

    # 平滑（3px 均值核）
    ks = max(3, int(len(inner) * 0.02))
    kernel = np.ones(ks) / ks
    inner_s = np.convolve(inner, kernel, mode="same")

    baseline = float(np.median(inner_s))
    if baseline < 1e-6:
        return 1.0, -1

    peak_val = float(inner_s.max())
    # 峰值须 > 基线 2.5 倍（明确的棱线信号）
    if peak_val < baseline * 2.5:
        return 1.0, -1

    peak_idx = int(np.argmax(inner_s))

    # 抑制主峰附近，检查是否有第二峰
    # 若有同等强度的第二峰 → 可能是装饰窗口/logo 的左右边缘，不是棱线
    suppressed = inner_s.copy()
    sup_w = max(5, int(len(inner) * 0.12))
    sl = max(0, peak_idx - sup_w)
    sr = min(len(suppressed), peak_idx + sup_w + 1)
    suppressed[sl:sr] = 0
    second_val = float(suppressed.max())

    if second_val > peak_val * 0.5:
        # 第二峰接近主峰强度 → 多半是装饰特征的对称边缘
        return 1.0, -1

    # 棱线位置（相对于整个轮廓宽度）
    edge_col = margin + peak_idx
    rel_pos = edge_col / w

    # 棱线须在 15%~85% 范围内（太靠边说明误检到轮廓边缘）
    if rel_pos < 0.15 or rel_pos > 0.85:
        return 1.0, -1

    # 修正系数: s / W = √(pos² + (1-pos)²)
    # 验证: pos=0.5(45°) → √0.5 = 0.707;  pos=0.7(~23°) → 0.781
    correction = math.sqrt(rel_pos ** 2 + (1 - rel_pos) ** 2)

    return round(correction, 4), round(rel_pos, 3)


def _sample_component_colors(
    color_img: np.ndarray, M, new_size: tuple,
    binary: np.ndarray, y_top: int, y_bot: int, boundary_y: int,
) -> dict:
    """从旋转后图像中采样 cap 和 bottle 区域的代表色 RGB。

    策略：取各区域中间 60% 区域的前景像素，逐通道取中位数，
    避免边缘混色和背景残留干扰。
    """
    rotated_color = cv2.warpAffine(color_img, M, new_size, flags=cv2.INTER_LINEAR)

    def _component_stats(y_start, y_end, prefix: str):
        region_h = y_end - y_start
        if region_h < 10:
            return {
                f"{prefix}_color_rgb": [128, 128, 128],
                f"{prefix}_base_color_rgb": [128, 128, 128],
                f"{prefix}_shadow_color_rgb": [82, 82, 82],
                f"{prefix}_highlight_color_rgb": [220, 220, 220],
                f"{prefix}_highlight_strength": 0.0,
                f"{prefix}_contrast": 0.0,
                f"{prefix}_saturation": 0.0,
            }
        margin = max(3, region_h // 5)
        y_lo, y_hi = y_start + margin, y_end - margin
        pixels = []
        for y in range(y_lo, y_hi):
            fg = np.where(binary[y] > 128)[0]
            if len(fg) < 3:
                continue
            col_margin = max(1, len(fg) // 5)
            center_cols = fg[col_margin:-col_margin] if col_margin < len(fg) // 2 else fg
            if len(center_cols) == 0:
                continue
            pixels.append(rotated_color[y, center_cols])
        if len(pixels) == 0:
            return {
                f"{prefix}_color_rgb": [128, 128, 128],
                f"{prefix}_base_color_rgb": [128, 128, 128],
                f"{prefix}_shadow_color_rgb": [82, 82, 82],
                f"{prefix}_highlight_color_rgb": [220, 220, 220],
                f"{prefix}_highlight_strength": 0.0,
                f"{prefix}_contrast": 0.0,
                f"{prefix}_saturation": 0.0,
            }

        all_bgr = np.vstack(pixels).astype(np.float32)
        all_rgb = all_bgr[:, ::-1]
        luma = (
            0.2126 * all_rgb[:, 0]
            + 0.7152 * all_rgb[:, 1]
            + 0.0722 * all_rgb[:, 2]
        )
        median_rgb = np.median(all_rgb, axis=0)
        p10 = float(np.percentile(luma, 10))
        p50 = float(np.percentile(luma, 50))
        p90 = float(np.percentile(luma, 90))
        p97 = float(np.percentile(luma, 97))
        shadow_rgb = np.median(all_rgb[luma <= p10 + 1e-3], axis=0)
        highlight_rgb = np.median(all_rgb[luma >= p97 - 1e-3], axis=0)
        highlight_strength = max(0.0, min(1.0, (p97 - p50) / 120.0))
        contrast = max(0.0, min(1.0, (p90 - p10) / 160.0))
        chroma = (all_rgb.max(axis=1) - all_rgb.min(axis=1)) / 255.0
        saturation = max(0.0, min(1.0, float(np.median(chroma))))

        def _to_rgb(values):
            arr = np.clip(np.round(values), 0, 255).astype(int)
            return [int(arr[0]), int(arr[1]), int(arr[2])]

        return {
            f"{prefix}_color_rgb": _to_rgb(median_rgb),
            f"{prefix}_base_color_rgb": _to_rgb(median_rgb),
            f"{prefix}_shadow_color_rgb": _to_rgb(shadow_rgb),
            f"{prefix}_highlight_color_rgb": _to_rgb(highlight_rgb),
            f"{prefix}_highlight_strength": round(float(highlight_strength), 3),
            f"{prefix}_contrast": round(float(contrast), 3),
            f"{prefix}_saturation": round(float(saturation), 3),
        }

    sampled = {}
    sampled.update(_component_stats(y_top, boundary_y, "cap"))
    sampled.update(_component_stats(boundary_y, y_bot, "bottle"))
    return sampled


def _clamp_float(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _mix_rgb(a: list[int], b: list[int], t: float) -> list[int]:
    t = _clamp_float(t, 0.0, 1.0)
    out = []
    for i in range(3):
        av = int(a[i]) if i < len(a) else 128
        bv = int(b[i]) if i < len(b) else 128
        out.append(int(round(av * (1.0 - t) + bv * t)))
    return out


def _render_fields_from_reference(
    prefix: str, material: str, sampled: dict,
) -> dict:
    """Build reference-matched PBR fields from color statistics."""
    base_rgb = sampled.get(f"{prefix}_base_color_rgb") or sampled.get(f"{prefix}_color_rgb") or [128, 128, 128]
    shadow_rgb = sampled.get(f"{prefix}_shadow_color_rgb") or _mix_rgb(base_rgb, [0, 0, 0], 0.35)
    highlight_rgb = sampled.get(f"{prefix}_highlight_color_rgb") or _mix_rgb(base_rgb, [255, 255, 255], 0.5)
    highlight_strength = _clamp_float(sampled.get(f"{prefix}_highlight_strength", 0.35), 0.0, 1.0)
    contrast = _clamp_float(sampled.get(f"{prefix}_contrast", 0.35), 0.0, 1.0)
    saturation = _clamp_float(sampled.get(f"{prefix}_saturation", 0.25), 0.0, 1.0)
    gloss = _clamp_float(highlight_strength * 0.7 + contrast * 0.3, 0.0, 1.0)
    roughness_hint = _clamp_float(0.72 - gloss * 0.52, 0.06, 0.82)

    fields = {
        f"{prefix}_material": material,
        f"{prefix}_color_rgb": base_rgb,
        f"{prefix}_base_color_rgb": base_rgb,
        f"{prefix}_shadow_color_rgb": shadow_rgb,
        f"{prefix}_highlight_color_rgb": highlight_rgb,
        f"{prefix}_highlight_strength": round(highlight_strength, 3),
        f"{prefix}_contrast": round(contrast, 3),
        f"{prefix}_saturation": round(saturation, 3),
        f"{prefix}_roughness": round(roughness_hint, 3),
        f"{prefix}_clearcoat": round(0.25 + gloss * 0.45, 3),
        f"{prefix}_clearcoat_roughness": round(_clamp_float(0.22 - gloss * 0.12, 0.04, 0.28), 3),
        f"{prefix}_metalness": 0.0,
        f"{prefix}_transmission": 0.0,
        f"{prefix}_opacity": 1.0,
        f"{prefix}_ior": 1.46,
        f"{prefix}_thickness": 1.2,
        f"{prefix}_attenuation_color_rgb": base_rgb,
        f"{prefix}_attenuation_distance": 24.0,
        f"{prefix}_env_intensity": round(0.55 + gloss * 0.35, 3),
        f"{prefix}_iridescence": 0.0,
        f"{prefix}_sheen": 0.0,
        f"{prefix}_sheen_roughness": 0.5,
    }

    if material == "transparent_glass":
        fields.update({
            f"{prefix}_base_color_rgb": _mix_rgb(base_rgb, [255, 255, 255], 0.28),
            f"{prefix}_roughness": round(_clamp_float(0.16 - gloss * 0.09, 0.035, 0.18), 3),
            f"{prefix}_clearcoat": 1.0,
            f"{prefix}_clearcoat_roughness": 0.045,
            f"{prefix}_transmission": round(_clamp_float(0.62 + gloss * 0.22, 0.58, 0.88), 3),
            f"{prefix}_opacity": 0.62,
            f"{prefix}_thickness": 2.4,
            f"{prefix}_attenuation_distance": round(14.0 + (1.0 - saturation) * 16.0, 2),
            f"{prefix}_env_intensity": 1.05,
        })
    elif material == "frosted_glass":
        fields.update({
            f"{prefix}_base_color_rgb": _mix_rgb(base_rgb, [255, 255, 255], 0.18),
            f"{prefix}_roughness": round(_clamp_float(0.56 + (1.0 - gloss) * 0.16, 0.44, 0.82), 3),
            f"{prefix}_clearcoat": 0.38,
            f"{prefix}_clearcoat_roughness": 0.24,
            f"{prefix}_transmission": 0.36,
            f"{prefix}_opacity": 0.78,
            f"{prefix}_thickness": 1.8,
            f"{prefix}_attenuation_distance": 18.0,
            f"{prefix}_env_intensity": 0.82,
        })
    elif material == "matte_plastic":
        fields.update({
            f"{prefix}_roughness": round(_clamp_float(0.62 + (1.0 - gloss) * 0.18, 0.56, 0.88), 3),
            f"{prefix}_clearcoat": 0.08,
            f"{prefix}_clearcoat_roughness": 0.42,
            f"{prefix}_env_intensity": 0.45,
        })
    elif material == "metal":
        fields.update({
            f"{prefix}_metalness": 0.86,
            f"{prefix}_roughness": round(_clamp_float(0.32 - gloss * 0.14, 0.14, 0.38), 3),
            f"{prefix}_clearcoat": 0.22,
            f"{prefix}_env_intensity": 1.1,
        })
    elif material == "pearl":
        fields.update({
            f"{prefix}_base_color_rgb": _mix_rgb(base_rgb, [255, 248, 238], 0.14),
            f"{prefix}_roughness": round(_clamp_float(0.34 - gloss * 0.08, 0.22, 0.42), 3),
            f"{prefix}_clearcoat": 0.58,
            f"{prefix}_clearcoat_roughness": 0.16,
            f"{prefix}_iridescence": 0.42,
            f"{prefix}_sheen": 0.38,
            f"{prefix}_sheen_roughness": 0.35,
            f"{prefix}_env_intensity": 0.92,
        })

    if prefix == "bottle" and material in ("transparent_glass", "frosted_glass"):
        fields.update({
            "bottle_liquid_color_rgb": _mix_rgb(base_rgb, shadow_rgb, 0.18),
            "bottle_liquid_opacity": 0.5 if material == "transparent_glass" else 0.35,
            "bottle_liquid_roughness": 0.28 if material == "transparent_glass" else 0.48,
            "bottle_liquid_level": 0.68,
        })

    return fields


def cv_measure(mask: np.ndarray, color_img: np.ndarray,
               total_height_mm: float, body_od_mm: float = 0) -> dict:
    """
    多轮廓协作 CV 测量。

    body_od_mm=0 时进入"纯高度校准"模式：用总高做唯一校准源，
    自动推算瓶身直径和口径。

    先验：图中所有物件是同一产品，区别在于完整装配 vs 单独组件。
    策略：
      1. 分类所有轮廓 (assembly / standalone_bottle / open_cap)
      2. 用 assembly 轮廓测 cap/bottle 比例和锥度
      3. 如果有 standalone_bottle → 用其宽度交叉校准 px_per_mm
      4. 双校准融合（宽度法+高度法）保持兼容

    返回字典与原版兼容，新增 calibration_source / classified_contours。
    """
    contours = _find_largest_contour(mask)
    if not contours:
        return {"error": "no_contour"}

    # ── 1. 分类每个轮廓（最多前 5 个） ──
    classified = []
    for i, c in enumerate(contours[:5]):
        cls = _classify_contour(mask, color_img, c)
        cls["contour_idx"] = i
        cls["area"] = int(cv2.contourArea(c))
        classified.append(cls)
        print(f"  [分类] 轮廓#{i}: {cls['type']} "
              f"(conf={cls['confidence']:.2f}, S={cls.get('s_upper',0):.0f}/{cls.get('s_lower',0):.0f}, "
              f"面积={cls['area']}px²)")

    # ── 2. 选择角色 ──
    assembly = None
    bottle_ref = None
    cap_ref = None
    for c in classified:
        if c["type"] == "assembly" and assembly is None:
            assembly = c
        if c["type"] == "standalone_bottle" and bottle_ref is None:
            bottle_ref = c
        if c["type"] == "open_cap" and cap_ref is None:
            cap_ref = c

    # 面积验证：组装产品（盖+瓶）既宽又高，面积应是最大的。
    # 盖瓶同色（全黑等）时 HSV 分类会误判，用面积纠正。
    # （高度不可靠——刷杆+刷头可能比组装产品还高）
    if len(classified) > 1:
        largest = classified[0]  # 按面积降序排列，[0]是最大
        if assembly is not None and largest is not assembly:
            if largest["area"] > assembly["area"] * 1.5:
                old_asm = assembly
                assembly = largest
                # 重新选择 bottle_ref：剩余轮廓中面积最大的
                # （不能用被降级的旧 assembly，它可能是刷杆而非独立瓶身）
                bottle_ref = None
                for c in classified:
                    if c is assembly or c is cap_ref:
                        continue
                    if bottle_ref is None or c["area"] > bottle_ref["area"]:
                        bottle_ref = c
                print(f"  [面积校正] 轮廓#{largest['contour_idx']}"
                      f"(面积={largest['area']}px²) 比 "
                      f"assembly#{old_asm['contour_idx']}"
                      f"({old_asm['area']}px²) 大>50%, "
                      f"重新分配为 assembly")
                if bottle_ref:
                    print(f"  [角色重选] bottle_ref → 轮廓#{bottle_ref['contour_idx']}"
                          f"(面积={bottle_ref['area']}px²)")

    # Fallback: 没有明确装配体 → 最大轮廓
    if assembly is None:
        assembly = classified[0]

    # ── 3. 测量装配体轮廓 ──
    asm_idx = assembly["contour_idx"]
    asm_meas = _measure_single_contour(mask, color_img, contours[asm_idx])
    if "error" in asm_meas:
        return asm_meas

    # ── 4. 校准 ──
    # 主校准源：总高（唯一用户锚定值）
    px_per_mm_h = asm_meas["total_height_px"] / total_height_mm
    px_per_mm = px_per_mm_h
    cal_source = "height"
    ref_meas = None

    # 宽度校准（可选，body_od_mm > 0 时启用作为辅助参考）
    px_per_mm_w = None
    if body_od_mm > 0:
        if bottle_ref is not None:
            ref_idx = bottle_ref["contour_idx"]
            ref_meas = _measure_single_contour(mask, color_img, contours[ref_idx])
            if "error" not in ref_meas and ref_meas["max_width_px"] > 10:
                px_per_mm_w = ref_meas["max_width_px"] / body_od_mm
                cal_source = f"height+standalone#{ref_idx}"
        if px_per_mm_w is None and asm_meas["bottle_max_w_px"] > 10:
            px_per_mm_w = asm_meas["bottle_max_w_px"] / body_od_mm
            cal_source = "height+assembly_width"
    else:
        # 无 body_od → 仅需独立 bottle 轮廓提取（用高度校准做 px→mm）
        if bottle_ref is not None:
            ref_idx = bottle_ref["contour_idx"]
            ref_meas = _measure_single_contour(mask, color_img, contours[ref_idx])

    # ── 4b. 独立 bottle 颈部特征提取 ──
    bottle_profile = None
    if bottle_ref is not None and ref_meas is not None and "error" not in ref_meas:
        bottle_profile = _measure_bottle_profile(ref_meas)

    # ── 5. 高度换算 ──
    # 主路径：高度校准（总高是唯一锚定尺寸）
    cap_h_mm = asm_meas["cap_height_px"] / px_per_mm_h
    bottle_h_mm = asm_meas["bottle_height_px"] / px_per_mm_h

    # 宽度辅助：如果有宽度校准，做双源融合（仅当提供了 body_od 时）
    if px_per_mm_w and px_per_mm_w > 0:
        cap_h_width = asm_meas["cap_height_px"] / px_per_mm_w
        cap_h_height = cap_h_mm

        mask_total_mm = asm_meas["total_height_px"] / px_per_mm_w
        truncation_ratio = min(1.0, mask_total_mm / total_height_mm)
        k = 2.0 if "standalone" in cal_source else 3.0
        alpha = max(0.0, min(1.0, (1.0 - truncation_ratio) * k))

        cap_h_mm = cap_h_width * (1 - alpha) + cap_h_height * alpha
        bottle_h_mm = total_height_mm - cap_h_mm

        print(f"  [校准] 源={cal_source}, 宽度法={cap_h_width:.1f}mm, "
              f"高度法={cap_h_height:.1f}mm, α={alpha:.2f} → cap={cap_h_mm:.1f}mm")
    else:
        print(f"  [校准] 源={cal_source}, px/mm={px_per_mm_h:.2f}, "
              f"cap={cap_h_mm:.1f}mm, bottle={bottle_h_mm:.1f}mm")

    # ── 5a. 独立瓶身轮廓反推盖高（比颜色法更可靠） ──
    # 颜色法对透明瓶身+有色盖容易误判，独立瓶身轮廓的上下边界不受颜色干扰
    standalone_bottle_h_mm = 0.0  # 独立瓶身实测高度（供建模用）
    if ref_meas is not None and "error" not in ref_meas:
        standalone_h_px = ref_meas.get("total_height_px", 0)
        if standalone_h_px > 30:
            standalone_h_mm = standalone_h_px / px_per_mm_h
            standalone_bottle_h_mm = round(standalone_h_mm, 1)
            new_cap_h = total_height_mm - standalone_h_mm
            if 3 < new_cap_h < total_height_mm * 0.7:
                old_cap_h = cap_h_mm
                cap_h_mm = new_cap_h
                bottle_h_mm = total_height_mm - cap_h_mm
                print(f"  [独立瓶身反推] 盖高: {old_cap_h:.1f}mm → {cap_h_mm:.1f}mm "
                      f"(总高{total_height_mm} - 瓶身{standalone_h_mm:.1f}mm)")

    # ── 5a2. 打开的盖轮廓直接测盖高（最可靠） ──
    # 从 open_cap 轮廓中提取盖体高度（排除刷杆），优先级高于独立瓶身反推
    if cap_ref is not None:
        cap_idx = cap_ref["contour_idx"]
        cap_meas = _measure_single_contour(mask, color_img, contours[cap_idx])
        if "error" not in cap_meas:
            cwp = cap_meas["_width_profile"]
            cy_top, cy_bot = cap_meas["_y_top"], cap_meas["_y_bot"]
            c_total_h = cy_bot - cy_top
            if c_total_h > 20:
                c_seg = max(3, c_total_h // 8)
                c_top_w = float(np.median(cwp[cy_top:cy_top + c_seg]))
                c_bot_w = float(np.median(cwp[cy_bot - c_seg:cy_bot]))
                # 宽端 = 盖体，窄端 = 刷杆
                cap_at_bottom = c_bot_w > c_top_w
                if cap_at_bottom:
                    profile = cwp[cy_top:cy_bot + 1][::-1].copy()
                else:
                    profile = cwp[cy_top:cy_bot + 1].copy()
                max_w = float(profile.max())
                if max_w > 10:
                    # 从最宽处往刷杆方向找宽度骤降点（兼容锥形盖：尖端本身也窄）
                    max_idx = int(np.argmax(profile))
                    cap_body_end = len(profile)
                    for i in range(max_idx, len(profile)):
                        if profile[i] < max_w * 0.3:
                            cap_body_end = i
                            break
                    cap_h_from_open = cap_body_end / px_per_mm_h
                    if 3 < cap_h_from_open < total_height_mm * 0.8:
                        old_cap_h = cap_h_mm
                        cap_h_mm = cap_h_from_open
                        bottle_h_mm = total_height_mm - cap_h_mm
                        print(f"  [打开盖轮廓] 盖高: {old_cap_h:.1f}mm → {cap_h_mm:.1f}mm "
                              f"(盖体{cap_body_end}px / {px_per_mm_h:.2f}px/mm)")

    # ── 5b. 从底部宽度比例推算瓶身底径 ──
    # 用底部宽度（更稳定）而非 max_width（可能受 collar/凸环影响）
    bottom_w_px = asm_meas.get("bottom_w_px", asm_meas["bottle_max_w_px"])
    derived_body_od = round(bottom_w_px / px_per_mm_h, 1)
    print(f"  [推算] body_od={derived_body_od:.1f}mm "
          f"(底部宽度比={bottom_w_px:.0f}px/{asm_meas['total_height_px']}px)")

    # ── 5c. 独立 bottle 轮廓交叉校验 ──
    # 独立 bottle 有自己的高度像素 → 可独立计算 px_per_mm → 得到第二个 body_od 估计
    # 当装配体轮廓因倾斜/透视失真时, 独立 bottle 可能位于不同角度, 提供修正
    if bottle_profile and ref_meas and "error" not in ref_meas:
        standalone_h_px = ref_meas.get("total_height_px", 0)
        standalone_w_px = bottle_profile.get("body_od_px", 0)
        if standalone_h_px > 30 and standalone_w_px > 10:
            # 独立 bottle 的 mm 高度: 从装配体 cap_ratio 推算
            visible_bottle_mm = total_height_mm * (1 - asm_meas["cap_ratio"])
            # 独立 bottle 展示全瓶身(含颈), 实际 h ≈ visible / 0.86
            est_bottle_mm = max(30, visible_bottle_mm / 0.86)
            standalone_px_per_mm = standalone_h_px / est_bottle_mm
            standalone_body_od = round(standalone_w_px / standalone_px_per_mm, 1)

            asm_od = derived_body_od
            deviation = abs(asm_od - standalone_body_od) / max(asm_od, standalone_body_od, 1)
            if deviation < 0.15:
                # 两源一致 → 取平均
                derived_body_od = round((asm_od + standalone_body_od) / 2, 1)
                print(f"  [交叉校验] 装配体={asm_od:.1f}mm, 独立瓶={standalone_body_od:.1f}mm "
                      f"(偏差{deviation:.0%}) → 平均={derived_body_od:.1f}mm")
            else:
                # 不一致 → 偏向较小值(宽度被高估的概率远大于低估)
                derived_body_od = round(min(asm_od, standalone_body_od), 1)
                print(f"  [交叉校验] 不一致: 装配体={asm_od:.1f}mm, 独立瓶={standalone_body_od:.1f}mm "
                      f"(偏差{deviation:.0%}) → 选较小值={derived_body_od:.1f}mm")

    # ── 5d. 方形瓶投影宽度修正 ──
    # 方形/多边形瓶拍摄有角度时，投影宽度 > 真实棱长。
    # 用 Sobel 竖向边缘检测找到瓶身上的棱线，还原实际棱长。
    # 圆形瓶无内部棱线 → 自动跳过，不影响。
    _corr_contour = (contours[bottle_ref["contour_idx"]]
                     if bottle_ref else contours[asm_idx])
    polygon_corr, edge_rel = _detect_square_rotation_correction(
        color_img, _corr_contour)
    if polygon_corr < 0.99:
        old_od = derived_body_od
        derived_body_od = round(derived_body_od * polygon_corr, 1)
        _angle = round(math.degrees(math.atan((1 - edge_rel) / edge_rel)), 1) \
            if 0.01 < edge_rel < 0.99 else 0
        print(f"  [方形修正] 棱线位置={edge_rel:.0%}, 旋转≈{_angle}°, "
              f"系数={polygon_corr:.3f}, "
              f"{old_od:.1f}mm → {derived_body_od:.1f}mm")
        # 同步修正独立瓶身轮廓的像素宽度（下一步 mm 换算会用到）
        if bottle_profile:
            bottle_profile["body_od_px"] = round(
                bottle_profile["body_od_px"] * polygon_corr, 1)

    # ── 6. Bottle profile mm 换算 + 透明瓶修正 ──
    # 统一用高度校准 px_per_mm_h（不依赖 body_od 输入）
    if bottle_profile and px_per_mm_h > 0:
        bottle_profile["neck_od_mm"] = round(bottle_profile["neck_od_px"] / px_per_mm_h, 1)
        bottle_profile["neck_height_mm"] = round(bottle_profile["neck_height_px"] / px_per_mm_h, 1)
        bottle_profile["shoulder_height_mm"] = round(
            bottle_profile["shoulder_height_px"] / px_per_mm_h, 1)
        bottle_profile["body_od_mm"] = round(bottle_profile["body_od_px"] / px_per_mm_h, 1)
        bottle_profile["neck_od_source"] = "mask"

        print(f"  [Bottle Profile] neck_od={bottle_profile['neck_od_mm']:.1f}mm "
              f"(src={bottle_profile['neck_od_source']}), "
              f"neck_h={bottle_profile['neck_height_mm']:.1f}mm, "
              f"shoulder_h={bottle_profile['shoulder_height_mm']:.1f}mm, "
              f"neck/body={bottle_profile['neck_body_ratio']:.3f}")

    cap_od_ratio = (asm_meas["cap_bottom_w_px"] / asm_meas["bottle_max_w_px"]
                    if asm_meas["bottle_max_w_px"] > 0 else 1.0)

    # ── 7. 高宽比交叉验证 ──
    aspect_check = {
        "measured_body_od_mm": derived_body_od,
        "user_body_od_mm": body_od_mm if body_od_mm > 0 else derived_body_od,
        "deviation_pct": 0,
    }
    if body_od_mm > 0:
        deviation = abs(derived_body_od - body_od_mm) / body_od_mm
        aspect_check["deviation_pct"] = round(deviation * 100, 1)
        if deviation > 0.1:
            print(f"  [高宽比] 图像推导={derived_body_od:.1f}mm vs 输入={body_od_mm:.1f}mm, "
                  f"偏差={deviation:.0%} → 采用图像推导值")

    # ── 8. 装饰带检测 (collar / base_ring) ──
    deco_bands = {"collar": {"detected": False}, "base_ring": {"detected": False}}
    effective_px_per_mm = px_per_mm_h
    if effective_px_per_mm > 0:
        deco_bands = _detect_decorative_bands(
            color_img, asm_meas["_M"], asm_meas["_new_size"],
            asm_meas["_binary"], asm_meas["_width_profile"],
            asm_meas["_y_top"], asm_meas["_boundary_y"], asm_meas["_y_bot"],
            effective_px_per_mm,
        )
        col = deco_bands["collar"]
        br = deco_bands["base_ring"]
        if col["detected"]:
            print(f"  [装饰带] collar: {col['height_mm']:.1f}mm "
                  f"(密度比={col.get('density_ratio', 0):.1f}), "
                  f"宽余={col['width_excess_mm']:.1f}mm, conf={col['confidence']:.2f}")
            # ── 修正 cap 高度：collar 不应计入 cap ──
            if col.get("corrected_cap_height_px") and effective_px_per_mm > 0:
                corrected_cap_px = col["corrected_cap_height_px"]
                corrected_cap_mm = corrected_cap_px / effective_px_per_mm
                old_cap_mm = cap_h_mm
                cap_h_mm = corrected_cap_mm
                bottle_h_mm = total_height_mm - cap_h_mm
                print(f"  [修正] cap 高度: {old_cap_mm:.1f}mm → {cap_h_mm:.1f}mm "
                      f"(扣除 collar {col['height_mm']:.1f}mm)")
        if br["detected"]:
            print(f"  [装饰带] base_ring: {br['height_mm']:.1f}mm, "
                  f"宽余={br['width_excess_mm']:.1f}mm, conf={br['confidence']:.2f}")

    # ── 9. 从图像推算口径（无独立瓶身轮廓时的回退） ──
    derived_neck_od = 0
    if bottle_profile and bottle_profile.get("neck_od_mm", 0) > 0:
        derived_neck_od = bottle_profile["neck_od_mm"]
    elif asm_meas.get("cap_bottom_w_px", 0) > 0:
        # 从装配体 cap 底部宽度反推：neck_od ≈ cap底宽 - 2*(壁厚+间隙)
        cap_bot_mm = asm_meas["cap_bottom_w_px"] / px_per_mm_h
        derived_neck_od = round(max(8.0, cap_bot_mm - 1.8), 1)
        print(f"  [推算] neck_od={derived_neck_od:.1f}mm (cap底反推)")
    else:
        # 最终回退：body_od * 0.75
        derived_neck_od = round(derived_body_od * 0.75, 1)
        print(f"  [推算] neck_od={derived_neck_od:.1f}mm (body_od * 0.75 回退)")

    result = {
        "cap_taper_deg": asm_meas["cap_taper_deg"],
        "bottle_taper_deg": asm_meas["bottle_taper_deg"],
        "unified_taper_deg": asm_meas.get("unified_taper_deg", 0),
        "cap_ratio": round(cap_h_mm / total_height_mm, 3),
        "cap_height_mm": round(cap_h_mm, 1),
        "bottle_height_mm": round(bottle_h_mm, 1),
        "standalone_bottle_height_mm": standalone_bottle_h_mm,
        "cap_od_ratio": round(cap_od_ratio, 3),
        "derived_body_od_mm": derived_body_od,
        "derived_neck_od_mm": derived_neck_od,
        "polygon_correction": polygon_corr,
        "cap_height_px": asm_meas["cap_height_px"],
        "bottom_w_px": asm_meas.get("bottom_w_px", asm_meas.get("bottle_max_w_px", 0)),
        "boundary_method": asm_meas["boundary_method"],
        "boundary_confidence": asm_meas["boundary_confidence"],
        "calibration_source": cal_source,
        "bottle_profile": bottle_profile,
        "aspect_check": aspect_check,
        "decorative_bands": deco_bands,
        "contour_count": len(contours),
        "classified_contours": [
            {"idx": c["contour_idx"], "type": c["type"],
             "confidence": round(c["confidence"], 2)}
            for c in classified
        ],
        "_binary": asm_meas["_binary"],
        "_width_profile": asm_meas["_width_profile"],
        "_y_top": asm_meas["_y_top"],
        "_y_bot": asm_meas["_y_bot"],
        "_boundary_y": asm_meas["_boundary_y"],
        "_M": asm_meas["_M"],
        "_new_size": asm_meas["_new_size"],
    }

    # 颜色采样（拟真渲染用）
    try:
        pass
    except Exception:
        pass  # 颜色采样失败不影响主流程

    return result


# ════════════════════════════════════════════════════════════════════════
# Stage 3: VLM 定性分类
# ════════════════════════════════════════════════════════════════════════

def vlm_classify(image_path: str, user_dims: dict) -> dict:
    """调用 GLM-4v 进行两步 VLM 提取，返回 vlm_shape dict。
    只提取 CAD 几何/结构信息；材质外观由渲染工作流负责。"""
    from core.vlm_extract import (
        vlm_describe, vlm_extract_shape,
        _call_glm, _make_image_content,
        STEP1A_PROMPT, STEP1B_TEMPLATE,
    )

    # 读取图片为 base64
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    img_content = _make_image_content(b64)

    # ── Step 1A: 几何形态 ──
    # 1B 依赖 1A 的输出，所以不能和 1A 并发
    def _call_1a():
        return _call_glm([{
            "role": "user",
            "content": [img_content, {"type": "text", "text": STEP1A_PROMPT}],
        }])

    print("  [VLM] Step 1A: 识别 CAD 几何形态...")
    t_vlm = time.time()
    geometry_desc = _call_1a()
    print(f"  [VLM] 1A 完成 ({time.time() - t_vlm:.1f}s)")
    print(f"  [VLM] 几何: {geometry_desc[:120]}...")

    # ── Step 1B: 装饰（依赖 1A 结果） ──
    print("  [VLM] Step 1B: AI 识别装饰特征（纹理/装饰带/底座）...")
    step1b_prompt = STEP1B_TEMPLATE.format(
        geometry_description=geometry_desc[:300]
    )
    decoration_desc = _call_glm([{
        "role": "user",
        "content": [img_content, {"type": "text", "text": step1b_prompt}],
    }])
    print(f"  [VLM] 装饰: {decoration_desc[:120]}...")

    # 合并描述
    description = (
        f"【几何形态】\n{geometry_desc}\n\n"
        f"【装饰特征】\n{decoration_desc}"
    )

    # Step 2: 结构化参数提取
    print("  [VLM] Step 2: 提取结构化参数...")
    vlm_shape = vlm_extract_shape(description, user_dims)
    conf = vlm_shape.get("confidence", 0)
    desc = vlm_shape.get("shape_description", "")
    print(f"  [VLM] 置信度={conf}, {desc}")

    return vlm_shape, description


# ════════════════════════════════════════════════════════════════════════
# Stage 4: 合并 CV + VLM → Gallery-ready vlm_shape
# ════════════════════════════════════════════════════════════════════════

def merge_cv_vlm(cv_result: dict, vlm_shape: dict, user_dims: dict,
                  total_height_mm: float = 0) -> dict:
    """
    合并 CV 定量 + VLM 定性 → GALLERY_CATALOG 兼容的 vlm_shape。

    策略:
      - 定量参数 (锥度、比例、宽度): 用 CV 值（更精确）
      - 定性参数 (截面、顶面、肩部): 用 VLM 值（CV 无法从 2D 判断）
      - 冲突仲裁: CV 有高置信度时覆盖 VLM 同类型参数
      - 盖高仲裁: CV 边界置信度低且与 VLM 比例严重偏离时回退到 VLM
    """
    merged = {}

    # ── VLM 定性参数（CV 无法判断） ──
    merged["cross_section"] = vlm_shape.get("cross_section", "round")
    merged["corner_radius_mm"] = vlm_shape.get("corner_radius_mm", 3.0)
    merged["cap_top_shape"] = vlm_shape.get("cap_top_shape", "flat")
    merged["cap_grip_style"] = vlm_shape.get("cap_grip_style", "smooth")
    merged["shoulder_style"] = vlm_shape.get("shoulder_style", "round")
    merged["shoulder_fillet_mm"] = vlm_shape.get("shoulder_fillet_mm", 3.0)
    merged["bottom_style"] = vlm_shape.get("bottom_style", "flat")
    merged["bottom_fillet_mm"] = vlm_shape.get("bottom_fillet_mm", 1.0)
    merged["profile_mode"] = vlm_shape.get("profile_mode", "classic")
    merged["profile_points"] = vlm_shape.get("profile_points", [])
    # 装饰特征（VLM 定性 + CV 定量覆盖）
    merged["bottle_collar_style"] = vlm_shape.get("bottle_collar_style", "none")
    merged["bottle_collar_height_ratio"] = vlm_shape.get("bottle_collar_height_ratio", 0)
    merged["bottle_base_ring"] = vlm_shape.get("bottle_base_ring", False)

    deco = cv_result.get("decorative_bands", {})
    cv_collar = deco.get("collar", {})
    cv_base = deco.get("base_ring", {})

    # CV 检测到 collar → 用 CV 精确值覆盖 VLM 粗估
    if cv_collar.get("detected") and cv_collar.get("confidence", 0) > 0.3:
        merged["bottle_collar_height_mm"] = cv_collar["height_mm"]
        merged["bottle_collar_width_excess_mm"] = cv_collar.get("width_excess_mm", 0.5)
        # 如果 VLM 未检测到 collar，用 CV 结果补全
        if merged["bottle_collar_style"] == "none":
            merged["bottle_collar_style"] = "smooth_band"
        bottle_h = cv_result.get("bottle_height_mm", 70)
        if bottle_h > 0:
            merged["bottle_collar_height_ratio"] = round(
                cv_collar["height_mm"] / bottle_h, 3)
        print(f"  [CV→merge] collar: {cv_collar['height_mm']:.1f}mm, "
              f"宽余={cv_collar.get('width_excess_mm', 0):.1f}mm "
              f"(conf={cv_collar['confidence']:.2f})")

    # CV 检测到 base_ring → 用 CV 精确值
    if cv_base.get("detected") and cv_base.get("confidence", 0) > 0.2:
        merged["bottle_base_ring"] = True
        merged["bottle_base_ring_height_mm"] = cv_base["height_mm"]
        merged["bottle_base_ring_width_excess_mm"] = cv_base["width_excess_mm"]
        print(f"  [CV→merge] base_ring: {cv_base['height_mm']:.1f}mm, "
              f"宽余={cv_base['width_excess_mm']:.1f}mm "
              f"(conf={cv_base['confidence']:.2f})")

    # ── CV 定量参数 ──
    # ★ 统一锥度：直接用整件轮廓的锥度，不分 cap/bottle
    unified_taper = cv_result.get("unified_taper_deg", 0)
    vlm_shape_type = vlm_shape.get("shape", "cyl")
    vlm_taper = vlm_shape.get("taper_deg", 0)

    # 仲裁: CV 极端锥度（>8°）且 VLM 判定直筒 → 疑似 CV 误检，回退到 VLM
    # （常见于方形瓶、小瓶等 CV 轮廓测量不准的场景）
    # 注意：中小锥度仍信任 CV（如 A3 cairui cone 的 5.5° 是正确的）
    if vlm_shape_type == "cyl" and vlm_taper < 0.5 and unified_taper > 8:
        print(f"  [CV→merge] 仲裁: CV锥度={unified_taper:.1f}°(>8°) 但VLM判定直筒 → 采用VLM(cyl)")
        merged["taper_deg"] = 0
        merged["cap_taper_deg"] = 0
        merged["shape"] = "cyl"
        merged["cap_od_base"] = vlm_shape.get("cap_od_base", "body")
    elif unified_taper > 0.5:
        merged["taper_deg"] = round(unified_taper, 1)
        merged["cap_taper_deg"] = round(unified_taper, 1)
        merged["shape"] = "taper"
        merged["cap_od_base"] = "body_top"
        print(f"  [CV→merge] 统一锥度={unified_taper:.1f}° (整件轮廓)")
    else:
        merged["taper_deg"] = 0
        merged["cap_taper_deg"] = 0
        merged["shape"] = "cyl"
        merged["cap_od_base"] = vlm_shape.get("cap_od_base", "body")

    # ★ cap 高度：CV cap_ratio × total_height，但需与 VLM 比例仲裁
    cv_cap_h = cv_result.get("cap_height_mm", 0)
    cv_confidence = cv_result.get("boundary_confidence", 0)
    cv_cap_ratio = cv_result.get("cap_ratio", 0)
    vlm_cap_ratio = vlm_shape.get("cap_height_ratio", 0)

    # 推算 total_height（如果未传入）
    _total_h = total_height_mm
    if _total_h <= 0 and cv_cap_ratio > 0.05 and cv_cap_h > 0:
        _total_h = cv_cap_h / cv_cap_ratio

    # 仲裁：CV 与 VLM 盖高比例偏离 → 回退 VLM
    # ★ 不再要求 CV 置信度低——掩码截断时边界检测置信度仍然很高，
    #   但比例计算已经因为掩码不完整而失真
    use_vlm_cap_h = False
    if vlm_cap_ratio > 0.05 and _total_h > 0:
        ratio_diff = abs(cv_cap_ratio - vlm_cap_ratio)
        if ratio_diff > 0.12:
            vlm_cap_h = round(_total_h * vlm_cap_ratio, 1)
            print(f"  [CV→merge] 仲裁: CV盖比={cv_cap_ratio:.3f} 与"
                  f"VLM盖比={vlm_cap_ratio:.3f} 差异={ratio_diff:.3f}(>0.12) "
                  f"→ 采用VLM盖高={vlm_cap_h:.1f}mm "
                  f"(CV置信度={cv_confidence:.2f}, 但掩码可能截断)")
            merged["cap_height_mm"] = vlm_cap_h
            use_vlm_cap_h = True
    if not use_vlm_cap_h and cv_cap_h > 5:
        merged["cap_height_mm"] = cv_cap_h
        print(f"  [CV→merge] cap_height={cv_cap_h:.1f}mm "
              f"(cap_ratio={cv_cap_ratio:.3f}, conf={cv_confidence:.2f})")

    # cap OD ratio
    cv_od_ratio = cv_result.get("cap_od_ratio", 1.0)
    if abs(cv_od_ratio - 1.0) < 0.05:
        merged["cap_od_ratio"] = 1.0
    else:
        merged["cap_od_ratio"] = round(cv_od_ratio, 2)

    # ── CV bottle_profile 精确测量（颈高、肩高） ──
    bp = cv_result.get("bottle_profile") or {}
    if bp.get("neck_height_mm", 0) > 0:
        merged["bottle_neck_height_mm"] = bp["neck_height_mm"]
        print(f"  [CV→merge] neck_height={bp['neck_height_mm']:.1f}mm (mask)")
    if bp.get("shoulder_height_mm", 0) > 0:
        merged["bottle_shoulder_height_mm"] = bp["shoulder_height_mm"]
        print(f"  [CV→merge] shoulder_height={bp['shoulder_height_mm']:.1f}mm (mask)")

    # VLM 定性比例（作为 CV 无法检测时的回退）
    merged["bottle_neck_height_ratio"] = vlm_shape.get("bottle_neck_height_ratio", 0.15)
    merged["bottle_shoulder_height_ratio"] = vlm_shape.get("bottle_shoulder_height_ratio", 0.08)

    # 肩高：CV 精确 > VLM ratio > 默认
    if bp.get("shoulder_height_mm", 0) > 0:
        merged["shoulder_height_mm"] = bp["shoulder_height_mm"]
    else:
        merged["shoulder_height_mm"] = vlm_shape.get("shoulder_height_mm", 0)

    # 多边形截面需要最小肩高来完成多边形→圆形过渡 loft
    cs = merged.get("cross_section", "round")
    if cs != "round" and merged["shoulder_height_mm"] < 1.0:
        merged["shoulder_height_mm"] = 1.0
        merged["bottle_shoulder_height_mm"] = 1.0
        print(f"  [CV→merge] 多边形截面({cs})最小肩高→1.0mm")

    # ── 固定参数（内置杆子等） ──
    # 从 VLM 继承 stem/brush 信息（如果有）
    if vlm_shape.get("cap_stem_enabled"):
        merged["cap_stem_enabled"] = True
        merged["cap_stem_diameter_mm"] = vlm_shape.get("cap_stem_diameter_mm", 4.25)
        merged["cap_brush_type"] = vlm_shape.get("cap_brush_type", "doe_foot")

    merged["confidence"] = 1.0
    return merged

# ════════════════════════════════════════════════════════════════════════
# 调试可视化
# ════════════════════════════════════════════════════════════════════════

def save_debug(name: str, color_img, cv_result: dict, merged: dict):
    """保存调试标注图"""
    binary = cv_result.get("_binary")
    if binary is None:
        return
    M = cv_result["_M"]
    new_size = cv_result["_new_size"]
    y_top = cv_result["_y_top"]
    y_bot = cv_result["_y_bot"]
    boundary_y = cv_result["_boundary_y"]
    width_profile = cv_result["_width_profile"]

    # 旋转原图
    rotated_color = cv2.warpAffine(color_img, M, new_size, flags=cv2.INTER_LINEAR)
    mask_3ch = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    vis = cv2.bitwise_and(rotated_color, mask_3ch)

    h, w = binary.shape
    # 边界线
    cv2.line(vis, (0, boundary_y), (w, boundary_y), (0, 0, 255), 2)
    cv2.line(vis, (0, y_top), (w, y_top), (0, 255, 0), 1)
    cv2.line(vis, (0, y_bot), (w, y_bot), (0, 255, 0), 1)

    font = cv2.FONT_HERSHEY_SIMPLEX
    cap_mid = (y_top + boundary_y) // 2
    bot_mid = (boundary_y + y_bot) // 2

    cap_r = cv_result.get("cap_ratio", 0)
    cv2.putText(vis, f"Cap: {cap_r:.1%}", (10, cap_mid), font, 0.6, (0, 255, 255), 2)
    cv2.putText(vis, f"Taper: {cv_result.get('cap_taper_deg', 0):.1f}deg",
                (10, cap_mid + 25), font, 0.5, (0, 255, 255), 1)
    if "cap_height_mm" in cv_result:
        cv2.putText(vis, f"{cv_result['cap_height_mm']:.1f}mm",
                    (10, cap_mid - 20), font, 0.5, (0, 255, 255), 1)

    cv2.putText(vis, f"Bottle: {1 - cap_r:.1%}", (10, bot_mid), font, 0.6, (255, 255, 0), 2)
    cv2.putText(vis, f"Taper: {cv_result.get('bottle_taper_deg', 0):.1f}deg",
                (10, bot_mid + 25), font, 0.5, (255, 255, 0), 1)

    # 宽度剖面
    max_wp = width_profile.max()
    if max_wp > 0:
        scale = min(200, w // 3) / max_wp
        for y in range(y_top, y_bot + 1):
            pw = int(width_profile[y] * scale)
            if pw > 0:
                c = (0, 200, 200) if y < boundary_y else (200, 200, 0)
                cv2.line(vis, (w - pw - 5, y), (w - 5, y), c, 1)

    # 右上角显示合并后参数 + 多轮廓分类信息
    contour_count = cv_result.get("contour_count", 1)
    cal_src = cv_result.get("calibration_source", "?")
    contour_info = f"Contours: {contour_count}"
    classified = cv_result.get("classified_contours", [])
    if classified:
        types = ", ".join(f"#{c['idx']}={c['type']}" for c in classified[:3])
        contour_info += f" [{types}]"

    bp = cv_result.get("bottle_profile")
    bp_line = "Bottle Profile: N/A"
    if bp and bp.get("neck_od_mm"):
        bp_line = (f"Bottle Profile: neck={bp['neck_od_mm']:.1f}mm, "
                   f"neck_h={bp.get('neck_height_mm', 0):.1f}mm, "
                   f"sh_h={bp.get('shoulder_height_mm', 0):.1f}mm")

    info_lines = [
        contour_info,
        f"Calibration: {cal_src}",
        f"Method: {cv_result.get('boundary_method', '?')}",
        f"CV cap_taper: {cv_result.get('cap_taper_deg', 0):.1f}deg",
        bp_line,
        f"Merged shape: {merged.get('shape', '?')}",
        f"Merged cross: {merged.get('cross_section', '?')}",
    ]
    for i, line in enumerate(info_lines):
        cv2.putText(vis, line, (w - 280, 25 + i * 22), font, 0.45, (200, 200, 200), 1)

    out_path = OUT_DIR / f"{name}_debug.png"
    cv2.imwrite(str(out_path), vis)
    print(f"  [调试图] {out_path}")


# ════════════════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════════════════

def run_pipeline(
    image_path: str,
    total_height_mm: float,
    body_od_mm: float = 0,
    neck_od_mm: float = 0,
    skip_vlm: bool = False,
    vlm_cache_id: str = "",
    progress_cb=None,
) -> dict:
    """
    执行完整 Pipeline: BiRefNet → CV → VLM → Merge

    body_od_mm / neck_od_mm = 0 时，由 CV 从图像高宽比自动推算。
    用户只需提供 total_height_mm（唯一锚定尺寸）。

    Returns: {
        "user_dims": {...},
        "vlm_shape": {...},       # Gallery-ready
        "cv_detail": {...},       # CV 原始测量
        "vlm_raw": {...},         # VLM 原始输出
        "gallery_entry": {...},   # 可直接插入 GALLERY_CATALOG
    }
    """
    name = Path(image_path).stem

    print(f"\n{'=' * 60}")
    print(f"自动化 Pipeline: {name}")
    if body_od_mm > 0:
        print(f"锚定尺寸: 总高={total_height_mm}mm, 外径={body_od_mm}mm, 颈径={neck_od_mm}mm")
    else:
        print(f"锚定尺寸: 总高={total_height_mm}mm (直径/口径由 CV 自动推算)")
    print(f"{'=' * 60}")

    t0 = time.time()

    # ── 构建 user_dims（CV 推算后会补全 body_od / neck_od） ──
    user_dims = {"height_mm": total_height_mm}
    if body_od_mm > 0:
        user_dims["body_od_mm"] = body_od_mm
    if neck_od_mm > 0:
        user_dims["neck_od_mm"] = neck_od_mm

    def _prog(msg, pct=0):
        if progress_cb:
            progress_cb(msg, pct)

    # ── 预加载彩色图（BiRefNet 补充分割和 CV 测量共用） ──
    color_img = cv2.imread(str(image_path))
    if color_img is None:
        # webp support
        buf = np.fromfile(str(image_path), dtype=np.uint8)
        color_img = cv2.imdecode(buf, cv2.IMREAD_COLOR)

    # ── Stage 1: BiRefNet ──
    print("\n[Stage 1] BiRefNet 背景剔除")
    _prog("BiRefNet 背景剔除...", 2)
    mask = birefnet_mask(image_path, color_img=color_img)
    _prog("BiRefNet 完成", 5)

    # ── Stage 2: CV 测量 ──
    print("\n[Stage 2] CV 定量测量")
    _prog("CV 轮廓分析...", 6)
    cv_result = cv_measure(mask, color_img, total_height_mm,
                           body_od_mm if body_od_mm > 0 else 0)

    if "error" in cv_result:
        print(f"  [CV] 错误: {cv_result['error']}")
        return {"error": cv_result["error"]}

    print(f"  [CV] 轮廓数: {cv_result.get('contour_count', 1)}, "
          f"校准源: {cv_result.get('calibration_source', '?')}")
    print(f"  [CV] cap 锥度: {cv_result['cap_taper_deg']:.2f}°")
    print(f"  [CV] bottle 锥度: {cv_result['bottle_taper_deg']:.2f}°")
    print(f"  [CV] cap 比例: {cv_result['cap_ratio']:.1%}")
    print(f"  [CV] cap 高度: {cv_result['cap_height_mm']:.1f}mm")
    print(f"  [CV] bottle 高度: {cv_result['bottle_height_mm']:.1f}mm")
    print(f"  [CV] cap OD 比: {cv_result['cap_od_ratio']:.3f}")
    print(f"  [CV] 边界方法: {cv_result['boundary_method']} (置信度={cv_result['boundary_confidence']:.2f})")

    # ── 用 CV 推算值补全 user_dims ──
    cv_body_od = cv_result.get("derived_body_od_mm", 0)
    cv_neck_od = cv_result.get("derived_neck_od_mm", 0)
    if cv_body_od > 0:
        print(f"  [CV] 推算 body_od: {cv_body_od:.1f}mm")
    if cv_neck_od > 0:
        print(f"  [CV] 推算 neck_od: {cv_neck_od:.1f}mm")

    # 确定最终使用的 body_od / neck_od（CV 优先，前端滑条值兜底）
    effective_body_od = cv_body_od if cv_body_od > 0 else body_od_mm
    effective_neck_od = cv_neck_od if cv_neck_od > 0 else neck_od_mm

    # 零值兜底：CV 无结果 + 前端也没给值 → 比例回退
    if effective_body_od <= 0:
        effective_body_od = round(total_height_mm * 0.22, 1)
        print(f"  [回退] body_od: {effective_body_od:.1f}mm (CV无结果, 总高*0.22)")
    if effective_neck_od <= 0:
        effective_neck_od = round(effective_body_od * 0.75, 1)
        print(f"  [回退] neck_od: {effective_neck_od:.1f}mm (CV无结果, body_od*0.75)")

    # 安全下限：确保不低于各组件 ParamDef 最小值（bottle.body_od>=12, neck>=10）
    _MIN_BODY_OD = 12.0
    _MIN_NECK_OD = 10.0
    if effective_body_od < _MIN_BODY_OD:
        print(f"  [安全下限] body_od: {effective_body_od:.1f}mm → {_MIN_BODY_OD}mm")
        effective_body_od = _MIN_BODY_OD
    if effective_neck_od < _MIN_NECK_OD:
        print(f"  [安全下限] neck_od: {effective_neck_od:.1f}mm → {_MIN_NECK_OD}mm")
        effective_neck_od = _MIN_NECK_OD
    # 物理约束：口径必须 < 外径
    if effective_neck_od >= effective_body_od:
        effective_neck_od = round(effective_body_od * 0.75, 1)
        effective_neck_od = max(_MIN_NECK_OD, effective_neck_od)
        print(f"  [安全下限] neck_od 缩减至: {effective_neck_od:.1f}mm (需 < body_od)")

    # 补全 user_dims 供后续 VLM / merge 使用
    user_dims["body_od_mm"] = effective_body_od
    user_dims["neck_od_mm"] = effective_neck_od

    # ── Stage 3: VLM 分类 ──
    _prog("CV 完成, AI 视觉识别中...", 7)
    vlm_shape_raw = {}
    vlm_desc = ""
    if not skip_vlm:
        print("\n[Stage 3] VLM 定性分类 (GLM-4v)")
        try:
            vlm_shape_raw, vlm_desc = vlm_classify(image_path, user_dims)
            print(f"  [VLM] cross_section: {vlm_shape_raw.get('cross_section')}")
            print(f"  [VLM] cap_top_shape: {vlm_shape_raw.get('cap_top_shape')}")
            print(f"  [VLM] shoulder_style: {vlm_shape_raw.get('shoulder_style')}")
            print(f"  [VLM] shape: {vlm_shape_raw.get('shape')}")
        except Exception as e:
            print(f"  [VLM] 错误: {e}")
            print("  [VLM] 使用默认定性参数")
            vlm_shape_raw = {
                "cross_section": "octagon", "corner_radius_mm": 0.8,
                "cap_top_shape": "flat", "cap_grip_style": "smooth",
                "shoulder_style": "angular", "shoulder_fillet_mm": 0.5,
                "bottom_style": "flat",
            }
    else:
        print("\n[Stage 3] VLM 跳过 (--skip-vlm)")
        # 优先从 VLM 缓存加载
        vlm_shape_raw = {}
        vlm_cache_dir = Path(__file__).resolve().parent.parent / "artifacts" / "vlm_cache"
        if vlm_cache_id:
            cache_file = vlm_cache_dir / f"{vlm_cache_id}.json"
            if cache_file.exists():
                try:
                    cached = json.loads(cache_file.read_text("utf-8"))
                    vlm_shape_raw = cached.get("vlm_raw", {})
                    vlm_desc = cached.get("vlm_description", "")
                    print(f"  [VLM缓存] 已加载 {vlm_cache_id}")
                except Exception as e:
                    print(f"  [VLM缓存] 加载失败: {e}")
        if not vlm_shape_raw:
            vlm_shape_raw = {
                "cross_section": "round", "corner_radius_mm": 0.0,
                "cap_top_shape": "flat", "cap_grip_style": "smooth",
                "shoulder_style": "round", "shoulder_fillet_mm": 2.5,
                "bottom_style": "flat",
            }
            print("  [VLM] 使用默认定性参数")

    # ── Stage 4: 合并 ──
    _prog("合并 CV + VLM 参数...", 12)
    print("\n[Stage 4] 合并 CV + VLM")
    # 补充 VLM 中的 stem/brush 信息（A3 产品已知有内置杆子）
    if "cap_stem_enabled" not in vlm_shape_raw:
        vlm_shape_raw["cap_stem_enabled"] = True
        vlm_shape_raw["cap_stem_diameter_mm"] = 4.25
        vlm_shape_raw["cap_brush_type"] = "doe_foot"

    merged = merge_cv_vlm(cv_result, vlm_shape_raw, user_dims,
                          total_height_mm=total_height_mm)

    # ── 掩码截断修正：当 VLM 仲裁纠正了盖高时，说明 px_per_mm_h 失真 ──
    # 用纠正后的盖高反推正确的 px_per_mm，重新计算直径
    cv_cap_h = cv_result.get("cap_height_mm", 0)
    merged_cap_h = merged.get("cap_height_mm", cv_cap_h)
    if (merged_cap_h > 0 and cv_cap_h > 0
            and abs(merged_cap_h - cv_cap_h) > 3):
        # VLM 仲裁修正了盖高 → 掩码截断确认
        cv_cap_h_px = cv_result.get("cap_height_px",
                                     cv_result.get("_boundary_y", 0) - cv_result.get("_y_top", 0))
        if cv_cap_h_px > 10:
            corrected_px_per_mm = cv_cap_h_px / merged_cap_h
            old_body_od = effective_body_od
            old_neck_od = effective_neck_od
            # 重新计算直径
            bottom_w_px = cv_result.get("bottom_w_px",
                                         cv_result.get("_width_profile", np.array([0])).max())
            if bottom_w_px > 10:
                effective_body_od = round(bottom_w_px / corrected_px_per_mm, 1)
                effective_body_od = max(12.0, effective_body_od)
            # neck_od: 有独立瓶身测量时用比例，否则 body_od * 0.75
            bp = cv_result.get("bottle_profile") or {}
            if bp.get("neck_od_px", 0) > 0:
                effective_neck_od = round(bp["neck_od_px"] / corrected_px_per_mm, 1)
            else:
                effective_neck_od = round(effective_body_od * 0.75, 1)
            effective_neck_od = max(10.0, effective_neck_od)
            if effective_neck_od >= effective_body_od:
                effective_neck_od = round(effective_body_od * 0.75, 1)
            # 更新 user_dims
            user_dims["body_od_mm"] = effective_body_od
            user_dims["neck_od_mm"] = effective_neck_od
            print(f"  [截断修正] px_per_mm: {cv_cap_h_px / cv_cap_h:.2f} → "
                  f"{corrected_px_per_mm:.2f} (基于VLM盖高{merged_cap_h:.1f}mm)")
            print(f"  [截断修正] body_od: {old_body_od:.1f} → {effective_body_od:.1f}mm")
            print(f"  [截断修正] neck_od: {old_neck_od:.1f} → {effective_neck_od:.1f}mm")

    # 确定 bottle height（建模参数）
    # 优先用独立瓶身轮廓的实测高度（最可靠，直接测到瓶身全高含颈部）
    # 回退：可见瓶身 + 颈高估算
    cap_h = merged.get("cap_height_mm", cv_result.get("cap_height_mm", 45))
    standalone_bh = cv_result.get("standalone_bottle_height_mm", 0)
    if standalone_bh > 20:
        bottle_h = standalone_bh
        print(f"  [瓶身高度] 使用独立瓶身实测: {bottle_h:.1f}mm")
    else:
        visible_bottle = total_height_mm - cap_h
        neck_h_est = merged.get("bottle_neck_height_mm",
                                total_height_mm * merged.get("bottle_neck_height_ratio", 0.1))
        bottle_h = round(visible_bottle + neck_h_est, 1)
        print(f"  [瓶身高度] 回退: 可见瓶身{visible_bottle:.1f} + 颈高{neck_h_est:.1f} = {bottle_h:.1f}mm")
    bottle_h = max(30, min(100, bottle_h))

    print(f"\n  合并结果:")
    print(f"    shape={merged['shape']}, taper_deg={merged['taper_deg']}")
    print(f"    cap_taper_deg={merged['cap_taper_deg']}")
    print(f"    cap_height_mm={cap_h}, bottle_height_mm={bottle_h}")
    print(f"    cross_section={merged['cross_section']}")
    print(f"    cap_top_shape={merged['cap_top_shape']}")
    print(f"    shoulder_style={merged['shoulder_style']}")
    print(f"    cap_od_ratio={merged.get('cap_od_ratio', 1.0)}")
    print(f"    cap_od_base={merged.get('cap_od_base', 'body')}")
    if merged.get("_unified_silhouette"):
        print(f"    ★ 统一轮廓: {merged.get('_unified_note', '')}")

    # ── CV Bottle Profile → shoulder_height 精确覆盖 ──
    bp = cv_result.get("bottle_profile")
    if bp and bp.get("shoulder_height_mm"):
        cv_sh = bp["shoulder_height_mm"]
        if 2.0 < cv_sh < 25.0:
            merged["shoulder_height_mm"] = cv_sh
            print(f"  [Override] shoulder_height: → {cv_sh:.1f}mm (CV测量)")

    # ── 构建 Gallery entry ──
    # effective_body_od / effective_neck_od 已在 Stage 2 后确定
    print(f"\n  最终参数: body_od={effective_body_od:.1f}mm, "
          f"neck_od={effective_neck_od:.1f}mm, bottle_h={bottle_h:.1f}mm")
    gallery_entry = {
        "group_id": "auto",
        "variant_label": "自动 Pipeline",
        "desc": f"自动版 — BiRefNet+CV+VLM ({int(total_height_mm)}mm产品)",
        "components": ["bottle", "cap", "wiper"],
        "user_dims": {
            "height_mm": bottle_h,
            "body_od_mm": effective_body_od,
            "neck_od_mm": effective_neck_od,
        },
        "vlm_shape": merged,
    }

    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"Pipeline 完成, 耗时 {elapsed:.1f}s")
    print(f"{'=' * 60}")

    # ── 保存结果 ──
    # 清理不可序列化的内部调试数据
    cv_clean = {k: v for k, v in cv_result.items() if not k.startswith("_")}

    result = {
        "name": name,
        "total_height_mm": total_height_mm,
        "user_dims": gallery_entry["user_dims"],
        "cv_measurement": cv_clean,
        "vlm_raw": vlm_shape_raw,
        "vlm_description": vlm_desc,
        "merged_vlm_shape": merged,
        "gallery_entry": gallery_entry,
    }

    out_json = OUT_DIR / f"{name}_result.json"
    with open(str(out_json), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n结果已保存: {out_json}")

    # 调试图
    save_debug(name, color_img, cv_result, merged)

    return result


# ════════════════════════════════════════════════════════════════════════
# 轻量级 CV 尺寸推算（仅 BiRefNet + CV，不跑 VLM）
# ════════════════════════════════════════════════════════════════════════

def cv_quick_dims(image_path: str, total_height_mm: float) -> dict:
    """
    快速从参考图推算全部关键几何参数。

    只跑 BiRefNet 抠图 + CV 定量测量，不调 VLM API。
    返回: {
        "body_od_mm", "neck_od_mm", "height_mm",  -- 尺寸
        "cap_height_mm", "taper_deg", "cap_ratio", -- 比例/角度
        "cap_od_ratio",                            -- cap/body 宽度比
    }
    """
    mask = birefnet_mask(image_path)
    color_img = cv2.imread(str(image_path))
    if color_img is None:
        buf = np.fromfile(str(image_path), dtype=np.uint8)
        color_img = cv2.imdecode(buf, cv2.IMREAD_COLOR)

    cv_result = cv_measure(mask, color_img, total_height_mm, 0)
    if "error" in cv_result:
        return {}

    body_od = cv_result.get("derived_body_od_mm", 0)
    neck_od = cv_result.get("derived_neck_od_mm", 0)
    cap_h = cv_result.get("cap_height_mm", total_height_mm * 0.35)
    cap_ratio = cv_result.get("cap_ratio", 0)
    cap_od_ratio = cv_result.get("cap_od_ratio", 1.0)

    # 统一锥度（整件轮廓，不分 cap/bottle）
    unified_taper = cv_result.get("unified_taper_deg", 0)

    # 用 cap_ratio 推算产品可见高度 → bottle 建模高度
    visible_bottle = total_height_mm * (1 - cap_ratio) if cap_ratio > 0 else total_height_mm * 0.4
    bottle_h = max(30, min(100, round((visible_bottle + 5) / 0.86, 1)))

    # 零值兜底：CV 完全无法测量时才用简单回退
    if body_od <= 0:
        body_od = round(total_height_mm * 0.22, 1)
        print(f"  [CV推算] body_od 无结果, 回退: {body_od:.1f}mm")
    if neck_od <= 0:
        neck_od = round(body_od * 0.75, 1)
        print(f"  [CV推算] neck_od 无结果, 回退: {neck_od:.1f}mm")

    print(f"  [CV推算] body_od={body_od:.1f}mm, neck_od={neck_od:.1f}mm, "
          f"cap_h={cap_h:.1f}mm, taper={unified_taper:.1f}°, "
          f"cap_ratio={cap_ratio:.3f}")

    return {
        "body_od_mm": round(body_od, 1),
        "neck_od_mm": round(neck_od, 1),
        "height_mm": bottle_h,
        "cap_height_mm": round(cap_h, 1),
        "taper_deg": round(unified_taper, 1),
        "cap_ratio": round(cap_ratio, 3),
        "cap_od_ratio": round(cap_od_ratio, 3),
    }


# ════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="BiRefNet + CV + VLM 自动化参数提取 Pipeline"
    )
    parser.add_argument("image", help="参考图片路径")
    parser.add_argument("--total-height", type=float, required=True,
                        help="产品总高 (mm)")
    parser.add_argument("--body-od", type=float, default=0,
                        help="瓶身最大外径 (mm), 0=由CV自动推算")
    parser.add_argument("--neck-od", type=float, default=0,
                        help="瓶口外径 (mm), 0=���CV自动推算")
    parser.add_argument("--skip-vlm", action="store_true",
                        help="跳过 VLM 分类���使用默认定性参数）")

    args = parser.parse_args()
    result = run_pipeline(
        args.image, args.total_height, args.body_od, args.neck_od,
        skip_vlm=args.skip_vlm,
    )

    # 打印可粘贴的 Gallery entry
    entry = result.get("gallery_entry", {})
    if entry:
        print("\n" + "=" * 60)
        print("Gallery 条目（可直接粘贴到 GALLERY_CATALOG）:")
        print("=" * 60)
        # 格式化为 Python dict 字面量
        print(json.dumps(entry, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
