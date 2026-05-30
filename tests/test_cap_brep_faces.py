# -*- coding: utf-8 -*-
"""
Cap BREP 面数/边数统计脚本 -- spline vs classic 对比

用法：
    conda activate AiCad
    cd g:/AiCad
    set PYTHONPATH=g:/AiCad/src
    python tests/test_cap_brep_faces.py
"""
from __future__ import annotations

import sys
import json

sys.path.insert(0, "g:/AiCad/src")

import cadquery as cq

# 确保派生规则已注册
import products.lip_gloss.derived_params  # noqa: F401

from core.modeler import Modeler


# ── 公共默认参数 ──────────────────────────────────────────────────────
CAP_BASE = {
    "outer_od_mm": 24.0,
    "height_mm": 25.0,
    "taper_deg": 0.0,
    "top_shape": "flat",
    "inner_id_mm": 22.4,
    "cavity_depth_mm": 23.5,
    "edge_fillet_mm": 0.5,
    "grip": {"style": "none", "count": 0, "depth_mm": 0.0},
}


def analyze_brep(label: str, solid: cq.Workplane, meta: dict) -> None:
    """统计并打印 BREP 面/边信息"""
    shape = solid.val()
    faces = shape.Faces()
    edges = shape.Edges()

    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"  模式:    {meta.get('profile_mode', 'unknown')}")
    print(f"  体积:    {shape.Volume():.2f} mm^3")
    print(f"  面数:    {len(faces)}")
    print(f"  边数:    {len(edges)}")

    if meta.get("degraded"):
        print(f"  降级特征: {meta['degraded']}")

    # 逐面详情
    print(f"\n  --- 面详情 (共 {len(faces)} 个) ---")
    for i, face in enumerate(faces):
        face_type = type(face.wrapped).__name__
        # 通过 OCC 获取曲面类型
        try:
            from OCP.BRep import BRep_Tool
            from OCP.GeomAbs import GeomAbs_SurfaceType
            surface = BRep_Tool.Surface_s(face.wrapped)
            from OCP.GeomAdaptor import GeomAdaptor_Surface
            adaptor = GeomAdaptor_Surface(surface)
            stype = adaptor.GetType()
            type_names = {
                GeomAbs_SurfaceType.GeomAbs_Plane: "Plane(平面)",
                GeomAbs_SurfaceType.GeomAbs_Cylinder: "Cylinder(圆柱面)",
                GeomAbs_SurfaceType.GeomAbs_Cone: "Cone(锥面)",
                GeomAbs_SurfaceType.GeomAbs_Sphere: "Sphere(球面)",
                GeomAbs_SurfaceType.GeomAbs_Torus: "Torus(环面)",
                GeomAbs_SurfaceType.GeomAbs_BezierSurface: "Bezier(贝塞尔面)",
                GeomAbs_SurfaceType.GeomAbs_BSplineSurface: "BSpline(B样条面)",
                GeomAbs_SurfaceType.GeomAbs_SurfaceOfRevolution: "Revolution(旋转面)",
                GeomAbs_SurfaceType.GeomAbs_SurfaceOfExtrusion: "Extrusion(拉伸面)",
                GeomAbs_SurfaceType.GeomAbs_OffsetSurface: "Offset(偏移面)",
                GeomAbs_SurfaceType.GeomAbs_OtherSurface: "Other(其他)",
            }
            stype_name = type_names.get(stype, f"Unknown({stype})")
        except Exception as e:
            stype_name = f"(无法获取: {e})"

        # 面积
        try:
            area = face.Area()
        except Exception:
            area = -1.0

        # 边数
        try:
            face_edges = face.Edges()
            n_edges = len(face_edges)
        except Exception:
            n_edges = -1

        print(f"    Face[{i:2d}]: {stype_name:30s}  面积={area:10.2f} mm^2  边数={n_edges}")

    print()


def main():
    modeler = Modeler()

    # ── 1. Classic 模式 ──────────────────────────────────────────────
    meta_classic = {}
    params_classic = {**CAP_BASE, "profile_mode": "classic"}
    solid_classic = modeler.build("cap", params_classic, meta=meta_classic)
    analyze_brep("Classic 模式瓶盖", solid_classic, meta_classic)

    # ── 2. Spline 模式（默认自动生成轮廓） ─────────────────────────
    meta_spline_default = {}
    params_spline_default = {
        **CAP_BASE,
        "profile_mode": "spline",
        "profile_points_json": "[]",
    }
    solid_spline_default = modeler.build("cap", params_spline_default, meta=meta_spline_default)
    analyze_brep("Spline 模式瓶盖（默认轮廓）", solid_spline_default, meta_spline_default)

    # ── 3. Spline 模式（自定义弧形轮廓） ──────────────────────────
    meta_spline_custom = {}
    cap_pts = [
        [12.0, 0.0],
        [12.2, 8.0],
        [12.1, 18.0],
        [11.5, 25.0],
    ]
    params_spline_custom = {
        **CAP_BASE,
        "profile_mode": "spline",
        "profile_points_json": json.dumps(cap_pts),
    }
    solid_spline_custom = modeler.build("cap", params_spline_custom, meta=meta_spline_custom)
    analyze_brep("Spline 模式瓶盖（自定义弧形轮廓）", solid_spline_custom, meta_spline_custom)

    # ── 汇总对比 ─────────────────────────────────────────────────────
    results = [
        ("Classic", solid_classic),
        ("Spline(默认)", solid_spline_default),
        ("Spline(自定义)", solid_spline_custom),
    ]

    print("\n" + "=" * 60)
    print("  汇总对比")
    print("=" * 60)
    print(f"  {'模式':<18s}  {'面数':>6s}  {'边数':>6s}  {'体积':>12s}")
    print(f"  {'-'*18}  {'-'*6}  {'-'*6}  {'-'*12}")
    for label, solid in results:
        shape = solid.val()
        n_faces = len(shape.Faces())
        n_edges = len(shape.Edges())
        vol = shape.Volume()
        print(f"  {label:<18s}  {n_faces:>6d}  {n_edges:>6d}  {vol:>12.2f}")

    # ── 旋转体分段面分析 ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  旋转体分段面分析")
    print("=" * 60)
    print("  [说明] 旋转体(revolution)理论上应是单一曲面。")
    print("  如果出现多个 BSpline 面或 Revolution 面拼成外壁，")
    print("  则这些面的边界就是可见的分段线。")
    print()

    for label, solid, meta in [
        ("Classic", solid_classic, meta_classic),
        ("Spline(默认)", solid_spline_default, meta_spline_default),
        ("Spline(自定义)", solid_spline_custom, meta_spline_custom),
    ]:
        shape = solid.val()
        faces = shape.Faces()
        rev_faces = []
        bspline_faces = []
        other_faces = []

        try:
            from OCP.BRep import BRep_Tool
            from OCP.GeomAbs import GeomAbs_SurfaceType
            from OCP.GeomAdaptor import GeomAdaptor_Surface

            for i, face in enumerate(faces):
                surface = BRep_Tool.Surface_s(face.wrapped)
                adaptor = GeomAdaptor_Surface(surface)
                stype = adaptor.GetType()
                if stype == GeomAbs_SurfaceType.GeomAbs_SurfaceOfRevolution:
                    rev_faces.append(i)
                elif stype == GeomAbs_SurfaceType.GeomAbs_BSplineSurface:
                    bspline_faces.append(i)
                else:
                    other_faces.append((i, stype))
        except Exception as e:
            print(f"  [{label}] OCC 分析失败: {e}")
            continue

        print(f"  [{label}]")
        print(f"    旋转面(Revolution): {len(rev_faces)} 个 -> 索引 {rev_faces}")
        print(f"    B样条面(BSpline):   {len(bspline_faces)} 个 -> 索引 {bspline_faces}")
        print(f"    其他面:             {len(other_faces)} 个")
        if rev_faces or bspline_faces:
            outer_candidates = rev_faces + bspline_faces
            print(f"    => 外壁旋转体候选面: {outer_candidates}")
            if len(outer_candidates) > 1:
                print(f"    => 外壁由 {len(outer_candidates)} 个面拼接，面边界即为分段线！")
            else:
                print(f"    => 外壁为单一面，无可见分段线。")
        print()


if __name__ == "__main__":
    main()
