# -*- coding: utf-8 -*-
"""
工程图共享绘图基础库 (GB/T 标准)

提供符合国标的 SVG 绘图原语：
- 标准线型（粗实线/细实线/点划线/虚线）
- 实心三角箭头尺寸标注 + 尺寸界线
- 45° 剖面线 (hatching)
- 剖切符号
- 网格式标题栏
- 第一角投影布局工具
"""
from __future__ import annotations


# ============================================================
# 常量
# ============================================================

# 线型 dash 模式
DASH_CENTER = "10,2,2,2"   # 点划线（中心线/对称线）
DASH_HIDDEN = "4,2"         # 虚线（不可见轮廓）

# 线宽
SW_OUTLINE = 0.7            # 粗实线（可见轮廓）
SW_THIN = 0.35              # 细实线（尺寸线/引出线/剖面线）
SW_CENTER = 0.25            # 中心线/虚线

# 箭头尺寸
ARROW_L = 2.5               # 箭头长度 mm
ARROW_W = 0.8               # 箭头半宽 mm

# 字体
FONT = "Arial,Microsoft YaHei,SimHei"


# ============================================================
# 工具函数
# ============================================================

def _f(x: float) -> str:
    """格式化浮点数为 1 位小数字符串。"""
    return f"{x:.1f}"


def esc(s: str) -> str:
    """XML 特殊字符转义。"""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ============================================================
# 基础 SVG 图元
# ============================================================

def rect(x: float, y: float, w: float, h: float,
         sw: float = SW_OUTLINE, fill: str = "none",
         stroke: str = "black", dash: str | None = None) -> str:
    ds = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'stroke="{stroke}" stroke-width="{sw}" fill="{fill}"{ds}/>')


def line(x1: float, y1: float, x2: float, y2: float,
         sw: float = SW_THIN, dash: str | None = None,
         stroke: str = "black") -> str:
    ds = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{stroke}" stroke-width="{sw}"{ds}/>')


def text(x: float, y: float, s: str, size: float = 3.2,
         anchor: str = "start", weight: str = "normal",
         rotate: float = 0) -> str:
    fw = f' font-weight="{weight}"' if weight != "normal" else ""
    rot = f' transform="rotate({rotate},{x:.2f},{y:.2f})"' if rotate else ""
    return (f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" '
            f'text-anchor="{anchor}" font-family="{FONT}"{fw}{rot}>'
            f'{esc(s)}</text>')


def circle(cx: float, cy: float, r: float,
           sw: float = SW_OUTLINE, fill: str = "none",
           stroke: str = "black") -> str:
    return (f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def polygon(points: list[tuple[float, float]],
            fill: str = "black", sw: float = 0,
            stroke: str = "none") -> str:
    pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return (f'<polygon points="{pts}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw}"/>')


# ============================================================
# 标准线型快捷函数
# ============================================================

def centerline(x1: float, y1: float, x2: float, y2: float) -> str:
    """点划线中心线。"""
    return line(x1, y1, x2, y2, sw=SW_CENTER, dash=DASH_CENTER)


def hidden_line(x1: float, y1: float, x2: float, y2: float) -> str:
    """虚线（不可见轮廓）。"""
    return line(x1, y1, x2, y2, sw=SW_CENTER, dash=DASH_HIDDEN)


def hidden_rect(x: float, y: float, w: float, h: float) -> str:
    """虚线矩形（不可见轮廓）。"""
    return rect(x, y, w, h, sw=SW_CENTER, dash=DASH_HIDDEN)


# ============================================================
# 实心三角箭头
# ============================================================

def _arrow_right(x: float, y: float) -> str:
    """箭头尖端在 (x,y)，指向右。"""
    return polygon([
        (x, y),
        (x - ARROW_L, y - ARROW_W),
        (x - ARROW_L, y + ARROW_W),
    ])


def _arrow_left(x: float, y: float) -> str:
    """箭头尖端在 (x,y)，指向左。"""
    return polygon([
        (x, y),
        (x + ARROW_L, y - ARROW_W),
        (x + ARROW_L, y + ARROW_W),
    ])


def _arrow_down(x: float, y: float) -> str:
    """箭头尖端在 (x,y)，指向下。"""
    return polygon([
        (x, y),
        (x - ARROW_W, y - ARROW_L),
        (x + ARROW_W, y - ARROW_L),
    ])


def _arrow_up(x: float, y: float) -> str:
    """箭头尖端在 (x,y)，指向上。"""
    return polygon([
        (x, y),
        (x - ARROW_W, y + ARROW_L),
        (x + ARROW_W, y + ARROW_L),
    ])


# ============================================================
# 尺寸标注（GB/T 4458.4）
# ============================================================

def dim_h(x1: float, x2: float, y: float, label: str,
          ext_y1: float | None = None,
          ext_y2: float | None = None) -> list[str]:
    """
    水平尺寸标注。

    参数:
        x1, x2: 尺寸线左右端点 X
        y: 尺寸线 Y 位置
        label: 标注文字（如 "Ø24.0"）
        ext_y1: 左侧尺寸界线起点 Y（轮廓边缘），None 则不画界线
        ext_y2: 右侧尺寸界线起点 Y，None 则同 ext_y1
    """
    if ext_y2 is None:
        ext_y2 = ext_y1
    out: list[str] = []
    gap = 1.0    # 界线与轮廓间隙
    ext = 2.0    # 界线超出尺寸线的长度

    # 尺寸界线
    if ext_y1 is not None:
        sign1 = 1 if ext_y1 < y else -1
        out.append(line(x1, ext_y1 + sign1 * gap, x1, y + sign1 * (-ext), sw=SW_THIN))
    if ext_y2 is not None:
        sign2 = 1 if ext_y2 < y else -1
        out.append(line(x2, ext_y2 + sign2 * gap, x2, y + sign2 * (-ext), sw=SW_THIN))

    # 尺寸线
    out.append(line(x1, y, x2, y, sw=SW_THIN))

    # 实心箭头
    out.append(_arrow_right(x2, y))
    out.append(_arrow_left(x1, y))

    # 文字（尺寸线上方居中）
    out.append(text((x1 + x2) / 2, y - 1.5, label, size=3.0, anchor="middle"))
    return out


def dim_v(x: float, y1: float, y2: float, label: str,
          ext_x1: float | None = None,
          ext_x2: float | None = None) -> list[str]:
    """
    竖直尺寸标注。

    参数:
        x: 尺寸线 X 位置
        y1, y2: 尺寸线上下端点 Y（y1 < y2）
        label: 标注文字
        ext_x1: 上端尺寸界线起点 X，None 则不画界线
        ext_x2: 下端尺寸界线起点 X，None 则同 ext_x1
    """
    if ext_x2 is None:
        ext_x2 = ext_x1
    out: list[str] = []
    gap = 1.0
    ext = 2.0

    # 尺寸界线
    if ext_x1 is not None:
        sign1 = 1 if ext_x1 < x else -1
        out.append(line(ext_x1 + sign1 * gap, y1, x + sign1 * (-ext), y1, sw=SW_THIN))
    if ext_x2 is not None:
        sign2 = 1 if ext_x2 < x else -1
        out.append(line(ext_x2 + sign2 * gap, y2, x + sign2 * (-ext), y2, sw=SW_THIN))

    # 尺寸线
    out.append(line(x, y1, x, y2, sw=SW_THIN))

    # 实心箭头
    out.append(_arrow_up(x, y1))
    out.append(_arrow_down(x, y2))

    # 文字（尺寸线左侧，旋转 90°）
    tx = x - 2.0
    ty = (y1 + y2) / 2
    out.append(text(tx, ty, label, size=3.0, anchor="middle", rotate=-90))
    return out


# ============================================================
# 剖面线 Hatching (GB/T 4458.6)
# ============================================================

def hatch_defs(pattern_id: str = "hatch",
               spacing: float = 2.5, angle: float = 45) -> str:
    """返回 SVG <defs> 块，定义 45° 剖面线填充图案。"""
    return (
        f'<defs>'
        f'<pattern id="{pattern_id}" width="{spacing:.1f}" height="{spacing:.1f}" '
        f'patternUnits="userSpaceOnUse" patternTransform="rotate({angle})">'
        f'<line x1="0" y1="0" x2="0" y2="{spacing:.1f}" '
        f'stroke="black" stroke-width="0.2"/>'
        f'</pattern>'
        f'</defs>'
    )


def hatch_rect(x: float, y: float, w: float, h: float,
               pattern_id: str = "hatch") -> str:
    """用剖面线填充的矩形区域。"""
    if w <= 0 or h <= 0:
        return ""
    return (f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'fill="url(#{pattern_id})" stroke="none"/>')


def hatch_polygon(points: list[tuple[float, float]],
                  pattern_id: str = "hatch") -> str:
    """用剖面线填充的多边形区域。"""
    pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return f'<polygon points="{pts}" fill="url(#{pattern_id})" stroke="none"/>'


# ============================================================
# 剖切符号 (GB/T 4458.6)
# ============================================================

def section_symbol(cx: float, y_top: float, y_bot: float,
                   label: str = "A", arrow_dir: str = "right") -> list[str]:
    """
    在正视图上绘制剖切符号。

    在 cx 处画竖直剖切线（细点划线），
    上下端各有粗短线段 + 字母 + 投影方向箭头。
    """
    out: list[str] = []
    stub = 5.0       # 粗短线段长度
    arrow_off = 3.5  # 箭头偏移距离
    text_off = 4.0   # 字母偏移距离

    # 剖切线（细点划线）
    out.append(line(cx, y_top, cx, y_bot, sw=SW_THIN, dash=DASH_CENTER))

    # 上端粗短线 + 箭头 + 字母
    out.append(line(cx - stub / 2, y_top, cx + stub / 2, y_top, sw=1.0))
    if arrow_dir == "right":
        out.append(_arrow_right(cx + arrow_off, y_top))
        out.append(text(cx - text_off, y_top + 1.2, label, size=4.0, anchor="middle", weight="bold"))
    else:
        out.append(_arrow_left(cx - arrow_off, y_top))
        out.append(text(cx + text_off, y_top + 1.2, label, size=4.0, anchor="middle", weight="bold"))

    # 下端粗短线 + 箭头 + 字母
    out.append(line(cx - stub / 2, y_bot, cx + stub / 2, y_bot, sw=1.0))
    if arrow_dir == "right":
        out.append(_arrow_right(cx + arrow_off, y_bot))
        out.append(text(cx - text_off, y_bot + 1.2, label, size=4.0, anchor="middle", weight="bold"))
    else:
        out.append(_arrow_left(cx - arrow_off, y_bot))
        out.append(text(cx + text_off, y_bot + 1.2, label, size=4.0, anchor="middle", weight="bold"))

    return out


# ============================================================
# 标题栏 (GB/T 10609.1 简化)
# ============================================================

def title_block(x0: float, y0: float, w: float, h: float,
                fields: dict) -> list[str]:
    """
    GB/T 风格网格标题栏。

    fields 键值:
        title      - 图名
        subtitle   - 副标题/规格描述
        drawing_no - 图号
        material   - 材料
        scale_text - 比例
        finish     - 口部规格
        date       - 日期
        version    - 版本
        tolerance  - 未注公差
    """
    out: list[str] = []
    # 外框
    out.append(rect(x0, y0, w, h, sw=0.5))

    # 列分割: 40% | 25% | 35%
    c1 = w * 0.40
    c2 = w * 0.65

    out.append(line(x0 + c1, y0, x0 + c1, y0 + h, sw=SW_THIN))
    out.append(line(x0 + c2, y0, x0 + c2, y0 + h, sw=SW_THIN))

    # 行分割: 每行 h/4
    rh = h / 4.0
    for i in range(1, 4):
        yy = y0 + i * rh
        out.append(line(x0, yy, x0 + w, yy, sw=0.2))

    # 左列 (col 0): 图名 / 规格 / 单位 / 投影法
    pad = 3.0
    out.append(text(x0 + pad, y0 + rh * 0.6, fields.get("title", ""), size=4.2, weight="bold"))
    out.append(text(x0 + pad, y0 + rh * 1.6, fields.get("subtitle", ""), size=2.8))
    out.append(text(x0 + pad, y0 + rh * 2.6, "单位: mm", size=2.8))
    # 第一角投影符号（简化文字）
    out.append(text(x0 + pad, y0 + rh * 3.6, "投影: 第一角法", size=2.8))

    # 中列 (col 1): 图号 / 材料 / 比例 / 规格
    mx = x0 + c1 + pad
    out.append(text(mx, y0 + rh * 0.4, "图号", size=2.2))
    out.append(text(mx, y0 + rh * 0.8, fields.get("drawing_no", "—"), size=2.8))
    out.append(text(mx, y0 + rh * 1.4, "材料", size=2.2))
    out.append(text(mx, y0 + rh * 1.8, fields.get("material", "—"), size=2.8))
    out.append(text(mx, y0 + rh * 2.4, "比例", size=2.2))
    out.append(text(mx, y0 + rh * 2.8, fields.get("scale_text", "NTS"), size=2.8))
    out.append(text(mx, y0 + rh * 3.4, "规格", size=2.2))
    out.append(text(mx, y0 + rh * 3.8, fields.get("finish", ""), size=2.8))

    # 右列 (col 2): 版本 / 日期 / 公差 / 空
    rx = x0 + c2 + pad
    out.append(text(rx, y0 + rh * 0.4, "版本", size=2.2))
    out.append(text(rx, y0 + rh * 0.8, fields.get("version", "A"), size=2.8))
    out.append(text(rx, y0 + rh * 1.4, "日期", size=2.2))
    out.append(text(rx, y0 + rh * 1.8, fields.get("date", ""), size=2.8))
    out.append(text(rx, y0 + rh * 2.4, "未注公差", size=2.2))
    out.append(text(rx, y0 + rh * 2.8, fields.get("tolerance", "±0.2"), size=2.8))

    return out


# ============================================================
# 图框
# ============================================================

def drawing_frame(W: float, H: float, margin: float = 10.0) -> list[str]:
    """标准双线图框：外框粗线 + 内框细线。"""
    return [
        rect(margin, margin, W - 2 * margin, H - 2 * margin, sw=0.8),
        rect(margin + 3, margin + 3, W - 2 * margin - 6, H - 2 * margin - 6, sw=0.3),
    ]


# ============================================================
# 布局工具
# ============================================================

def viewport(box: tuple[float, float, float, float],
             header: float = 0, bottom: float = 0,
             pad: float = 0) -> tuple[float, float, float, float]:
    """
    从 box (x,y,w,h) 中减去 header/bottom/pad 后得到可用视图区。
    返回 (vx, vy, vw, vh)。
    """
    x, y, w, h = box
    vx = x + pad
    vy = y + header
    vw = max(1.0, w - 2.0 * pad)
    vh = max(1.0, h - header - bottom)
    return vx, vy, vw, vh


def fit_scale(vw: float, vh: float,
              obj_w: float, obj_h: float,
              ratio: float = 0.92) -> float:
    """计算缩放比例使 obj 适合 (vw×vh) 视图区。"""
    sx = (vw * ratio) / max(obj_w, 1e-6)
    sy = (vh * ratio) / max(obj_h, 1e-6)
    return min(sx, sy)


def svg_header(W: float, H: float) -> str:
    """SVG 文件头。"""
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">'


# ============================================================
# 第一角投影布局计算
# ============================================================

def first_angle_layout(W: float = 297.0, H: float = 210.0,
                       margin: float = 10.0,
                       title_h: float = 30.0):
    """
    计算第一角投影法的视图区域。

    返回 dict:
        front: (x, y, w, h)  正视图区域（左上）
        section: (x, y, w, h)  剖视图区域（右上）
        plan: (x, y, w, h)  俯视图区域（左下）
        title: (x, y, w, h)  标题栏区域（右下）
    """
    inner_x = margin + 3
    inner_y = margin + 3
    inner_w = W - 2 * margin - 6
    inner_h = H - 2 * margin - 6

    # 左右分割 55:45
    left_w = inner_w * 0.55
    right_w = inner_w - left_w

    # 上下分割: 上行 = inner_h - title_h，下行 = title_h
    top_h = inner_h - title_h
    # 正视图占上行的 60%，俯视图占下行（去掉标题栏高度）
    front_h = top_h * 0.62
    plan_h = top_h * 0.38

    return {
        "front":   (inner_x, inner_y, left_w, front_h),
        "section": (inner_x + left_w, inner_y, right_w, front_h),
        "plan":    (inner_x, inner_y + front_h, left_w, plan_h),
        "title":   (inner_x + left_w, inner_y + front_h, right_w, plan_h + title_h),
    }
