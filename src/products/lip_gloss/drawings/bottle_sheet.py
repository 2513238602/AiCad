# -*- coding: utf-8 -*-
"""瓶身工程图 — 符合 GB/T 基本标准的参数化 SVG 图纸。"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from typing import Any

from .primitives import (
    _f, svg_header, drawing_frame, first_angle_layout, title_block,
    hatch_defs, hatch_rect,
    rect, line, text, circle,
    centerline, hidden_rect, hidden_line,
    dim_h, dim_v, section_symbol, fit_scale,
    SW_OUTLINE, SW_THIN,
)


def export_bottle_sheet(p: dict, out_svg: Path,
                        title: str = "唇釉瓶-瓶身",
                        solid: Any = None) -> None:
    # ------------------------------------------------------------------
    # 参数提取
    # ------------------------------------------------------------------
    H = float(p.get("height_mm", 100.0))
    body_od = float(p.get("body_od_mm", 24.0))
    wall = float(p.get("wall_thickness_mm", 1.2))
    bottom_t = float(p.get("bottom_thickness_mm", 2.0))
    finish = str(p.get("finish", "18-415"))

    neck_od = float(p.get("neck_od_mm", 18.0))
    neck_h = float(p.get("neck_height_mm", 12.0))
    shoulder_h = float(p.get("shoulder_height_mm", 18.0))
    lip_t = float(p.get("lip_thickness_mm", 1.0))
    kind = str(p.get("shape", "cyl"))
    taper_deg = float(p.get("taper_deg", 0.0))
    capacity_ml = float(p.get("capacity_ml", 5.0))

    neck_id = max(0.1, neck_od - 2 * lip_t)
    body_id = max(0.1, body_od - 2 * wall)

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
    s = fit_scale(box_front[2] - 2 * pad_h, box_front[3] - pad_v - 20, body_od, H)
    s = min(s, 1.5)
    s_sect = fit_scale(box_sect[2] - 2 * pad_h, box_sect[3] - pad_v - 20, body_od, H)
    s_sect = min(s_sect, 1.5)
    s_plan = fit_scale(box_plan[2] - 2 * pad_h, box_plan[3] - pad_v - 10, body_od, body_od)
    s_plan = min(s_plan, 1.5)

    # ------------------------------------------------------------------
    # SVG 输出
    # ------------------------------------------------------------------
    svg: list[str] = [svg_header(W, Hp)]
    svg.extend(drawing_frame(W, Hp))
    svg.append(hatch_defs())

    # ------------------------------------------------------------------
    # 正视图（左上）
    # ------------------------------------------------------------------
    fx0, fy0, fw, fh = box_front
    svg.append(text(fx0 + fw / 2, fy0 + 5, "正视图", size=3.2, anchor="middle", weight="bold"))

    bottle_w = body_od * s
    bottle_h = H * s
    neck_w = neck_od * s
    neck_hh = neck_h * s
    cx = fx0 + fw / 2
    top_y = fy0 + 10 + (fh - 10 - bottle_h) / 2
    left_x = cx - bottle_w / 2
    neck_left = cx - neck_w / 2

    if solid is not None:
        from .projection import project_to_svg, DIR_FRONT
        svg.extend(project_to_svg(solid, DIR_FRONT, scale=s,
                                  cx=cx, cy=top_y + bottle_h / 2))
    else:
        svg.append(rect(left_x, top_y, bottle_w, bottle_h, sw=SW_OUTLINE))
        svg.append(rect(neck_left, top_y, neck_w, neck_hh, sw=SW_OUTLINE))
        inner_w_f = body_id * s
        inner_left_f = cx - inner_w_f / 2
        cavity_top_f = top_y + lip_t * s
        cavity_h_f = bottle_h - bottom_t * s - lip_t * s
        if cavity_h_f > 0:
            svg.append(hidden_rect(inner_left_f, cavity_top_f, inner_w_f, cavity_h_f))

    # 中心线
    svg.append(centerline(cx, top_y - 6, cx, top_y + bottle_h + 6))

    # 剖切符号 A-A
    svg.extend(section_symbol(cx, top_y - 3, top_y + bottle_h + 3, "A", "right"))

    # 尺寸标注
    dim_y = top_y + bottle_h + 12
    svg.extend(dim_h(left_x, left_x + bottle_w, dim_y,
                     f"Ø{_f(body_od)}", ext_y1=top_y + bottle_h, ext_y2=top_y + bottle_h))
    svg.extend(dim_v(left_x + bottle_w + 12, top_y, top_y + bottle_h,
                     _f(H), ext_x1=left_x + bottle_w, ext_x2=left_x + bottle_w))
    svg.extend(dim_h(neck_left, neck_left + neck_w, top_y - 5,
                     f"Ø{_f(neck_od)}", ext_y1=top_y, ext_y2=top_y))

    # ------------------------------------------------------------------
    # A-A 剖视图（右上）
    # ------------------------------------------------------------------
    sx0, sy0, sw_, sh_ = box_sect
    svg.append(text(sx0 + sw_ / 2, sy0 + 5, "A-A", size=3.2, anchor="middle", weight="bold"))

    bottle_w2 = body_od * s_sect
    bottle_h2 = H * s_sect
    cx2 = sx0 + sw_ / 2
    top_y2 = sy0 + 10 + (sh_ - 10 - bottle_h2) / 2
    left_x2 = cx2 - bottle_w2 / 2

    if solid is not None:
        from .projection import section_to_svg, DIR_FRONT
        svg.extend(section_to_svg(solid, DIR_FRONT,
                                  cut_origin=(0, 0, 0), cut_normal=(0, 1, 0),
                                  scale=s_sect, cx=cx2, cy=top_y2 + bottle_h2 / 2))
    else:
        wall_w2 = wall * s_sect
        bottom_h2 = bottom_t * s_sect
        lip_h2 = lip_t * s_sect
        inner_w2 = body_id * s_sect
        inner_left2 = cx2 - inner_w2 / 2
        cavity_top2 = top_y2 + lip_h2
        cavity_h2 = bottle_h2 - bottom_h2 - lip_h2
        svg.append(hatch_rect(left_x2, top_y2 + bottle_h2 - bottom_h2, bottle_w2, bottom_h2))
        if cavity_h2 > 0:
            svg.append(hatch_rect(left_x2, cavity_top2, wall_w2, cavity_h2))
        if cavity_h2 > 0:
            svg.append(hatch_rect(inner_left2 + inner_w2, cavity_top2, wall_w2, cavity_h2))
        neck_w2 = neck_od * s_sect
        neck_hh2 = neck_h * s_sect
        neck_left2 = cx2 - neck_w2 / 2
        neck_wall2 = lip_t * s_sect
        svg.append(hatch_rect(neck_left2, top_y2, neck_wall2, neck_hh2))
        svg.append(hatch_rect(neck_left2 + neck_w2 - neck_wall2, top_y2, neck_wall2, neck_hh2))
        svg.append(rect(left_x2, top_y2, bottle_w2, bottle_h2, sw=SW_OUTLINE))
        svg.append(rect(neck_left2, top_y2, neck_w2, neck_hh2, sw=SW_OUTLINE))
        if cavity_h2 > 0:
            svg.append(rect(inner_left2, cavity_top2, inner_w2, cavity_h2, sw=SW_OUTLINE))

    # 中心线
    svg.append(centerline(cx2, top_y2 - 6, cx2, top_y2 + bottle_h2 + 6))

    # 尺寸标注
    inner_w2 = body_id * s_sect
    bottom_h2 = bottom_t * s_sect
    inner_left2 = cx2 - inner_w2 / 2
    dim_y2 = top_y2 + bottle_h2 + 12
    svg.extend(dim_h(inner_left2, inner_left2 + inner_w2, dim_y2,
                     f"Ø{_f(body_id)}", ext_y1=top_y2 + bottle_h2, ext_y2=top_y2 + bottle_h2))
    svg.extend(dim_v(inner_left2 + inner_w2 + 10,
                     top_y2 + bottle_h2 - bottom_h2, top_y2 + bottle_h2,
                     _f(bottom_t),
                     ext_x1=inner_left2 + inner_w2, ext_x2=inner_left2 + inner_w2))

    # ------------------------------------------------------------------
    # 俯视图（左下）
    # ------------------------------------------------------------------
    px0, py0, pw, ph = box_plan
    svg.append(text(px0 + pw / 2, py0 + 5, "俯视图", size=3.2, anchor="middle", weight="bold"))

    r_outer = (body_od / 2) * s_plan
    r_inner = (body_id / 2) * s_plan
    ccx = px0 + pw / 2
    ccy = py0 + 10 + (ph - 10 - 2 * r_outer) / 2 + r_outer

    if solid is not None:
        from .projection import project_top_to_svg
        svg.extend(project_top_to_svg(solid, scale=s_plan, cx=ccx, cy=ccy))
    else:
        svg.append(circle(ccx, ccy, r_outer, sw=SW_OUTLINE))
        svg.append(circle(ccx, ccy, r_inner, sw=SW_THIN))

    svg.append(centerline(ccx - r_outer - 8, ccy, ccx + r_outer + 8, ccy))
    svg.append(centerline(ccx, ccy - r_outer - 8, ccx, ccy + r_outer + 8))

    svg.extend(dim_h(ccx - r_outer, ccx + r_outer, ccy + r_outer + 10,
                     f"Ø{_f(body_od)}", ext_y1=ccy + r_outer, ext_y2=ccy + r_outer))

    # ------------------------------------------------------------------
    # 标题栏（右下）
    # ------------------------------------------------------------------
    tx0, ty0, tw, th = box_title
    svg.extend(title_block(tx0, ty0, tw, th, {
        "title": title,
        "subtitle": f"形状: {kind}  锥度: {_f(taper_deg)}°  容量: {_f(capacity_ml)}ml",
        "drawing_no": f"LG-BTL-{finish}",
        "material": "PET / PETG",
        "scale_text": "NTS",
        "finish": finish,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "version": "A",
        "tolerance": "±0.2",
    }))

    svg.append("</svg>")

    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text("\n".join(svg), encoding="utf-8")
