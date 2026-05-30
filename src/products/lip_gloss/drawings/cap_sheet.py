# -*- coding: utf-8 -*-
"""瓶盖工程图 — 符合 GB/T 基本标准的参数化 SVG 图纸。"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from typing import Any

from .primitives import (
    _f, svg_header, drawing_frame, first_angle_layout, title_block,
    hatch_defs, hatch_rect,
    rect, line, text, circle, polygon,
    centerline, hidden_rect, hidden_line,
    dim_h, dim_v, section_symbol, fit_scale,
    SW_OUTLINE, SW_THIN,
)


def export_cap_sheet(spec: dict, out_svg: Path, solid: Any = None) -> None:
    # ------------------------------------------------------------------
    # 参数提取
    # ------------------------------------------------------------------
    od = float(spec.get("outer_od_mm", 24.0))
    H = float(spec.get("height_mm", 25.0))
    taper_deg = float(spec.get("taper_deg", 0.0))
    top_shape = str(spec.get("top_shape", "flat"))

    id_ = float(spec.get("inner_id_mm", max(1.0, od - 2.0)))
    cav = float(spec.get("cavity_depth_mm", max(1.0, H - 2.0)))
    edge_fillet = float(spec.get("edge_fillet_mm", 1.0))

    thr = spec.get("thread", {}) or {}
    thr_on = bool(thr.get("enabled", False))
    thr_crest = float(thr.get("crest_dia_mm", id_))

    wall = max(0.1, (od - id_) / 2.0)
    top_thick = H - cav

    top_style = "圆顶" if top_shape == "dome" else "平顶"
    if 17.5 <= id_ <= 19.0:
        finish = "18-415"
    elif 19.5 <= id_ <= 21.0:
        finish = "20-410"
    elif 23.5 <= id_ <= 25.0:
        finish = "24-410"
    else:
        finish = f"⌀{id_:.0f}"

    # ------------------------------------------------------------------
    # 页面与布局
    # ------------------------------------------------------------------
    W, Hp = 297.0, 210.0
    layout = first_angle_layout(W, Hp)
    box_front = layout["front"]
    box_sect = layout["section"]
    box_plan = layout["plan"]
    box_title = layout["title"]

    # 缩放
    pad_h, pad_v = 16.0, 18.0
    fvw = box_front[2] - 2 * pad_h
    fvh = box_front[3] - pad_v - 20
    s = fit_scale(fvw, fvh, od, H)

    svw = box_sect[2] - 2 * pad_h
    svh = box_sect[3] - pad_v - 20
    s_sect = fit_scale(svw, svh, od, H)

    pvw = box_plan[2] - 2 * pad_h
    pvh = box_plan[3] - pad_v - 10
    s_plan = fit_scale(pvw, pvh, od, od)

    # ------------------------------------------------------------------
    # SVG 输出
    # ------------------------------------------------------------------
    svg: list[str] = [svg_header(W, Hp)]

    # 图框
    svg.extend(drawing_frame(W, Hp))

    # 剖面线定义
    svg.append(hatch_defs())

    # ------------------------------------------------------------------
    # 正视图（左上）
    # ------------------------------------------------------------------
    fx0, fy0, fw, fh = box_front
    svg.append(text(fx0 + fw / 2, fy0 + 5, "正视图", size=3.2, anchor="middle", weight="bold"))

    cap_w = od * s
    cap_h = H * s
    cx = fx0 + fw / 2
    top_y = fy0 + 10 + (fh - 10 - cap_h) / 2
    left_x = cx - cap_w / 2

    if solid is not None:
        # --- 真实 3D 投影 ---
        from .projection import project_to_svg, DIR_FRONT
        svg.extend(project_to_svg(solid, DIR_FRONT, scale=s,
                                  cx=cx, cy=top_y + cap_h / 2))
    else:
        # --- 回退：参数化手绘 ---
        svg.append(rect(left_x, top_y, cap_w, cap_h, sw=SW_OUTLINE))
        inner_w_f = id_ * s
        cav_h_f = cav * s
        inner_left_f = cx - inner_w_f / 2
        inner_top_f = top_y + cap_h - cav_h_f
        svg.append(hidden_rect(inner_left_f, inner_top_f, inner_w_f, cav_h_f))

    # 中心线（点划线）
    svg.append(centerline(cx, top_y - 6, cx, top_y + cap_h + 6))

    # 剖切符号 A-A
    svg.extend(section_symbol(cx, top_y - 3, top_y + cap_h + 3, "A", "right"))

    # 尺寸标注
    dim_y_h = top_y + cap_h + 12
    svg.extend(dim_h(left_x, left_x + cap_w, dim_y_h,
                     f"Ø{_f(od)}", ext_y1=top_y + cap_h, ext_y2=top_y + cap_h))
    svg.extend(dim_v(left_x + cap_w + 12, top_y, top_y + cap_h,
                     _f(H), ext_x1=left_x + cap_w, ext_x2=left_x + cap_w))

    # ------------------------------------------------------------------
    # A-A 剖视图（右上）
    # ------------------------------------------------------------------
    sx0, sy0, sw_, sh_ = box_sect
    svg.append(text(sx0 + sw_ / 2, sy0 + 5, "A-A", size=3.2, anchor="middle", weight="bold"))

    cap_w2 = od * s_sect
    cap_h2 = H * s_sect
    cx2 = sx0 + sw_ / 2
    top_y2 = sy0 + 10 + (sh_ - 10 - cap_h2) / 2
    left_x2 = cx2 - cap_w2 / 2

    if solid is not None:
        # --- 真实 3D 剖切投影 ---
        from .projection import section_to_svg, DIR_FRONT
        svg.extend(section_to_svg(solid, DIR_FRONT,
                                  cut_origin=(0, 0, 0), cut_normal=(0, 1, 0),
                                  scale=s_sect, cx=cx2, cy=top_y2 + cap_h2 / 2))
    else:
        # --- 回退：参数化手绘 ---
        inner_w2 = id_ * s_sect
        cav_h2 = cav * s_sect
        top_thick_h = top_thick * s_sect
        wall_w2 = wall * s_sect
        inner_left2 = cx2 - inner_w2 / 2
        inner_top2 = top_y2 + top_thick_h
        svg.append(hatch_rect(left_x2, top_y2, cap_w2, top_thick_h))
        svg.append(hatch_rect(left_x2, inner_top2, wall_w2, cav_h2))
        svg.append(hatch_rect(inner_left2 + inner_w2, inner_top2, wall_w2, cav_h2))
        svg.append(rect(left_x2, top_y2, cap_w2, cap_h2, sw=SW_OUTLINE))
        svg.append(rect(inner_left2, inner_top2, inner_w2, cav_h2, sw=SW_OUTLINE))

    # 中心线
    svg.append(centerline(cx2, top_y2 - 6, cx2, top_y2 + cap_h2 + 6))

    # 尺寸标注
    inner_w2 = id_ * s_sect
    cav_h2 = cav * s_sect
    top_thick_h = top_thick * s_sect
    inner_left2 = cx2 - inner_w2 / 2
    inner_top2 = top_y2 + top_thick_h
    dim_y_sect = top_y2 + cap_h2 + 12
    svg.extend(dim_h(inner_left2, inner_left2 + inner_w2, dim_y_sect,
                     f"Ø{_f(id_)}", ext_y1=top_y2 + cap_h2, ext_y2=top_y2 + cap_h2))
    svg.extend(dim_v(inner_left2 + inner_w2 + 10, inner_top2, inner_top2 + cav_h2,
                     _f(cav), ext_x1=inner_left2 + inner_w2, ext_x2=inner_left2 + inner_w2))
    # 壁厚标注
    svg.extend(dim_h(left_x2, inner_left2, top_y2 + top_thick_h + cav_h2 / 2,
                     _f(wall)))

    # ------------------------------------------------------------------
    # 俯视图（左下）
    # ------------------------------------------------------------------
    px0, py0, pw, ph = box_plan
    svg.append(text(px0 + pw / 2, py0 + 5, "俯视图", size=3.2, anchor="middle", weight="bold"))

    r = (od / 2.0) * s_plan
    ccx = px0 + pw / 2
    ccy = py0 + 10 + (ph - 10 - 2 * r) / 2 + r

    if solid is not None:
        # --- 真实 3D 俯视投影 ---
        from .projection import project_top_to_svg
        svg.extend(project_top_to_svg(solid, scale=s_plan, cx=ccx, cy=ccy))
    else:
        # --- 回退：参数化手绘 ---
        svg.append(circle(ccx, ccy, r, sw=SW_OUTLINE))
        if thr_on:
            r_thr = (thr_crest / 2.0) * s_plan
            svg.append(circle(ccx, ccy, r_thr, sw=SW_THIN))

    # 中心线十字
    svg.append(centerline(ccx - r - 8, ccy, ccx + r + 8, ccy))
    svg.append(centerline(ccx, ccy - r - 8, ccx, ccy + r + 8))

    # 尺寸标注
    svg.extend(dim_h(ccx - r, ccx + r, ccy + r + 10,
                     f"Ø{_f(od)}", ext_y1=ccy + r, ext_y2=ccy + r))

    # ------------------------------------------------------------------
    # 标题栏（右下）
    # ------------------------------------------------------------------
    tx0, ty0, tw, th = box_title
    svg.extend(title_block(tx0, ty0, tw, th, {
        "title": "唇釉瓶-瓶盖",
        "subtitle": f"口部: {finish}  顶型: {top_style}",
        "drawing_no": f"LG-CAP-{finish}",
        "material": "PP / ABS",
        "scale_text": "NTS",
        "finish": finish,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "version": "A",
        "tolerance": "±0.15",
    }))

    svg.append("</svg>")

    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text("\n".join(svg), encoding="utf-8")
