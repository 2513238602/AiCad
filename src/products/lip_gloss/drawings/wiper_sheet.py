# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from datetime import datetime


def _f(x: float) -> str:
    return f"{x:.1f}"


def export_wiper_sheet(p: dict, out_svg: Path, title: str = "唇釉瓶-内塞 工程图（参数化）") -> None:
    """
    内塞工程图：
    - A4 横向
    - 正视图 / 剖视图 / 俯视图 + 参数表
    - 关键尺寸标注
    """
    # ---- 提取参数 ----
    H = float(p.get("height_mm", 12.0))
    outer_od = float(p.get("outer_od_mm", 15.5))
    inner_id = float(p.get("inner_id_mm", 12.0))
    orifice = float(p.get("orifice_mm", 7.0))
    orifice_edge = float(p.get("orifice_edge_mm", 0.3))

    flange_od = float(p.get("flange_od_mm", 17.0))
    flange_id = float(p.get("flange_id_mm", 14.5))
    flange_h = float(p.get("flange_height_mm", 1.5))
    flange_pos = str(p.get("flange_position", "bottom"))

    diaphragm_style = str(p.get("diaphragm_style", "flat"))
    diaphragm_t = float(p.get("diaphragm_thickness_mm", 0.8))

    material = str(p.get("material", "LDPE"))
    finish = str(p.get("finish", "18-415"))

    wall_t = (outer_od - inner_id) / 2.0

    # ---- 页面布局参数 ----
    W, Hp = 297.0, 210.0  # A4 横向
    M = 8.0  # 外边距
    title_h = 28.0  # 标题栏高度

    frame_x0, frame_y0 = M, M
    frame_x1, frame_y1 = W - M, Hp - M
    work_y1 = frame_y1 - title_h  # 工作区底部

    # 三列布局：正视图 | 剖视图 | 俯视图+参数表
    col_gap = 6.0
    left_margin = 6.0
    right_margin = 6.0
    available_w = frame_x1 - frame_x0 - left_margin - right_margin - 2 * col_gap
    col_w = available_w / 3.0

    vx0 = frame_x0 + left_margin
    vy0 = frame_y0 + 6
    vH = work_y1 - vy0 - 4

    # 计算缩放比例（内塞是小零件，需要放大显示）
    max_view_h = vH * 0.50
    scale = min(max_view_h / max(H, 1.0), (col_w - 40) / max(flange_od, 1.0))
    scale = max(scale, 2.0)  # 内塞很小，至少放大2倍
    scale = min(scale, 8.0)  # 限制最大缩放

    # ---- SVG 绘图函数 ----
    def rect(x: float, y: float, w: float, h: float, stroke: str = "black", sw: float = 0.5, fill: str = "none") -> str:
        return f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" stroke="{stroke}" stroke-width="{sw}" fill="{fill}"/>'

    def line(x1: float, y1: float, x2: float, y2: float, stroke: str = "black", sw: float = 0.5, dash: str | None = None) -> str:
        ds = f' stroke-dasharray="{dash}"' if dash else ""
        return f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{stroke}" stroke-width="{sw}"{ds}/>'

    def text(x: float, y: float, s: str, size: float = 3.2, anchor: str = "start", weight: str = "normal") -> str:
        s = (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        fw = f' font-weight="{weight}"' if weight != "normal" else ""
        return f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}" font-family="Arial, sans-serif"{fw}>{s}</text>'

    def circle(cx: float, cy: float, r: float, stroke: str = "black", sw: float = 0.5, fill: str = "none") -> str:
        return f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'

    def dim_h(x1: float, x2: float, y: float, label: str) -> str:
        """水平尺寸标注"""
        arrow = 1.5
        out = [
            line(x1, y, x2, y, sw=0.3),
            line(x1, y, x1 + arrow, y - arrow, sw=0.3),
            line(x1, y, x1 + arrow, y + arrow, sw=0.3),
            line(x2, y, x2 - arrow, y - arrow, sw=0.3),
            line(x2, y, x2 - arrow, y + arrow, sw=0.3),
            text((x1 + x2) / 2, y - 1.5, label, size=2.8, anchor="middle"),
        ]
        return "\n".join(out)

    def dim_v(x: float, y1: float, y2: float, label: str, offset: float = 2.0) -> str:
        """垂直尺寸标注"""
        arrow = 1.5
        out = [
            line(x, y1, x, y2, sw=0.3),
            line(x, y1, x - arrow, y1 + arrow, sw=0.3),
            line(x, y1, x + arrow, y1 + arrow, sw=0.3),
            line(x, y2, x - arrow, y2 - arrow, sw=0.3),
            line(x, y2, x + arrow, y2 - arrow, sw=0.3),
            text(x + offset, (y1 + y2) / 2 + 1, label, size=2.8, anchor="start"),
        ]
        return "\n".join(out)

    # ---- 开始绘制 ----
    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{Hp}mm" viewBox="0 0 {W} {Hp}">')

    # 外框
    svg.append(rect(frame_x0, frame_y0, frame_x1 - frame_x0, frame_y1 - frame_y0, sw=0.6))
    svg.append(rect(frame_x0 + 2, frame_y0 + 2, frame_x1 - frame_x0 - 4, frame_y1 - frame_y0 - 4, sw=0.3))

    # ---- 标题栏 ----
    tx0, ty0 = frame_x0 + 2, frame_y1 - title_h + 2
    tw, th = frame_x1 - frame_x0 - 4, title_h - 4
    svg.append(rect(tx0, ty0, tw, th, sw=0.3))
    svg.append(line(tx0 + tw * 0.65, ty0, tx0 + tw * 0.65, ty0 + th, sw=0.3))

    svg.append(text(tx0 + 4, ty0 + 7, title, size=4.5, weight="bold"))
    svg.append(text(tx0 + 4, ty0 + 14, f"配合规格：{finish}    材料：{material}    隔膜：{diaphragm_style}", size=3.0))
    svg.append(text(tx0 + 4, ty0 + 20, "单位：mm    比例：NTS    投影：第一角法", size=3.0))

    svg.append(text(tx0 + tw * 0.65 + 4, ty0 + 8, "版本：A", size=3.0))
    svg.append(text(tx0 + tw * 0.65 + 4, ty0 + 14, "未注公差：±0.1", size=3.0))
    svg.append(text(tx0 + tw * 0.65 + 4, ty0 + 20, datetime.now().strftime("日期：%Y-%m-%d"), size=3.0))

    # ---- 计算视图位置 ----
    wiper_w = outer_od * scale
    wiper_h = H * scale
    flange_w = flange_od * scale
    flange_hh = flange_h * scale

    view_top = vy0 + 15  # 视图顶部（留出标题空间）

    # ---- 第一列：正视图 ----
    col1_x = vx0
    svg.append(rect(col1_x, vy0, col_w, vH, sw=0.2, stroke="#ccc"))
    svg.append(text(col1_x + col_w / 2, vy0 + 5, "正视图", size=3.2, anchor="middle", weight="bold"))

    cx1 = col1_x + col_w / 2
    left1 = cx1 - wiper_w / 2
    flange_left1 = cx1 - flange_w / 2

    # 主体外形
    svg.append(rect(left1, view_top, wiper_w, wiper_h, sw=0.6))

    # 凸环（根据位置绘制）
    if flange_pos == "bottom":
        flange_y = view_top + wiper_h - flange_hh
    elif flange_pos == "middle":
        flange_y = view_top + (wiper_h - flange_hh) / 2
    else:  # top
        flange_y = view_top

    svg.append(rect(flange_left1, flange_y, flange_w, flange_hh, sw=0.6))

    # 中心线
    svg.append(line(cx1, view_top - 5, cx1, view_top + wiper_h + 5, sw=0.2, dash="2,1"))

    # 尺寸标注
    svg.append(dim_h(left1, left1 + wiper_w, view_top + wiper_h + 10, f"Ø{_f(outer_od)}"))
    svg.append(dim_v(left1 + wiper_w + 10, view_top, view_top + wiper_h, f"H={_f(H)}"))
    svg.append(dim_h(flange_left1, flange_left1 + flange_w, flange_y - 5, f"Ø{_f(flange_od)}"))

    # ---- 第二列：剖视图 ----
    col2_x = vx0 + col_w + col_gap
    svg.append(rect(col2_x, vy0, col_w, vH, sw=0.2, stroke="#ccc"))
    svg.append(text(col2_x + col_w / 2, vy0 + 5, "A-A 剖视图", size=3.2, anchor="middle", weight="bold"))

    cx2 = col2_x + col_w / 2
    left2 = cx2 - wiper_w / 2
    flange_left2 = cx2 - flange_w / 2

    # 外形
    svg.append(rect(left2, view_top, wiper_w, wiper_h, sw=0.6))

    # 凸环
    if flange_pos == "bottom":
        flange_y2 = view_top + wiper_h - flange_hh
    elif flange_pos == "middle":
        flange_y2 = view_top + (wiper_h - flange_hh) / 2
    else:
        flange_y2 = view_top
    svg.append(rect(flange_left2, flange_y2, flange_w, flange_hh, sw=0.6))

    # 内腔
    inner_w = inner_id * scale
    inner_left2 = cx2 - inner_w / 2
    diaphragm_hh = diaphragm_t * scale
    cavity_h = wiper_h - diaphragm_hh
    if cavity_h > 0:
        svg.append(rect(inner_left2, view_top + diaphragm_hh, inner_w, cavity_h, sw=0.4))

    # 中心孔口
    orifice_w = orifice * scale
    orifice_left2 = cx2 - orifice_w / 2
    svg.append(rect(orifice_left2, view_top, orifice_w, diaphragm_hh, sw=0.4, fill="#ddd"))

    # 中心线
    svg.append(line(cx2, view_top - 5, cx2, view_top + wiper_h + 5, sw=0.2, dash="2,1"))

    # 尺寸标注
    svg.append(dim_h(inner_left2, inner_left2 + inner_w, view_top + wiper_h + 10, f"内Ø{_f(inner_id)}"))
    svg.append(dim_h(orifice_left2, orifice_left2 + orifice_w, view_top - 5, f"孔Ø{_f(orifice)}"))
    svg.append(text(left2 - 1, view_top + wiper_h / 2, f"壁厚{_f(wall_t)}", size=2.6, anchor="end"))

    # ---- 第三列：俯视图 + 参数表 ----
    col3_x = vx0 + 2 * (col_w + col_gap)
    svg.append(rect(col3_x, vy0, col_w, vH, sw=0.2, stroke="#ccc"))
    svg.append(text(col3_x + col_w / 2, vy0 + 5, "俯视图", size=3.2, anchor="middle", weight="bold"))

    # 俯视图同心圆
    ccx = col3_x + col_w / 2
    r_flange = (flange_od / 2) * scale
    ccy = view_top + r_flange + 5

    # 凸环外圆
    svg.append(circle(ccx, ccy, r_flange, sw=0.6))
    # 主体外圆
    r_outer = (outer_od / 2) * scale
    svg.append(circle(ccx, ccy, r_outer, sw=0.5))
    # 内腔圆
    r_inner = (inner_id / 2) * scale
    svg.append(circle(ccx, ccy, r_inner, sw=0.4))
    # 中心孔口
    r_orifice = (orifice / 2) * scale
    svg.append(circle(ccx, ccy, r_orifice, sw=0.4, fill="#ddd"))

    # 十字线
    svg.append(line(ccx - r_flange - 5, ccy, ccx + r_flange + 5, ccy, sw=0.2, dash="2,1"))
    svg.append(line(ccx, ccy - r_flange - 5, ccx, ccy + r_flange + 5, sw=0.2, dash="2,1"))

    # 俯视图尺寸
    svg.append(dim_h(ccx - r_orifice, ccx + r_orifice, ccy + r_flange + 8, f"孔Ø{_f(orifice)}"))

    # ---- 参数表（在俯视图下方）----
    table_y = ccy + r_flange + 20
    table_x = col3_x + 4
    line_h = 4.5  # 行高

    svg.append(text(table_x, table_y, "关键参数", size=3.0, weight="bold"))
    table_y += 2

    params = [
        ("总高 H", f"{_f(H)} mm"),
        ("外径", f"Ø{_f(outer_od)} mm"),
        ("内径", f"Ø{_f(inner_id)} mm"),
        ("小孔径", f"Ø{_f(orifice)} mm"),
        ("凸环外径", f"Ø{_f(flange_od)} mm"),
        ("凸环内径", f"Ø{_f(flange_id)} mm"),
        ("凸环高", f"{_f(flange_h)} mm"),
        ("隔膜厚", f"{_f(diaphragm_t)} mm"),
        ("壁厚", f"{_f(wall_t)} mm"),
    ]

    # 确保参数表不超出边界
    max_rows = int((work_y1 - table_y - 5) / line_h)
    params = params[:max_rows]

    for i, (name, val) in enumerate(params):
        y = table_y + (i + 1) * line_h
        svg.append(text(table_x, y, f"{name}:", size=2.6))
        svg.append(text(table_x + 26, y, val, size=2.6))

    svg.append("</svg>")

    # ---- 写入文件 ----
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text("\n".join(svg), encoding="utf-8")
