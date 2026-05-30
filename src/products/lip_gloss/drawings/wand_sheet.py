# -*- coding: utf-8 -*-
"""刷杆工程图 — 符合 GB/T 基本标准的参数化 SVG 图纸。"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from typing import Any

from .primitives import (
    _f, svg_header, drawing_frame, first_angle_layout, title_block,
    hatch_defs, hatch_rect, hatch_polygon,
    rect, line, text, circle, polygon,
    centerline, hidden_rect, hidden_line,
    dim_h, dim_v, section_symbol, fit_scale,
    SW_OUTLINE, SW_THIN,
)


def export_wand_sheet(p: dict, out_svg: Path,
                      title: str = "唇釉瓶-刷杆",
                      solid: Any = None) -> None:
    # ------------------------------------------------------------------
    # 参数提取
    # ------------------------------------------------------------------
    wand_type = str(p.get("wand_type", "cap_integrated"))
    total_h = float(p.get("total_height_mm", 65.0))
    outer_od = float(p.get("outer_od_mm", 24.0))
    cap_h = float(p.get("cap_height_mm", 18.0))

    stem_d = float(p.get("stem_diameter_mm", 4.0))
    stem_len = float(p.get("stem_length_mm", 55.0))
    stem_wall = float(p.get("stem_wall_mm", 0.8))

    thr = p.get("thread", {}) or {}
    thr_crest = float(thr.get("crest_dia_mm", 18.0))
    thr_root = float(thr.get("root_dia_mm", 16.5))

    seal = p.get("seal_ring", {}) or {}
    seal_od = float(seal.get("od_mm", 17.5))
    seal_h = float(seal.get("height_mm", 3.0))

    brush = p.get("brush", {}) or {}
    brush_type = str(brush.get("type", "doe_foot"))
    brush_len = float(brush.get("length_mm", 12.0))
    brush_w = float(brush.get("width_mm", 10.0))

    finish = str(p.get("finish", "18-415"))
    type_label = "一体式" if wand_type == "cap_integrated" else "独立式"

    cap_wall = max(0.1, (outer_od - thr_crest) / 2.0)

    # ------------------------------------------------------------------
    # 页面与布局
    # ------------------------------------------------------------------
    W, Hp = 297.0, 210.0
    layout = first_angle_layout(W, Hp)
    box_front = layout["front"]
    box_sect = layout["section"]
    box_plan = layout["plan"]
    box_title = layout["title"]

    # 缩放（刷杆较长，需要控制）
    pad_h, pad_v = 12.0, 18.0
    s = fit_scale(box_front[2] - 2 * pad_h, box_front[3] - pad_v - 20, outer_od, total_h)
    s = max(0.6, min(s, 2.0))
    s_sect = fit_scale(box_sect[2] - 2 * pad_h, box_sect[3] - pad_v - 20, outer_od, total_h)
    s_sect = max(0.6, min(s_sect, 2.0))
    s_plan = fit_scale(box_plan[2] - 2 * pad_h, box_plan[3] - pad_v - 10, outer_od, outer_od)
    s_plan = min(s_plan, 2.5)

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

    cap_w = outer_od * s
    cap_hh = cap_h * s
    stem_w = stem_d * s
    stem_hh = stem_len * s
    brush_hh = brush_len * s
    brush_w_s = brush_w * s / 2

    cx = fx0 + fw / 2
    top_y = fy0 + 10 + (fh - 10 - total_h * s) / 2
    cap_left = cx - cap_w / 2
    stem_left = cx - stem_w / 2
    stem_top = top_y + cap_hh
    brush_top = top_y + cap_hh + stem_hh

    if solid is not None:
        from .projection import project_to_svg, DIR_FRONT
        svg.extend(project_to_svg(solid, DIR_FRONT, scale=s,
                                  cx=cx, cy=top_y + total_h * s / 2))
    else:
        svg.append(rect(cap_left, top_y, cap_w, cap_hh, sw=SW_OUTLINE))
        svg.append(rect(stem_left, stem_top, stem_w, stem_hh, sw=SW_OUTLINE))
        pts_l = f"{cx},{brush_top + brush_hh} {cx - brush_w_s},{brush_top + brush_hh} {stem_left},{brush_top}"
        svg.append(f'<polygon points="{pts_l}" fill="none" stroke="black" stroke-width="{SW_OUTLINE}"/>')
        pts_r = f"{cx},{brush_top + brush_hh} {cx + brush_w_s},{brush_top + brush_hh} {stem_left + stem_w},{brush_top}"
        svg.append(f'<polygon points="{pts_r}" fill="none" stroke="black" stroke-width="{SW_OUTLINE}"/>')
        thr_w_f = thr_crest * s
        thr_left_f = cx - thr_w_f / 2
        svg.append(hidden_rect(thr_left_f, top_y, thr_w_f, cap_hh * 0.7))
        seal_w_f = seal_od * s
        seal_left_f = cx - seal_w_f / 2
        seal_hh_f = seal_h * s
        svg.append(hidden_rect(seal_left_f, top_y + cap_hh * 0.7 - seal_hh_f, seal_w_f, seal_hh_f))

    # 中心线
    svg.append(centerline(cx, top_y - 6, cx, brush_top + brush_hh + 6))

    # 剖切符号
    svg.extend(section_symbol(cx, top_y - 3, brush_top + brush_hh + 3, "A", "right"))

    # 尺寸标注
    svg.extend(dim_h(cap_left, cap_left + cap_w, top_y - 8,
                     f"Ø{_f(outer_od)}", ext_y1=top_y, ext_y2=top_y))
    svg.extend(dim_v(cap_left - 10, top_y, top_y + cap_hh,
                     _f(cap_h), ext_x1=cap_left, ext_x2=cap_left))
    svg.extend(dim_h(stem_left, stem_left + stem_w, stem_top + stem_hh / 2,
                     f"Ø{_f(stem_d)}"))
    svg.extend(dim_v(cap_left + cap_w + 10, top_y, brush_top + brush_hh,
                     _f(total_h), ext_x1=cap_left + cap_w, ext_x2=cap_left + cap_w))

    # ------------------------------------------------------------------
    # A-A 剖视图（右上）
    # ------------------------------------------------------------------
    sx0, sy0, sw_, sh_ = box_sect
    svg.append(text(sx0 + sw_ / 2, sy0 + 5, "A-A", size=3.2, anchor="middle", weight="bold"))

    cap_w2 = outer_od * s_sect
    cap_hh2 = cap_h * s_sect
    stem_w2 = stem_d * s_sect
    stem_hh2 = stem_len * s_sect
    brush_hh2 = brush_len * s_sect
    brush_w_s2 = brush_w * s_sect / 2
    cx2 = sx0 + sw_ / 2
    top_y2 = sy0 + 10 + (sh_ - 10 - total_h * s_sect) / 2
    cap_left2 = cx2 - cap_w2 / 2

    if solid is not None:
        from .projection import section_to_svg, DIR_FRONT
        svg.extend(section_to_svg(solid, DIR_FRONT,
                                  cut_origin=(0, 0, 0), cut_normal=(0, 1, 0),
                                  scale=s_sect, cx=cx2, cy=top_y2 + total_h * s_sect / 2))
    else:
        thr_w2 = thr_crest * s_sect
        thr_left2 = cx2 - thr_w2 / 2
        cap_wall_w = (cap_w2 - thr_w2) / 2
        cavity_hh2 = cap_hh2 * 0.7
        svg.append(hatch_rect(cap_left2, top_y2, cap_w2, cap_hh2 - cavity_hh2))
        svg.append(hatch_rect(cap_left2, top_y2 + cap_hh2 - cavity_hh2, cap_wall_w, cavity_hh2))
        svg.append(hatch_rect(thr_left2 + thr_w2, top_y2 + cap_hh2 - cavity_hh2, cap_wall_w, cavity_hh2))
        stem_left2 = cx2 - stem_w2 / 2
        stem_top2 = top_y2 + cap_hh2
        if stem_wall > 0 and stem_wall < stem_d / 2:
            inner_stem_w2 = (stem_d - 2 * stem_wall) * s_sect
            stem_wall_w2 = stem_wall * s_sect
            svg.append(hatch_rect(stem_left2, stem_top2, stem_wall_w2, stem_hh2 * 0.8))
            svg.append(hatch_rect(stem_left2 + stem_w2 - stem_wall_w2, stem_top2, stem_wall_w2, stem_hh2 * 0.8))
        seal_w2 = seal_od * s_sect
        seal_hh2 = seal_h * s_sect
        seal_left2 = cx2 - seal_w2 / 2
        seal_y2 = top_y2 + cap_hh2 - cavity_hh2 + (cavity_hh2 - seal_hh2)
        svg.append(hatch_rect(seal_left2, seal_y2, seal_w2, seal_hh2))
        svg.append(rect(seal_left2, seal_y2, seal_w2, seal_hh2, sw=SW_THIN, fill="#ddd"))
        svg.append(rect(cap_left2, top_y2, cap_w2, cap_hh2, sw=SW_OUTLINE))
        svg.append(rect(thr_left2, top_y2 + cap_hh2 - cavity_hh2, thr_w2, cavity_hh2, sw=SW_THIN))
        svg.append(rect(stem_left2, stem_top2, stem_w2, stem_hh2, sw=SW_OUTLINE))
        if stem_wall > 0 and stem_wall < stem_d / 2:
            inner_stem_left2 = cx2 - inner_stem_w2 / 2
            svg.append(rect(inner_stem_left2, stem_top2, inner_stem_w2, stem_hh2 * 0.8, sw=SW_THIN))
        brush_top2 = stem_top2 + stem_hh2
        svg.append(line(stem_left2, brush_top2, cx2 - brush_w_s2, brush_top2 + brush_hh2, sw=SW_OUTLINE))
        svg.append(line(stem_left2 + stem_w2, brush_top2, cx2 + brush_w_s2, brush_top2 + brush_hh2, sw=SW_OUTLINE))
        svg.append(line(cx2 - brush_w_s2, brush_top2 + brush_hh2, cx2 + brush_w_s2, brush_top2 + brush_hh2, sw=SW_OUTLINE))

    # 中心线
    brush_top2 = top_y2 + cap_hh2 + stem_hh2
    svg.append(centerline(cx2, top_y2 - 6, cx2, brush_top2 + brush_hh2 + 6))

    # 尺寸标注
    thr_w2 = thr_crest * s_sect
    thr_left2 = cx2 - thr_w2 / 2
    seal_w2 = seal_od * s_sect
    seal_hh2 = seal_h * s_sect
    seal_left2 = cx2 - seal_w2 / 2
    cavity_hh2 = cap_hh2 * 0.7
    seal_y2 = top_y2 + cap_hh2 - cavity_hh2 + (cavity_hh2 - seal_hh2)
    svg.extend(dim_h(thr_left2, thr_left2 + thr_w2, top_y2 - 5,
                     f"Ø{_f(thr_crest)}", ext_y1=top_y2, ext_y2=top_y2))
    svg.extend(dim_h(seal_left2, seal_left2 + seal_w2, seal_y2 - 4,
                     f"Ø{_f(seal_od)}"))

    # ------------------------------------------------------------------
    # 俯视图（左下）
    # ------------------------------------------------------------------
    px0, py0, pw, ph = box_plan
    svg.append(text(px0 + pw / 2, py0 + 5, "俯视图", size=3.2, anchor="middle", weight="bold"))

    r_outer = (outer_od / 2) * s_plan
    ccx = px0 + pw / 2
    ccy = py0 + 10 + (ph - 10 - 2 * r_outer) / 2 + r_outer

    if solid is not None:
        from .projection import project_top_to_svg
        svg.extend(project_top_to_svg(solid, scale=s_plan, cx=ccx, cy=ccy))
    else:
        svg.append(circle(ccx, ccy, r_outer, sw=SW_OUTLINE))
        r_thr = (thr_crest / 2) * s_plan
        svg.append(circle(ccx, ccy, r_thr, sw=SW_THIN))
        r_seal = (seal_od / 2) * s_plan
        svg.append(circle(ccx, ccy, r_seal, sw=SW_THIN, fill="#eee"))
        r_stem = (stem_d / 2) * s_plan
        svg.append(circle(ccx, ccy, r_stem, sw=SW_OUTLINE, fill="#ccc"))

    svg.append(centerline(ccx - r_outer - 8, ccy, ccx + r_outer + 8, ccy))
    svg.append(centerline(ccx, ccy - r_outer - 8, ccx, ccy + r_outer + 8))

    svg.extend(dim_h(ccx - r_outer, ccx + r_outer, ccy + r_outer + 10,
                     f"Ø{_f(outer_od)}", ext_y1=ccy + r_outer, ext_y2=ccy + r_outer))

    # ------------------------------------------------------------------
    # 标题栏（右下）
    # ------------------------------------------------------------------
    tx0, ty0, tw, th = box_title
    svg.extend(title_block(tx0, ty0, tw, th, {
        "title": title,
        "subtitle": f"类型: {type_label}  刷头: {brush_type}",
        "drawing_no": f"LG-WND-{finish}",
        "material": "PP + 尼龙",
        "scale_text": "NTS",
        "finish": finish,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "version": "A",
        "tolerance": "±0.2",
    }))

    svg.append("</svg>")

    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text("\n".join(svg), encoding="utf-8")
