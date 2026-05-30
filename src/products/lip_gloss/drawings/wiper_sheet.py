# -*- coding: utf-8 -*-
"""内塞工程图 — 符合 GB/T 基本标准的参数化 SVG 图纸。"""
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


def export_wiper_sheet(p: dict, out_svg: Path,
                       title: str = "唇釉瓶-内塞",
                       solid: Any = None) -> None:
    # ------------------------------------------------------------------
    # 参数提取
    # ------------------------------------------------------------------
    H = float(p.get("height_mm", 12.0))
    outer_od = float(p.get("outer_od_mm", 15.5))
    inner_id = float(p.get("inner_id_mm", 12.0))
    orifice = float(p.get("orifice_mm", 7.0))

    flange_od = float(p.get("flange_od_mm", 17.0))
    flange_id = float(p.get("flange_id_mm", 14.5))
    flange_h = float(p.get("flange_height_mm", 1.5))
    flange_pos = str(p.get("flange_position", "bottom"))

    diaphragm_style = str(p.get("diaphragm_style", "flat"))
    diaphragm_t = float(p.get("diaphragm_thickness_mm", 0.8))

    material = str(p.get("material", "LDPE"))
    finish = str(p.get("finish", "18-415"))

    wall_t = (outer_od - inner_id) / 2.0

    # ------------------------------------------------------------------
    # 页面与布局
    # ------------------------------------------------------------------
    W, Hp = 297.0, 210.0
    layout = first_angle_layout(W, Hp)
    box_front = layout["front"]
    box_sect = layout["section"]
    box_plan = layout["plan"]
    box_title = layout["title"]

    # 缩放（内塞小零件，需放大）
    pad_h, pad_v = 12.0, 18.0
    s = fit_scale(box_front[2] - 2 * pad_h, box_front[3] - pad_v - 20, flange_od, H)
    s = max(s, 2.0)
    s = min(s, 8.0)
    s_sect = fit_scale(box_sect[2] - 2 * pad_h, box_sect[3] - pad_v - 20, flange_od, H)
    s_sect = max(s_sect, 2.0)
    s_sect = min(s_sect, 8.0)
    s_plan = fit_scale(box_plan[2] - 2 * pad_h, box_plan[3] - pad_v - 10, flange_od, flange_od)
    s_plan = max(s_plan, 2.0)
    s_plan = min(s_plan, 8.0)

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

    wiper_w = outer_od * s
    wiper_h = H * s
    flange_w = flange_od * s
    flange_hh = flange_h * s

    cx = fx0 + fw / 2
    top_y = fy0 + 10 + (fh - 10 - wiper_h) / 2
    left1 = cx - wiper_w / 2
    flange_left1 = cx - flange_w / 2

    # 计算凸环 Y 位置（尺寸标注需要）
    if flange_pos == "bottom":
        flange_y = top_y + wiper_h - flange_hh
    elif flange_pos == "middle":
        flange_y = top_y + (wiper_h - flange_hh) / 2
    else:
        flange_y = top_y

    if solid is not None:
        from .projection import project_to_svg, DIR_FRONT
        svg.extend(project_to_svg(solid, DIR_FRONT, scale=s,
                                  cx=cx, cy=top_y + wiper_h / 2))
    else:
        svg.append(rect(left1, top_y, wiper_w, wiper_h, sw=SW_OUTLINE))
        svg.append(rect(flange_left1, flange_y, flange_w, flange_hh, sw=SW_OUTLINE))
        inner_w_f = inner_id * s
        inner_left_f = cx - inner_w_f / 2
        diaphragm_hh = diaphragm_t * s
        cavity_h_f = wiper_h - diaphragm_hh
        if cavity_h_f > 0:
            svg.append(hidden_rect(inner_left_f, top_y + diaphragm_hh, inner_w_f, cavity_h_f))
        orifice_w_f = orifice * s
        orifice_left_f = cx - orifice_w_f / 2
        svg.append(hidden_rect(orifice_left_f, top_y, orifice_w_f, diaphragm_hh))

    # 中心线
    svg.append(centerline(cx, top_y - 6, cx, top_y + wiper_h + 6))

    # 剖切符号
    svg.extend(section_symbol(cx, top_y - 3, top_y + wiper_h + 3, "A", "right"))

    # 尺寸标注
    svg.extend(dim_h(left1, left1 + wiper_w, top_y + wiper_h + 12,
                     f"Ø{_f(outer_od)}", ext_y1=top_y + wiper_h, ext_y2=top_y + wiper_h))
    svg.extend(dim_v(left1 + wiper_w + 12, top_y, top_y + wiper_h,
                     _f(H), ext_x1=left1 + wiper_w, ext_x2=left1 + wiper_w))
    svg.extend(dim_h(flange_left1, flange_left1 + flange_w, flange_y - 5,
                     f"Ø{_f(flange_od)}", ext_y1=flange_y, ext_y2=flange_y))

    # ------------------------------------------------------------------
    # A-A 剖视图（右上）
    # ------------------------------------------------------------------
    sx0, sy0, sw_, sh_ = box_sect
    svg.append(text(sx0 + sw_ / 2, sy0 + 5, "A-A", size=3.2, anchor="middle", weight="bold"))

    wiper_w2 = outer_od * s_sect
    wiper_h2 = H * s_sect
    cx2 = sx0 + sw_ / 2
    top_y2 = sy0 + 10 + (sh_ - 10 - wiper_h2) / 2

    if solid is not None:
        from .projection import section_to_svg, DIR_FRONT
        svg.extend(section_to_svg(solid, DIR_FRONT,
                                  cut_origin=(0, 0, 0), cut_normal=(0, 1, 0),
                                  scale=s_sect, cx=cx2, cy=top_y2 + wiper_h2 / 2))
    else:
        flange_w2 = flange_od * s_sect
        flange_hh2 = flange_h * s_sect
        diaphragm_hh2 = diaphragm_t * s_sect
        wall_w2 = wall_t * s_sect
        inner_w2 = inner_id * s_sect
        orifice_w2 = orifice * s_sect
        left2 = cx2 - wiper_w2 / 2
        flange_left2 = cx2 - flange_w2 / 2
        inner_left2 = cx2 - inner_w2 / 2
        orifice_left2 = cx2 - orifice_w2 / 2
        if flange_pos == "bottom":
            flange_y2 = top_y2 + wiper_h2 - flange_hh2
        elif flange_pos == "middle":
            flange_y2 = top_y2 + (wiper_h2 - flange_hh2) / 2
        else:
            flange_y2 = top_y2
        svg.append(hatch_rect(left2, top_y2, (wiper_w2 - orifice_w2) / 2, diaphragm_hh2))
        svg.append(hatch_rect(orifice_left2 + orifice_w2, top_y2,
                              (wiper_w2 - orifice_w2) / 2, diaphragm_hh2))
        cavity_h2 = wiper_h2 - diaphragm_hh2
        if cavity_h2 > 0:
            svg.append(hatch_rect(left2, top_y2 + diaphragm_hh2, wall_w2, cavity_h2))
        if cavity_h2 > 0:
            svg.append(hatch_rect(inner_left2 + inner_w2, top_y2 + diaphragm_hh2, wall_w2, cavity_h2))
        flange_wall_w2 = (flange_w2 - wiper_w2) / 2
        if flange_wall_w2 > 0:
            svg.append(hatch_rect(flange_left2, flange_y2, flange_wall_w2, flange_hh2))
            svg.append(hatch_rect(left2 + wiper_w2, flange_y2, flange_wall_w2, flange_hh2))
        svg.append(rect(left2, top_y2, wiper_w2, wiper_h2, sw=SW_OUTLINE))
        svg.append(rect(flange_left2, flange_y2, flange_w2, flange_hh2, sw=SW_OUTLINE))
        if cavity_h2 > 0:
            svg.append(rect(inner_left2, top_y2 + diaphragm_hh2, inner_w2, cavity_h2, sw=SW_OUTLINE))
        svg.append(rect(orifice_left2, top_y2, orifice_w2, diaphragm_hh2, sw=SW_THIN, fill="#ddd"))

    # 中心线
    svg.append(centerline(cx2, top_y2 - 6, cx2, top_y2 + wiper_h2 + 6))

    # 尺寸标注
    inner_w2 = inner_id * s_sect
    orifice_w2 = orifice * s_sect
    inner_left2 = cx2 - inner_w2 / 2
    orifice_left2 = cx2 - orifice_w2 / 2
    svg.extend(dim_h(inner_left2, inner_left2 + inner_w2, top_y2 + wiper_h2 + 12,
                     f"Ø{_f(inner_id)}", ext_y1=top_y2 + wiper_h2, ext_y2=top_y2 + wiper_h2))
    svg.extend(dim_h(orifice_left2, orifice_left2 + orifice_w2, top_y2 - 5,
                     f"Ø{_f(orifice)}", ext_y1=top_y2, ext_y2=top_y2))

    # ------------------------------------------------------------------
    # 俯视图（左下）
    # ------------------------------------------------------------------
    px0, py0, pw, ph = box_plan
    svg.append(text(px0 + pw / 2, py0 + 5, "俯视图", size=3.2, anchor="middle", weight="bold"))

    r_flange = (flange_od / 2) * s_plan
    r_orifice = (orifice / 2) * s_plan
    ccx = px0 + pw / 2
    ccy = py0 + 10 + (ph - 10 - 2 * r_flange) / 2 + r_flange

    if solid is not None:
        from .projection import project_top_to_svg
        svg.extend(project_top_to_svg(solid, scale=s_plan, cx=ccx, cy=ccy))
    else:
        svg.append(circle(ccx, ccy, r_flange, sw=SW_OUTLINE))
        r_outer = (outer_od / 2) * s_plan
        svg.append(circle(ccx, ccy, r_outer, sw=SW_OUTLINE))
        r_inner = (inner_id / 2) * s_plan
        svg.append(circle(ccx, ccy, r_inner, sw=SW_THIN))
        svg.append(circle(ccx, ccy, r_orifice, sw=SW_THIN, fill="#ddd"))

    svg.append(centerline(ccx - r_flange - 8, ccy, ccx + r_flange + 8, ccy))
    svg.append(centerline(ccx, ccy - r_flange - 8, ccx, ccy + r_flange + 8))

    svg.extend(dim_h(ccx - r_orifice, ccx + r_orifice, ccy + r_flange + 10,
                     f"Ø{_f(orifice)}", ext_y1=ccy + r_orifice, ext_y2=ccy + r_orifice))

    # ------------------------------------------------------------------
    # 标题栏（右下）
    # ------------------------------------------------------------------
    tx0, ty0, tw, th = box_title
    svg.extend(title_block(tx0, ty0, tw, th, {
        "title": title,
        "subtitle": f"配合: {finish}  材料: {material}  隔膜: {diaphragm_style}",
        "drawing_no": f"LG-WPR-{finish}",
        "material": material,
        "scale_text": "NTS",
        "finish": finish,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "version": "A",
        "tolerance": "±0.1",
    }))

    svg.append("</svg>")

    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text("\n".join(svg), encoding="utf-8")
