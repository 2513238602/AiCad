# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from datetime import datetime


def _f(x: float) -> str:
    return f"{x:.1f}"


def export_cap_sheet(spec: dict, out_svg: Path) -> None:
    """
    生成 cap 的简易工程图（SVG）。

    设计目标：
    - A4 横向
    - 三视图：正视、A-A剖视、俯视
    - 关键尺寸标注
    - 关键修复：任何尺寸组合都不越界（使用 viewport + fit scale）
    """
    # ---------------------------
    # 读取参数（都给默认值，避免 KeyError）
    # ---------------------------
    # A. 外形尺寸（最重要）
    od = float(spec.get("outer_od_mm", 24.0))
    H = float(spec.get("height_mm", 25.0))
    taper_deg = float(spec.get("taper_deg", 0.0))
    top_shape = str(spec.get("top_shape", "flat"))

    # B. 内腔配合
    id_ = float(spec.get("inner_id_mm", max(1.0, od - 2.0)))
    cav = float(spec.get("cavity_depth_mm", max(1.0, H - 2.0)))
    edge_fillet = float(spec.get("edge_fillet_mm", 1.0))

    # C. 螺纹
    thr = spec.get("thread", {}) or {}
    thr_on = bool(thr.get("enabled", False))
    thr_crest = float(thr.get("crest_dia_mm", id_))
    thr_pitch = float(thr.get("pitch_mm", 2.7))
    thr_turns = int(thr.get("turns", 2))
    thr_depth = float(thr.get("depth_mm", 0.6))

    # 计算值
    wall = max(0.1, (od - id_) / 2.0)
    top_style = "圆顶" if top_shape == "dome" else "平顶"
    top_thick = H - cav  # 顶部厚度
    # 根据内径推断口部规格
    if 17.5 <= id_ <= 19.0:
        finish = "18-415"
    elif 19.5 <= id_ <= 21.0:
        finish = "20-410"
    elif 23.5 <= id_ <= 25.0:
        finish = "24-410"
    else:
        finish = f"⌀{id_:.0f}"

    # ---------------------------
    # 页面布局（A4 横向，单位 mm）
    # ---------------------------
    W, Hp = 297.0, 210.0
    M = 10.0
    title_h = 34.0

    frame_x0, frame_y0 = M, M
    frame_x1, frame_y1 = W - M, Hp - M
    work_y1 = frame_y1 - title_h

    # 三列视图区
    vx0 = frame_x0 + 8.0
    vy0 = frame_y0 + 10.0
    vH = max(10.0, work_y1 - vy0 - 6.0)
    col_gap = 10.0
    col_w = (frame_x1 - vx0 - 8.0 - 2.0 * col_gap) / 3.0

    box_front = (vx0, vy0, col_w, vH)
    box_sect = (vx0 + col_w + col_gap, vy0, col_w, vH)
    box_top = (vx0 + 2.0 * (col_w + col_gap), vy0, col_w, vH)

    # ---------------------------
    # SVG primitives
    # ---------------------------
    def esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def rect(x, y, w, h, sw=0.6, fill="none"):
        return f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" stroke="black" stroke-width="{sw}" fill="{fill}"/>'

    def line(x1, y1, x2, y2, sw=0.6, dash=None):
        ds = f' stroke-dasharray="{dash}"' if dash else ""
        return f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" stroke="black" stroke-width="{sw}"{ds}/>'

    def text(x, y, s, size=3.6, anchor="start"):
        return f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size}" text-anchor="{anchor}" font-family="Arial,Microsoft YaHei,SimHei">{esc(s)}</text>'

    def dim_h(x1, x2, y, label):
        # 简单水平尺寸标注
        arrow = 1.8
        out = []
        out.append(line(x1, y, x2, y, sw=0.4))
        out.append(line(x1, y, x1 + arrow, y - arrow, sw=0.4))
        out.append(line(x1, y, x1 + arrow, y + arrow, sw=0.4))
        out.append(line(x2, y, x2 - arrow, y - arrow, sw=0.4))
        out.append(line(x2, y, x2 - arrow, y + arrow, sw=0.4))
        out.append(text((x1 + x2) / 2.0, y - 1.2, label, size=3.4, anchor="middle"))
        return out

    def dim_v(x, y1, y2, label):
        arrow = 1.8
        out = []
        out.append(line(x, y1, x, y2, sw=0.4))
        out.append(line(x, y1, x - arrow, y1 + arrow, sw=0.4))
        out.append(line(x, y1, x + arrow, y1 + arrow, sw=0.4))
        out.append(line(x, y2, x - arrow, y2 - arrow, sw=0.4))
        out.append(line(x, y2, x + arrow, y2 - arrow, sw=0.4))
        out.append(text(x + 2.2, (y1 + y2) / 2.0, label, size=3.4, anchor="start"))
        return out

    # ---------------------------
    # 核心：viewport + fit scale（防越界）
    # ---------------------------
    def viewport(box, header=14.0, bottom=16.0, pad=6.0):
        """
        box: (x,y,w,h)
        header: 视图区顶部标题预留
        bottom: 视图区底部标注预留
        pad: 左右留白
        """
        x, y, w, h = box
        vx = x + pad
        vy = y + header
        vw = max(1.0, w - 2.0 * pad)
        vh = max(1.0, h - header - bottom)
        return vx, vy, vw, vh

    def fit_scale(vw, vh, obj_w, obj_h, ratio=0.98):
        """
        ratio: 额外安全系数，确保就算尺寸标注略占空间也不溢出
        """
        sx = (vw * ratio) / max(obj_w, 1e-6)
        sy = (vh * ratio) / max(obj_h, 1e-6)
        return min(sx, sy)

    # 视图 viewport
    fvx, fvy, fvw, fvh = viewport(box_front, header=14.0, bottom=18.0, pad=6.0)
    svx, svy, svw, svh = viewport(box_sect, header=14.0, bottom=18.0, pad=6.0)
    tvx, tvy, tvw, tvh = viewport(box_top, header=14.0, bottom=14.0, pad=6.0)

    # 主视图/剖视图按 (od,H) 拟合
    s_main = fit_scale(fvw, fvh, od, H, ratio=0.92)
    s_sect = fit_scale(svw, svh, od, H, ratio=0.92)
    # 俯视图按 (od,od) 拟合
    s_top = fit_scale(tvw, tvh, od, od, ratio=0.92)

    # ---------------------------
    # 输出 SVG
    # ---------------------------
    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{Hp}mm" viewBox="0 0 {W} {Hp}">')

    # 外框
    svg.append(rect(frame_x0, frame_y0, frame_x1 - frame_x0, frame_y1 - frame_y0, sw=0.8))
    svg.append(rect(frame_x0 + 4, frame_y0 + 4, frame_x1 - frame_x0 - 8, frame_y1 - frame_y0 - 8, sw=0.4))

    # 标题栏
    tx0, ty0 = frame_x0 + 4, frame_y1 - title_h + 4
    tw, th = frame_x1 - frame_x0 - 8, title_h - 8
    svg.append(rect(tx0, ty0, tw, th, sw=0.4))
    svg.append(line(tx0 + tw * 0.62, ty0, tx0 + tw * 0.62, ty0 + th, sw=0.4))
    svg.append(text(tx0 + 6, ty0 + 8, "唇釉瓶-瓶盖 工程图（参数化）", size=5.2))
    svg.append(text(tx0 + 6, ty0 + 16, f"口部：{finish}   顶型：{top_style}", size=3.4))
    svg.append(text(tx0 + 6, ty0 + 24, "单位：mm    比例：NTS", size=3.4))
    svg.append(text(tx0 + tw * 0.62 + 6, ty0 + 10, "版本：A", size=3.4))
    svg.append(text(tx0 + tw * 0.62 + 6, ty0 + 18, datetime.now().strftime("日期：%Y-%m-%d"), size=3.4))

    # 视图区框
    for bx in (box_front, box_sect, box_top):
        svg.append(rect(bx[0], bx[1], bx[2], bx[3], sw=0.3))

    # 视图区标题
    svg.append(text(box_front[0] + box_front[2] / 2.0, box_front[1] + 6, "正视图", size=3.6, anchor="middle"))
    svg.append(text(box_sect[0] + box_sect[2] / 2.0, box_sect[1] + 6, "A-A 剖视图", size=3.6, anchor="middle"))
    svg.append(text(box_top[0] + box_top[2] / 2.0, box_top[1] + 6, "俯视图", size=3.6, anchor="middle"))

    # ---------------------------
    # 正视图（外轮廓 + 中心线 + 尺寸）
    # ---------------------------
    cap_w = od * s_main
    cap_h = H * s_main
    cx = fvx + fvw / 2.0
    top_y = fvy + (fvh - cap_h) / 2.0
    left_x = cx - cap_w / 2.0

    svg.append(rect(left_x, top_y, cap_w, cap_h, sw=0.8))
    svg.append(line(cx, top_y - 4, cx, top_y + cap_h + 4, sw=0.3, dash="2,2"))

    # 尺寸放在 viewport 下方预留区（不会越界）
    svg.extend(dim_h(left_x, left_x + cap_w, fvy + fvh + 8, f"Ø{_f(od)}"))
    svg.extend(dim_v(left_x + cap_w + 10, top_y, top_y + cap_h, f"盖高 {_f(H)}"))

    # ---------------------------
    # 剖视图（外轮廓 + 内腔矩形示意 + 尺寸）
    # ---------------------------
    cap_w2 = od * s_sect
    cap_h2 = H * s_sect
    cx2 = svx + svw / 2.0
    top_y2 = svy + (svh - cap_h2) / 2.0
    left_x2 = cx2 - cap_w2 / 2.0

    svg.append(rect(left_x2, top_y2, cap_w2, cap_h2, sw=0.8))
    svg.append(line(cx2, top_y2 - 4, cx2, top_y2 + cap_h2 + 4, sw=0.3, dash="2,2"))

    inner_w = id_ * s_sect
    cav_h = cav * s_sect
    inner_left = cx2 - inner_w / 2.0
    inner_top = top_y2 + (cap_h2 - cav_h)  # 内腔从开口向上 cav
    svg.append(rect(inner_left, inner_top, inner_w, cav_h, sw=0.8))

    # 注释：壁厚、内径、内腔深
    svg.append(text(inner_left, inner_top - 4, f"壁厚≈{_f(wall)}", size=3.2))
    svg.extend(dim_h(inner_left, inner_left + inner_w, svy + svh + 8, f"内径 {_f(id_)}"))
    svg.extend(dim_v(inner_left + inner_w + 10, inner_top, inner_top + cav_h, f"内腔深 {_f(cav)}"))

    # ---------------------------
    # 俯视图（圆 + 中心线 + 直径标注）
    # ---------------------------
    r = (od / 2.0) * s_top
    ccx = tvx + tvw / 2.0
    ccy = tvy + tvh / 2.0

    svg.append(f'<circle cx="{ccx:.3f}" cy="{ccy:.3f}" r="{r:.3f}" fill="none" stroke="black" stroke-width="0.8"/>')
    svg.append(line(ccx - r - 10, ccy, ccx + r + 10, ccy, sw=0.3, dash="2,2"))
    svg.append(line(ccx, ccy - r - 10, ccx, ccy + r + 10, sw=0.3, dash="2,2"))
    svg.extend(dim_h(ccx - r, ccx + r, tvy + tvh + 8, f"Ø{_f(od)}"))

    # ---------------------------
    # 参数小表（放在俯视图下面，确保在 box_top 内）
    # ---------------------------
    tab_x = box_top[0] + 6
    tab_y = box_top[1] + box_top[3] - 70  # 固定放在底部区域，增加高度容纳更多参数
    svg.append(text(tab_x, tab_y, "关键参数（复核）", size=3.6))
    rows = [
        f"外径 OD：{_f(od)}",
        f"总高 H：{_f(H)}",
        f"内径 ID：{_f(id_)}",
        f"内腔深：{_f(cav)}",
        f"壁厚(计算)：{_f(wall)}",
        f"顶厚(计算)：{_f(top_thick)}",
        f"边缘圆角：{_f(edge_fillet)}",
    ]
    # 螺纹参数
    if thr_on:
        rows.append(f"螺纹峰径：{_f(thr_crest)}")
        rows.append(f"螺距×圈数：{_f(thr_pitch)}×{thr_turns}")
    for i, rtxt in enumerate(rows):
        svg.append(text(tab_x, tab_y + 6 + i * 4.5, rtxt, size=2.8))

    svg.append("</svg>")

    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text("\n".join(svg), encoding="utf-8")
