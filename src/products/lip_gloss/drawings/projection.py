# -*- coding: utf-8 -*-
"""
3D → 2D 正交投影引擎

利用 OCCT HLR (Hidden Line Removal) 算法，将 CadQuery 3D 实体
投影为 SVG 可见轮廓 + 隐线，支持剖切面投影。

公共 API:
    project_to_svg   — 对整个实体做正交投影，返回 (visible_svg, hidden_svg)
    section_to_svg    — 剖切实体后投影，返回 (outline_svg, hatch_polygons)
    project_bbox      — 计算投影后的 2D 包围盒
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import cadquery as cq
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Section
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_Transform
from OCP.GCPnts import GCPnts_TangentialDeflection
from OCP.gp import gp_Ax2, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf, gp_Vec
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_WIRE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from .primitives import DASH_HIDDEN, SW_CENTER, SW_OUTLINE

# ============================================================
# 常量
# ============================================================

# 投影方向预设 (direction vector: 从哪个方向看)
DIR_FRONT = (0, -1, 0)   # 正视图：沿 -Y 方向看
DIR_RIGHT = (1, 0, 0)    # 右视图：沿 +X 方向看
DIR_TOP = (0, 0, 1)      # 俯视图：沿 +Z 方向看（从上往下）
DIR_BOTTOM = (0, 0, -1)  # 仰视图：沿 -Z 方向看

# 采样精度
_DEFLECTION = 0.05        # 弦偏差 (mm)
_ANGULAR = 0.1            # 角度偏差 (rad)


# ============================================================
# 内部工具
# ============================================================

def _shape_from_wp(wp: cq.Workplane) -> Any:
    """从 CadQuery Workplane 提取 OCCT TopoDS_Shape。"""
    return wp.val().wrapped


def _extract_edges(compound: Any) -> list:
    """从 TopoDS_Shape 中提取所有 Edge。"""
    edges = []
    if compound is None or compound.IsNull():
        return edges
    exp = TopExp_Explorer(compound, TopAbs_EDGE)
    while exp.More():
        edges.append(TopoDS.Edge_s(exp.Current()))
        exp.Next()
    return edges


def _edge_to_points(edge: Any) -> list[tuple[float, float]]:
    """
    将一条 OCCT Edge 离散化为 2D 点序列。
    HLR 投影后 Z 坐标为 0，使用 X/Y。
    """
    adaptor = BRepAdaptor_Curve(edge)
    first = adaptor.FirstParameter()
    last = adaptor.LastParameter()

    # 使用弦偏差采样，自动适配曲率
    try:
        sampler = GCPnts_TangentialDeflection(adaptor, _DEFLECTION, _ANGULAR)
        n = sampler.NbPoints()
        if n < 2:
            # 回退：线性采样
            p1 = adaptor.Value(first)
            p2 = adaptor.Value(last)
            return [(p1.X(), p1.Y()), (p2.X(), p2.Y())]
        return [(sampler.Value(i).X(), sampler.Value(i).Y()) for i in range(1, n + 1)]
    except Exception:
        # 最终回退
        p1 = adaptor.Value(first)
        p2 = adaptor.Value(last)
        return [(p1.X(), p1.Y()), (p2.X(), p2.Y())]


def _points_to_svg_path(points: list[tuple[float, float]],
                         scale: float, ox: float, oy: float,
                         flip_y: bool = True) -> str:
    """
    将 2D 点序列转为 SVG path d 属性。

    参数:
        scale:  缩放倍率 (mm→SVG坐标)
        ox, oy: 偏移 (SVG 画布中的中心点)
        flip_y: 翻转 Y 轴（3D Y向上 → SVG Y向下）
    """
    if len(points) < 2:
        return ""
    parts = []
    for i, (px, py) in enumerate(points):
        sx = ox + px * scale
        sy = oy + (-py if flip_y else py) * scale
        cmd = "M" if i == 0 else "L"
        parts.append(f"{cmd}{sx:.2f},{sy:.2f}")
    return " ".join(parts)


def _bbox_2d(edges: list) -> tuple[float, float, float, float]:
    """计算 edge 集合的 2D 包围盒 (xmin, ymin, xmax, ymax)。"""
    xmin = ymin = float("inf")
    xmax = ymax = float("-inf")
    for edge in edges:
        pts = _edge_to_points(edge)
        for px, py in pts:
            xmin = min(xmin, px)
            ymin = min(ymin, py)
            xmax = max(xmax, px)
            ymax = max(ymax, py)
    if xmin == float("inf"):
        return (0, 0, 0, 0)
    return (xmin, ymin, xmax, ymax)


# ============================================================
# HLR 投影核心
# ============================================================

def _hlr_project(shape: Any,
                 direction: tuple[float, float, float]
                 ) -> tuple[list, list]:
    """
    OCCT HLR 投影。

    参数:
        shape:     TopoDS_Shape (OCCT solid)
        direction: 投影方向向量 (dx, dy, dz)

    返回:
        (visible_edges, hidden_edges)
    """
    dx, dy, dz = direction

    # 构建投影坐标系
    proj_dir = gp_Dir(dx, dy, dz)
    # "up" 方向选择：如果投影方向接近 Z 轴，用 Y 作为 up
    if abs(dz) > 0.9:
        up = gp_Dir(0, -1, 0) if dz > 0 else gp_Dir(0, 1, 0)
    else:
        up = gp_Dir(0, 0, 1)

    ax2 = gp_Ax2(gp_Pnt(0, 0, 0), proj_dir, up)
    projector = HLRAlgo_Projector(ax2)

    algo = HLRBRep_Algo()
    algo.Add(shape)
    algo.Projector(projector)
    algo.Update()
    algo.Hide()

    hlr = HLRBRep_HLRToShape(algo)

    # 收集可见边
    visible = []
    for getter in [hlr.VCompound, hlr.OutLineVCompound, hlr.Rg1LineVCompound]:
        try:
            comp = getter()
            if comp and not comp.IsNull():
                visible.extend(_extract_edges(comp))
        except Exception:
            pass

    # 收集隐藏边
    hidden = []
    for getter in [hlr.HCompound, hlr.OutLineHCompound, hlr.Rg1LineHCompound]:
        try:
            comp = getter()
            if comp and not comp.IsNull():
                hidden.extend(_extract_edges(comp))
        except Exception:
            pass

    return visible, hidden


# ============================================================
# 剖切
# ============================================================

def _make_half_solid(shape: Any, plane_origin: tuple[float, float, float],
                     plane_normal: tuple[float, float, float]) -> Any:
    """
    用无限半平面切割实体，保留法线反方向的一半。
    用于制作剖视图的半剖。
    """
    ox, oy, oz = plane_origin
    nx, ny, nz = plane_normal
    pln = gp_Pln(gp_Pnt(ox, oy, oz), gp_Dir(nx, ny, nz))

    # 制作一个大平面作为切割工具
    face = BRepBuilderAPI_MakeFace(pln, -500, 500, -500, 500).Face()

    # 拉伸平面为薄板并做布尔切割会很复杂，
    # 改用更简洁的方法：制作一个大的半空间盒子来切割
    # 创建一个沿法线方向偏移的大盒子
    box = cq.Workplane("XY").box(1000, 1000, 1000)
    box_shape = box.val().wrapped

    # 平移盒子使其中心在 plane_origin + 500*normal 处
    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(
        ox + nx * 500,
        oy + ny * 500,
        oz + nz * 500,
    ))
    moved_box = BRepBuilderAPI_Transform(box_shape, trsf).Shape()

    # 从原始实体中切掉盒子
    cut = BRepAlgoAPI_Cut(shape, moved_box)
    cut.Build()
    if cut.IsDone():
        return cut.Shape()
    return shape  # 回退


def _section_profile(shape: Any, plane_origin: tuple[float, float, float],
                     plane_normal: tuple[float, float, float]) -> list:
    """
    提取剖切面上的截面轮廓边线（用于填充剖面线）。
    """
    ox, oy, oz = plane_origin
    nx, ny, nz = plane_normal
    pln = gp_Pln(gp_Pnt(ox, oy, oz), gp_Dir(nx, ny, nz))

    section = BRepAlgoAPI_Section(shape, pln)
    section.Build()
    if section.IsDone():
        return _extract_edges(section.Shape())
    return []


# ============================================================
# 公共 API
# ============================================================

def project_bbox(wp: cq.Workplane,
                 direction: tuple[float, float, float] = DIR_FRONT
                 ) -> tuple[float, float, float, float]:
    """
    计算实体沿指定方向投影后的 2D 包围盒。

    返回:
        (xmin, ymin, xmax, ymax) 单位 mm
    """
    shape = _shape_from_wp(wp)
    visible, hidden = _hlr_project(shape, direction)
    all_edges = visible + hidden
    if not all_edges:
        return (0, 0, 0, 0)
    return _bbox_2d(all_edges)


def project_to_svg(wp: cq.Workplane,
                   direction: tuple[float, float, float] = DIR_FRONT,
                   *,
                   scale: float = 1.0,
                   cx: float = 0.0,
                   cy: float = 0.0,
                   show_hidden: bool = True,
                   ) -> list[str]:
    """
    将 3D 实体投影为 SVG 元素列表。

    参数:
        wp:          CadQuery Workplane
        direction:   投影方向
        scale:       缩放倍率
        cx, cy:      SVG 画布中的中心偏移
        show_hidden: 是否绘制隐线

    返回:
        SVG 元素字符串列表
    """
    shape = _shape_from_wp(wp)
    visible, hidden = _hlr_project(shape, direction)

    svg_parts: list[str] = []

    # 计算投影包围盒中心，用于居中
    all_edges = visible + hidden
    if not all_edges:
        return svg_parts

    bx0, by0, bx1, by1 = _bbox_2d(all_edges)
    # 中心偏移：将投影几何中心对齐到 (cx, cy)
    bcx = (bx0 + bx1) / 2.0
    bcy = (by0 + by1) / 2.0
    ox = cx - bcx * scale
    oy = cy + bcy * scale  # flip_y

    # 可见轮廓（粗实线）
    for edge in visible:
        pts = _edge_to_points(edge)
        d = _points_to_svg_path(pts, scale, ox, oy)
        if d:
            svg_parts.append(
                f'<path d="{d}" fill="none" stroke="black" '
                f'stroke-width="{SW_OUTLINE}" stroke-linecap="round" '
                f'stroke-linejoin="round"/>'
            )

    # 隐线（虚线）
    if show_hidden:
        for edge in hidden:
            pts = _edge_to_points(edge)
            d = _points_to_svg_path(pts, scale, ox, oy)
            if d:
                svg_parts.append(
                    f'<path d="{d}" fill="none" stroke="black" '
                    f'stroke-width="{SW_CENTER}" '
                    f'stroke-dasharray="{DASH_HIDDEN}" '
                    f'stroke-linecap="round"/>'
                )

    return svg_parts


def section_to_svg(wp: cq.Workplane,
                   direction: tuple[float, float, float] = DIR_FRONT,
                   cut_origin: tuple[float, float, float] = (0, 0, 0),
                   cut_normal: tuple[float, float, float] = (0, 1, 0),
                   *,
                   scale: float = 1.0,
                   cx: float = 0.0,
                   cy: float = 0.0,
                   hatch_id: str = "hatch",
                   ) -> list[str]:
    """
    剖切实体后投影为 SVG 元素列表。

    流程：
    1. 沿 cut_normal 方向切掉一半实体
    2. 对剩余半体做 HLR 投影 → 可见轮廓
    3. 提取剖切面上的截面线 → 剖面线填充区域

    参数:
        wp:          CadQuery Workplane (完整实体)
        direction:   投影方向
        cut_origin:  剖切平面原点
        cut_normal:  剖切平面法线 (切掉法线方向那一半)
        scale, cx, cy: SVG 定位参数
        hatch_id:    剖面线图案 ID

    返回:
        SVG 元素字符串列表（含剖面线填充 + 轮廓线）
    """
    shape = _shape_from_wp(wp)

    # 1. 半剖：切掉一半
    half = _make_half_solid(shape, cut_origin, cut_normal)

    # 2. 投影半体
    visible, hidden = _hlr_project(half, direction)

    # 3. 获取截面线（在剖切面上的轮廓）
    section_edges = _section_profile(shape, cut_origin, cut_normal)

    # 计算包围盒（用完整实体的投影确保与正视图对齐）
    full_vis, full_hid = _hlr_project(shape, direction)
    all_edges = full_vis + full_hid
    if not all_edges:
        all_edges = visible + hidden

    svg_parts: list[str] = []
    if not all_edges:
        return svg_parts

    bx0, by0, bx1, by1 = _bbox_2d(all_edges)
    bcx = (bx0 + bx1) / 2.0
    bcy = (by0 + by1) / 2.0
    ox = cx - bcx * scale
    oy = cy + bcy * scale

    # 截面线 → 闭合多边形 → 剖面线填充
    # 收集截面边的所有点，构建填充多边形
    section_pts_all: list[tuple[float, float]] = []
    for edge in section_edges:
        pts = _edge_to_points(edge)
        section_pts_all.extend(pts)

    if section_pts_all:
        # 按角度排序形成闭合多边形（旋转体截面通常可按角度排序）
        # 对于复杂截面，先按 Y 排序再对称处理
        svg_pts = []
        for px, py in section_pts_all:
            sx = ox + px * scale
            sy = oy + (-py) * scale
            svg_pts.append(f"{sx:.2f},{sy:.2f}")

        if svg_pts:
            pts_str = " ".join(svg_pts)
            svg_parts.append(
                f'<polygon points="{pts_str}" '
                f'fill="url(#{hatch_id})" stroke="none"/>'
            )

    # 可见轮廓
    for edge in visible:
        pts = _edge_to_points(edge)
        d = _points_to_svg_path(pts, scale, ox, oy)
        if d:
            svg_parts.append(
                f'<path d="{d}" fill="none" stroke="black" '
                f'stroke-width="{SW_OUTLINE}" stroke-linecap="round" '
                f'stroke-linejoin="round"/>'
            )

    return svg_parts


def project_top_to_svg(wp: cq.Workplane,
                       *,
                       scale: float = 1.0,
                       cx: float = 0.0,
                       cy: float = 0.0,
                       show_hidden: bool = True,
                       ) -> list[str]:
    """
    俯视图投影（从 +Z 向下看）的便捷接口。
    注意：俯视图中 X→SVG X, Y→SVG Y（不翻转）。
    """
    shape = _shape_from_wp(wp)
    visible, hidden = _hlr_project(shape, DIR_TOP)

    svg_parts: list[str] = []
    all_edges = visible + hidden
    if not all_edges:
        return svg_parts

    bx0, by0, bx1, by1 = _bbox_2d(all_edges)
    bcx = (bx0 + bx1) / 2.0
    bcy = (by0 + by1) / 2.0
    ox = cx - bcx * scale
    # 俯视图: 从上往下看，Y 轴不翻转
    oy = cy - bcy * scale

    for edge in visible:
        pts = _edge_to_points(edge)
        d = _points_to_svg_path(pts, scale, ox, oy, flip_y=False)
        if d:
            svg_parts.append(
                f'<path d="{d}" fill="none" stroke="black" '
                f'stroke-width="{SW_OUTLINE}" stroke-linecap="round" '
                f'stroke-linejoin="round"/>'
            )

    if show_hidden:
        for edge in hidden:
            pts = _edge_to_points(edge)
            d = _points_to_svg_path(pts, scale, ox, oy, flip_y=False)
            if d:
                svg_parts.append(
                    f'<path d="{d}" fill="none" stroke="black" '
                    f'stroke-width="{SW_CENTER}" '
                    f'stroke-dasharray="{DASH_HIDDEN}" '
                    f'stroke-linecap="round"/>'
                )

    return svg_parts
