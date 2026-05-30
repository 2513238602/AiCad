# -*- coding: utf-8 -*-
from __future__ import annotations

import math
from typing import Any, Callable, Dict, cast

import cadquery as cq

# 截面类型映射表：None = 特殊路径(round/square)，int = polygon 边数
SIDES_MAP = {
    "round": None,
    "square": None,
    "triangle": 3,
    "hexagon": 6,
    "octagon": 8,
}


def _is_polygon(cs: str) -> bool:
    """是否走 _polygon_loft 通用路径（triangle/hexagon/octagon 等）"""
    return SIDES_MAP.get(cs) is not None


def _n_sides(cs: str) -> int:
    """获取多边形边数"""
    return SIDES_MAP[cs]


# ═══════════════════════════════════════════════════════════════════════
# L6 几何 QC 辅助函数 — BRep 级成品检查
# ═══════════════════════════════════════════════════════════════════════

def _check_dimensions(comp_id: str, params: Dict[str, Any], bb) -> list:
    """L6a: BBox 尺寸 vs 参数验证"""
    checks = []

    if comp_id == "bottle":
        h_exp = params.get("height_mm", 0)
        od_exp = params.get("body_od_mm", 0)
        h_act = bb.zmax - bb.zmin
        od_act = max(bb.xmax - bb.xmin, bb.ymax - bb.ymin)
        is_spline = params.get("profile_mode") == "spline"
        has_taper = params.get("taper_deg", 0) > 0
        cs = params.get("cross_section", "round")
        # 容差：spline 高度控制松散，taper+polygon 也会缩短有效高度
        if is_spline:
            h_tol = max(8.0, h_exp * 0.4)
        elif has_taper and cs != "round":
            h_tol = max(5.0, h_exp * 0.25)
        elif params.get("bottom_style") == "convex":
            h_tol = 3.0
        else:
            h_tol = 2.0
        od_tol = 8.0 if is_spline else 1.5
        checks.append({
            "name": "bottle 高度", "expected": h_exp,
            "actual": round(h_act, 1), "tolerance": round(h_tol, 1),
            "pass": abs(h_act - h_exp) <= h_tol, "severity": "hard",
            "msg": f"height: 期望{h_exp}, 实际{h_act:.1f}mm (±{h_tol:.1f})",
        })
        checks.append({
            "name": "bottle 外径", "expected": od_exp,
            "actual": round(od_act, 1), "tolerance": od_tol,
            "pass": abs(od_act - od_exp) <= od_tol, "severity": "hard",
            "msg": f"body_od: 期望{od_exp}, 实际{od_act:.1f}mm (±{od_tol})",
        })

    elif comp_id == "cap":
        h_exp = params.get("height_mm", 0)
        od_exp = params.get("outer_od_mm", 0)
        h_act = bb.zmax - bb.zmin
        od_act = max(bb.xmax - bb.xmin, bb.ymax - bb.ymin)
        top_shape = params.get("top_shape", "flat")
        h_tol = 8.0 if top_shape == "dome" else (12.0 if top_shape == "pointed" else 3.0)
        checks.append({
            "name": "cap 高度", "expected": h_exp,
            "actual": round(h_act, 1), "tolerance": h_tol,
            "pass": abs(h_act - h_exp) <= h_tol, "severity": "hard",
            "msg": f"height: 期望{h_exp}, 实际{h_act:.1f}mm (±{h_tol}, {top_shape})",
        })
        checks.append({
            "name": "cap 外径", "expected": od_exp,
            "actual": round(od_act, 1), "tolerance": 1.5,
            "pass": abs(od_act - od_exp) <= 1.5, "severity": "hard",
            "msg": f"outer_od: 期望{od_exp}, 实际{od_act:.1f}mm (±1.5)",
        })

    elif comp_id == "wand":
        stem_len = params.get("stem_length_mm", 60)
        brush = params.get("brush", {})
        brush_len = brush.get("length_mm", 15.0) if isinstance(brush, dict) else 15.0
        h_exp = stem_len + brush_len
        h_act = bb.zmax - bb.zmin
        checks.append({
            "name": "wand 物理高度", "expected": round(h_exp, 1),
            "actual": round(h_act, 1), "tolerance": 5.0,
            "pass": abs(h_act - h_exp) <= 5.0, "severity": "hard",
            "msg": f"physical_height: 期望{h_exp:.1f}, 实际{h_act:.1f}mm (±5.0)",
        })

    elif comp_id == "wiper":
        od_exp = params.get("outer_od_mm", 0)
        od_act = max(bb.xmax - bb.xmin, bb.ymax - bb.ymin)
        checks.append({
            "name": "wiper 外径", "expected": od_exp,
            "actual": round(od_act, 1), "tolerance": 1.5,
            "pass": abs(od_act - od_exp) <= 1.5, "severity": "hard",
            "msg": f"outer_od: 期望{od_exp}, 实际{od_act:.1f}mm (±1.5)",
        })

    return checks


def _check_cross_section_geometry(
    comp_id: str, params: Dict[str, Any],
    face_types: Dict[str, int], total_faces: int,
) -> list:
    """L6b: 面类型分布 vs cross_section 验证"""
    checks = []
    cs = params.get("cross_section", "round")
    if comp_id == "wiper":
        return checks  # wiper 始终旋转体

    n_plane = face_types.get("plane", 0)
    n_cyl = face_types.get("cylinder", 0)

    if cs == "square":
        ok = n_plane >= 4
        checks.append({
            "name": f"{comp_id} 截面(square)", "pass": ok,
            "severity": "hard",
            "msg": f"square 需 plane≥4, 实际 plane={n_plane}; {face_types}",
        })
    elif _is_polygon(cs):
        n = _n_sides(cs)
        n_bspline = face_types.get("bspline", 0)
        # polygon_loft 生成 bspline 侧面而非 plane 侧面
        # 判定条件：plane ≥ n（拉伸）或 bspline 存在且无 cylinder（loft）
        ok = n_plane >= n or (n_bspline > 0 and n_cyl == 0)
        checks.append({
            "name": f"{comp_id} 截面({cs})", "pass": ok,
            "severity": "hard",
            "msg": f"{cs}(n={n}): plane={n_plane}, bspline={n_bspline}, cyl={n_cyl}; {face_types}",
        })
    elif cs == "round":
        has_rot = (n_cyl > 0 or face_types.get("cone", 0) > 0
                   or face_types.get("bspline", 0) > 0
                   or face_types.get("sphere", 0) > 0)
        checks.append({
            "name": f"{comp_id} 截面(round)", "pass": has_rot,
            "severity": "hard",
            "msg": f"round 需旋转面, cyl={n_cyl}; {face_types}",
        })

    return checks


def _check_thread_presence(
    comp_id: str, params: Dict[str, Any], meta: Dict[str, Any],
) -> list:
    """L6c: 螺纹存在性验证"""
    checks = []
    if comp_id not in ("bottle", "wand"):
        return checks

    thread_d = params.get("thread", {})
    thr_on = thread_d.get("enabled", True) if isinstance(thread_d, dict) else True

    if not thr_on:
        checks.append({
            "name": f"{comp_id} 螺纹", "pass": True, "severity": "info",
            "msg": f"螺纹已禁用（参数设置）",
        })
        return checks

    degraded = meta.get("degraded", [])
    thr_degraded = any("thread" in d.get("feature", "") for d in degraded)
    ts = meta.get("thread_status", {})

    if thr_degraded:
        checks.append({
            "name": f"{comp_id} 螺纹", "pass": False, "severity": "soft",
            "msg": f"螺纹已请求但生成失败（降级）",
        })
    elif ts.get("attempted") is False:
        checks.append({
            "name": f"{comp_id} 螺纹", "pass": True, "severity": "info",
            "msg": f"螺纹已启用但未尝试（长度不足）",
        })
    else:
        checks.append({
            "name": f"{comp_id} 螺纹", "pass": True, "severity": "info",
            "msg": f"螺纹已生成",
        })

    return checks


class Modeler:
    """
    通用建模器：所有 CadQuery 几何都在这里
    - 非关键装饰特征允许 degrade（记录在 meta.degraded）
    - 关键几何（壳体/切空/螺纹/密封）失败应抛异常，让上层 hard fail
    """

    # -----------------------------
    # common helpers
    # -----------------------------
    def degrade(self, meta: Dict[str, Any], feature: str, err: Exception) -> None:
        meta.setdefault("degraded", []).append({"feature": feature, "error": repr(err)})

    def try_feature(
        self,
        meta: Dict[str, Any],
        feature: str,
        fn: Callable[[], cq.Workplane],
        fallback: cq.Workplane,
    ) -> cq.Workplane:
        try:
            result = fn()
            # 安全检查：如果操作后体积变为负或接近零，回退
            try:
                vol = result.val().Volume()
                if vol <= 0:
                    self.degrade(meta, feature,
                                 RuntimeError(f"体积异常({vol:.1f})，已回退"))
                    return fallback
            except Exception:
                pass  # 无法获取体积时不阻塞
            return result
        except Exception as e:
            self.degrade(meta, feature, e)
            return fallback

    def export_step(self, wp: cq.Workplane, out_path: str) -> None:
        shp = wp.val()
        if not hasattr(shp, "Solids"):
            raise RuntimeError("export_step: val() is not a Shape")
        solids = shp.Solids()  # type: ignore[union-attr]
        if not solids or len(solids) == 0:
            raise RuntimeError("export_step: 0 solids, refuse to export empty STEP")
        if len(solids) > 1:
            import logging
            logging.warning("export_step: %d solids (expected 1) → %s", len(solids), out_path)
        cq.exporters.export(wp, out_path)

    def build_assembly(
        self,
        workplanes: Dict[str, cq.Workplane],
        positions: Dict[str, Dict[str, Any]],
    ) -> cq.Assembly:
        """
        将已构建的组件按装配位置组装为 cq.Assembly。
        在专业 CAD 软件中打开可看到完整外观，并可拆解每个命名组件。

        参数:
            workplanes: {"bottle": wp, "cap": wp, "wand": wp, "wiper": wp}
            positions: compute_assembly_positions() 返回的 {comp_id: {"dz": float}}
        返回:
            cq.Assembly — 可用 exportAssembly 导出为单一 STEP
        """
        assy = cq.Assembly(name="lip_gloss_assembly")
        for comp_id in ("bottle", "cap", "wand", "wiper"):
            wp = workplanes.get(comp_id)
            pos = positions.get(comp_id, {})
            if wp is None:
                continue
            dz = float(pos.get("dz", 0.0))
            assy.add(wp, name=comp_id, loc=cq.Location((0, 0, dz)))
        return assy

    @staticmethod
    def export_assembly_step(assy: cq.Assembly, out_path: str) -> None:
        """导出装配体为单一 STEP 文件（各组件保留命名，可在 CAD 软件中拆解）"""
        cq.exporters.assembly.exportAssembly(assy, out_path)

    def build(self, component_id: str, params: Dict[str, Any], meta: Dict[str, Any] | None = None) -> cq.Workplane:
        if meta is None:
            meta = {}
        fn = getattr(self, f"build_{component_id}", None)
        if not callable(fn):
            raise KeyError(f"no builder: build_{component_id}")
        result = cast(cq.Workplane, fn(params, meta))
        # 通用后处理：确保单实体 + 拓扑 QC
        result = self._ensure_single_solid(result, meta, label=component_id)
        shp = result.val()
        solids = shp.Solids()
        meta["topology_qc"] = {
            "solid_count": len(solids),
            "total_volume_mm3": round(shp.Volume(), 2),
            "per_solid_volumes": [round(s.Volume(), 2) for s in solids],
            "is_single_solid": len(solids) == 1,
            "negative_volume": shp.Volume() < 0,
            "fixes_applied": meta.get("topology_fixes", []),
            "warnings": meta.get("topology_warnings", []),
        }
        # ── geometry_qc — BRep 级几何语义检查 ──
        try:
            bb = shp.BoundingBox()
            faces = shp.Faces()
            face_types: Dict[str, int] = {}
            for f in faces:
                t = f.geomType().lower()
                face_types[t] = face_types.get(t, 0) + 1

            geo_checks: list = []
            geo_checks.extend(_check_dimensions(component_id, params, bb))
            geo_checks.extend(_check_cross_section_geometry(
                component_id, params, face_types, len(faces)))
            geo_checks.extend(_check_thread_presence(component_id, params, meta))

            meta["geometry_qc"] = {
                "bbox": {
                    "width": round(bb.xmax - bb.xmin, 2),
                    "depth": round(bb.ymax - bb.ymin, 2),
                    "height": round(bb.zmax - bb.zmin, 2),
                },
                "face_types": face_types,
                "total_faces": len(faces),
                "total_edges": len(shp.Edges()),
                "checks": geo_checks,
            }
        except Exception as _geo_err:
            meta["geometry_qc"] = {"error": repr(_geo_err), "checks": []}
        return result

    def _ensure_single_solid(
        self, wp: cq.Workplane, meta: Dict[str, Any], label: str = ""
    ) -> cq.Workplane:
        """
        检查 Workplane 是否包含多个 Solid。
        策略:
          0. 过滤微小碎片（< 总体积 1% 且 < 10mm³）
          1. BRepAlgoAPI_Fuse (标准)
          2. BRepAlgoAPI_Fuse + fuzzy tolerance (0.01mm)
          3. BOPAlgo_MakerVolume (体积构建器)
        """
        shp = wp.val()
        solids = shp.Solids()
        if len(solids) <= 1:
            return wp

        n_orig = len(solids)
        total_vol = sum(abs(s.Volume()) for s in solids)

        # ── 策略 1: 先尝试 Fuse 所有实体（不预过滤，避免丢弃有效零件） ──
        result_shape = self._try_fuse_solids(solids)
        if result_shape is not None:
            n = len(cq.Shape.cast(result_shape).Solids())
            if n == 1:
                return self._finish_fuse(result_shape, meta, label, n_orig, "Fuse")

        # ── 策略 2: Fuzzy Fuse (0.01mm 容差) ──
        result_shape = self._try_fuse_solids(solids, fuzzy=0.01)
        if result_shape is not None:
            n = len(cq.Shape.cast(result_shape).Solids())
            if n == 1:
                return self._finish_fuse(result_shape, meta, label, n_orig, "FuzzyFuse")

        # ── 策略 3: BOPAlgo_MakerVolume ──
        result_shape = self._try_maker_volume(solids)
        if result_shape is not None:
            n = len(cq.Shape.cast(result_shape).Solids())
            if n == 1:
                return self._finish_fuse(result_shape, meta, label, n_orig, "MakerVolume")

        # ── 策略 4: 过滤微小碎片后重试（阈值 1% 且 < 50mm³ 才视为碎片） ──
        largest_vol = max(abs(s.Volume()) for s in solids)
        significant = [s for s in solids
                       if abs(s.Volume()) >= total_vol * 0.01
                       or abs(s.Volume()) >= 50.0
                       or abs(s.Volume()) >= largest_vol - 0.01]
        tiny_count = len(solids) - len(significant)

        if tiny_count > 0 and len(significant) == 1:
            meta.setdefault("topology_fixes", []).append(
                f"{label}: 过滤 {tiny_count} 个微小碎片 (最大保留)"
            )
            return cq.Workplane("XY").newObject([significant[0]])

        if tiny_count > 0 and len(significant) > 1:
            # 过滤碎片后重试 fuse
            result_shape = self._try_fuse_solids(significant, fuzzy=0.01)
            if result_shape is not None and len(cq.Shape.cast(result_shape).Solids()) == 1:
                return self._finish_fuse(result_shape, meta, label, n_orig,
                                         f"FuzzyFuse+过滤{tiny_count}碎片")

        # ── 策略 5: 保留最大实体（最大占比 ≥ 85% 时安全丢弃小块） ──
        largest = max(solids, key=lambda s: abs(s.Volume()))
        largest_ratio = abs(largest.Volume()) / total_vol if total_vol > 0 else 0
        if largest_ratio >= 0.85:
            meta.setdefault("topology_fixes", []).append(
                f"{label}: 保留最大实体 (vol={abs(largest.Volume()):.0f}mm³, "
                f"{largest_ratio:.0%})，丢弃 {len(solids)-1} 个较小实体"
            )
            return cq.Workplane("XY").newObject([largest])

        # ── 所有策略失败 ──
        meta.setdefault("topology_warnings", []).append(
            f"{label}: 融合策略均失败，保留 {len(solids)} 实体"
        )
        return wp

    def _try_fuse_solids(self, solids, fuzzy: float = 0.0):
        """尝试用 BRepAlgoAPI_Fuse 逐个融合 solids，返回结果 Shape 或 None"""
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
        base = solids[0].wrapped
        for s in solids[1:]:
            fuser = BRepAlgoAPI_Fuse(base, s.wrapped)
            if fuzzy > 0:
                fuser.SetFuzzyValue(fuzzy)
            fuser.Build()
            if not fuser.IsDone():
                return None
            base = fuser.Shape()
        return base

    def _try_maker_volume(self, solids):
        """用 BOPAlgo_MakerVolume 从多个实体构建单一体积"""
        try:
            from OCP.BOPAlgo import BOPAlgo_MakerVolume
            from OCP.TopTools import TopTools_ListOfShape
            args = TopTools_ListOfShape()
            for s in solids:
                args.Append(s.wrapped)
            mv = BOPAlgo_MakerVolume()
            mv.SetArguments(args)
            mv.SetIntersect(True)
            mv.SetFuzzyValue(0.01)
            mv.Perform()
            if mv.HasErrors():
                return None
            return mv.Shape()
        except Exception:
            return None

    def _finish_fuse(self, shape, meta, label, n_orig, method):
        """清理融合结果并包装为 Workplane"""
        from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
        try:
            unifier = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
            unifier.Build()
            clean = unifier.Shape()
        except Exception:
            clean = shape
        meta.setdefault("topology_fixes", []).append(
            f"{label}: {n_orig} 实体 → 1 实体 ({method})"
        )
        return cq.Workplane("XY").newObject([cq.Shape.cast(clean)])

    def _robust_union(self, base: cq.Workplane, tool: cq.Workplane) -> cq.Workplane:
        """
        可靠的布尔合并：绕过 CadQuery .union()，直接用 OCC API。
        多级策略: 标准 Fuse → Fuzzy Fuse(0.01) → Fuzzy Fuse(0.1) → CadQuery fallback
        """
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse

        base_shp = base.val().wrapped
        tool_shp = tool.val().wrapped

        for fuzzy in [0.0, 0.01, 0.1]:
            fuser = BRepAlgoAPI_Fuse(base_shp, tool_shp)
            if fuzzy > 0:
                fuser.SetFuzzyValue(fuzzy)
            fuser.Build()
            if fuser.IsDone():
                result_shape = fuser.Shape()
                result_solids = cq.Shape.cast(result_shape).Solids()
                if len(result_solids) == 1:
                    return cq.Workplane("XY").newObject([cq.Shape.cast(result_shape)])

        # 所有 OCC 策略失败 → 回退 CadQuery .union()
        return base.union(tool)

    # -----------------------------
    # geometry primitives
    # -----------------------------
    def _rounded_rect_loft(
        self, side0: float, side1: float, corner_r: float,
        h: float, z0: float = 0.0,
    ) -> cq.Workplane:
        """方形截面 loft：底面矩形 side0 → 顶面矩形 side1，全边圆角"""
        if h <= 0:
            raise ValueError("rounded_rect_loft: h<=0")
        cr = min(corner_r, min(side0, side1) / 2.0 - 0.1)
        cr = max(cr, 0.5)
        body = (
            cq.Workplane("XY")
            .workplane(offset=z0)
            .rect(side0, side0)
            .workplane(offset=h)
            .rect(side1, side1)
            .loft(combine=True)
        )
        return body.edges().fillet(cr)

    def _square_to_circle_loft(
        self, side: float, corner_r: float, circle_r: float,
        h: float, z0: float = 0.0,
    ) -> cq.Workplane:
        """从方形截面过渡到圆形截面（肩部过渡用）"""
        if h <= 0:
            raise ValueError("square_to_circle_loft: h<=0")
        return (
            cq.Workplane("XY")
            .workplane(offset=z0)
            .rect(side, side)
            .workplane(offset=h)
            .circle(circle_r)
            .loft(combine=True)
        )

    def _polygon_loft(
        self, n_sides: int, r0: float, r1: float,
        corner_r: float, h: float, z0: float = 0.0,
    ) -> cq.Workplane:
        """正多边形截面 loft：n边形 外接圆半径 r0 → r1，内建圆角

        使用 placeSketch + regularPolygon.fillet 直接创建圆角多边形，
        替代先画尖角再后置 fillet（后者对 loft 斜面经常失败）。
        """
        if h <= 0:
            raise ValueError("polygon_loft: h<=0")
        if n_sides < 3:
            raise ValueError("polygon_loft: n_sides<3")

        def _mk_sketch(radius, cr):
            max_cr = radius * math.sin(math.pi / n_sides) * 0.9
            eff = min(cr, max_cr)
            eff = max(eff, 0.1)
            return (cq.Sketch()
                    .regularPolygon(radius, n_sides, angle=-90)
                    .vertices().fillet(eff))

        s0 = _mk_sketch(r0, corner_r)
        # 顶部圆角按半径等比缩放 → 截面几何相似 → loft 轮廓线顺直
        corner_r_top = corner_r * (r1 / r0) if r0 > 0 else corner_r
        s1 = _mk_sketch(r1, corner_r_top).moved(cq.Location(cq.Vector(0, 0, h)))
        body = cq.Workplane("XY").workplane(offset=z0).placeSketch(s0, s1).loft()
        return body

    def _tapered_cavity_segmented(
        self, r_inner: float, r_inner_top: float, inner_cr: float,
        wall: float, taper_deg: float, cav: float, eps: float,
        cross_section: str = "round", n_sides: int = 0,
    ) -> "cq.Workplane":
        """分段内腔：下段圆柱（保障螺纹间隙）+ 上段锥度（保障壁厚）。

        薄壁锥形 cap 的内腔如果全程等壁厚缩窄，会在颈部螺纹区过窄。
        分段方案：下段保持 r_inner 不缩，上段再跟随外壁锥度。
        """
        import math as _m
        tan_t = _m.tan(_m.radians(taper_deg)) if taper_deg > 0 else 0

        # 圆柱段高度 = 壁厚归零前（留0.02mm避退化几何）
        if tan_t > 0 and wall < 0.5:
            z_trans = max(1.0, (wall - 0.02) / tan_t)
            z_trans = min(z_trans, cav * 0.3)  # 不超过腔深30%
        else:
            z_trans = 0  # 不需要分段，直接全程锥度

        if z_trans < 1.0:
            # 无需分段，普通单段锥度
            if cross_section == "round":
                return self._loft_frustum(r_inner, r_inner_top, cav + 2 * eps, z0=-eps)
            else:
                return self._polygon_loft(n_sides, r_inner, r_inner_top, inner_cr,
                                          cav + 2 * eps, z0=-eps)

        # 分段构建
        h_lower = z_trans + eps       # 下段: 圆柱
        h_upper = cav - z_trans + eps  # 上段: 锥度

        if cross_section == "round":
            lower = self._loft_frustum(r_inner, r_inner, h_lower, z0=-eps)
            upper = self._loft_frustum(r_inner, r_inner_top, h_upper, z0=z_trans - eps)
        else:
            lower = self._polygon_loft(n_sides, r_inner, r_inner, inner_cr,
                                       h_lower, z0=-eps)
            upper = self._polygon_loft(n_sides, r_inner, r_inner_top, inner_cr,
                                       h_upper, z0=z_trans - eps)
        return lower.union(upper)

    def _polygon_to_circle_loft(
        self, n_sides: int, polygon_r: float, corner_r: float,
        circle_r: float, h: float, z0: float = 0.0,
    ) -> cq.Workplane:
        """从正多边形截面平滑过渡到圆形截面（尖顶/球顶用）

        多截面渐变 loft（placeSketch）：逐步增大多边形圆角至近似圆形，
        再过渡到纯圆截面，避免 polygon→circle 拓扑硬跳变。
        """
        if h <= 0:
            raise ValueError("polygon_to_circle_loft: h<=0")

        n_steps = 5
        sketches = []

        for i in range(n_steps + 1):
            t = i / n_steps  # 0.0 → 1.0
            z = h * t

            # 半径从 polygon_r 平滑过渡到 circle_r
            r = polygon_r + (circle_r - polygon_r) * t
            r = max(r, 0.1)

            # 前 70% 用圆角渐增的多边形，后 30% 用纯圆
            max_cr = r * math.sin(math.pi / n_sides) * 0.95
            use_polygon = (t < 0.7 and r > 1.0 and max_cr > 0.15)

            if use_polygon:
                eff_cr = min(corner_r, max_cr)
                roundness = t / 0.7
                eff_cr = eff_cr + (max_cr - eff_cr) * roundness
                eff_cr = max(eff_cr, 0.1)
                try:
                    s = (cq.Sketch()
                         .regularPolygon(r, n_sides, angle=-90)
                         .vertices().fillet(eff_cr))
                except Exception:
                    s = cq.Sketch().circle(r)
            else:
                s = cq.Sketch().circle(r)

            if z > 0:
                s = s.moved(cq.Location(cq.Vector(0, 0, z)))
            sketches.append(s)

        return (cq.Workplane("XY")
                .workplane(offset=z0)
                .placeSketch(*sketches)
                .loft())

    def _polygon_pointed_loft(
        self, n_sides: int, r0: float, r1: float,
        corner_r: float, body_h: float, cone_h: float,
        tip_r: float,
    ) -> cq.Workplane:
        """一体化多边形 + 尖顶/球顶 loft（无接缝）

        从底部多边形(r0) → 顶部多边形(r1) → 尖顶(tip_r)，
        中间用渐增圆角实现多边形→圆形的平滑过渡。

        Parameters:
            n_sides: 多边形边数
            r0: 底部外接圆半径
            r1: body 顶部外接圆半径
            corner_r: 多边形圆角半径
            body_h: body 段高度
            cone_h: 锥顶段高度
            tip_r: 顶端半径（尖顶≈0.15，球顶≈r1*0.6）
        """
        if body_h <= 0 or cone_h <= 0:
            raise ValueError("polygon_pointed_loft: h<=0")

        def _mk_sketch(radius, cr):
            max_cr = radius * math.sin(math.pi / n_sides) * 0.95
            eff = min(cr, max_cr)
            eff = max(eff, 0.1)
            return (cq.Sketch()
                    .regularPolygon(radius, n_sides, angle=-90)
                    .vertices().fillet(eff))

        sketches = []

        # Section 0: 底部 - 完整多边形
        sketches.append(_mk_sketch(r0, corner_r))

        # Section 1: body 顶部 - 完整多边形（与 body 段共用截面形态）
        s1 = _mk_sketch(r1, corner_r)
        s1 = s1.moved(cq.Location(cq.Vector(0, 0, body_h)))
        sketches.append(s1)

        # Cone 过渡段：从多边形渐变到圆形
        # 使用 4 个中间截面实现平滑过渡
        cone_fracs = [0.2, 0.45, 0.7, 1.0]
        for frac in cone_fracs:
            z = body_h + cone_h * frac
            # 半径从 r1 线性收缩到 tip_r
            r = r1 + (tip_r - r1) * frac
            r = max(r, 0.1)

            max_cr = r * math.sin(math.pi / n_sides) * 0.95
            # 圆角逐步增大：多边形→圆形
            if frac < 0.6 and r > 0.8 and max_cr > 0.15:
                # 前半段：圆角从 corner_r 渐增到 max_cr（趋近圆形）
                blend = frac / 0.6
                eff_cr = corner_r + (max_cr - corner_r) * blend
                eff_cr = min(eff_cr, max_cr)
                eff_cr = max(eff_cr, 0.1)
                try:
                    s = (cq.Sketch()
                         .regularPolygon(r, n_sides, angle=-90)
                         .vertices().fillet(eff_cr))
                except Exception:
                    s = cq.Sketch().circle(r)
            else:
                # 后半段：纯圆形截面
                s = cq.Sketch().circle(r)

            s = s.moved(cq.Location(cq.Vector(0, 0, z)))
            sketches.append(s)

        return (cq.Workplane("XY")
                .placeSketch(*sketches)
                .loft())

    def _loft_frustum(self, r0: float, r1: float, h: float, z0: float = 0.0) -> cq.Workplane:
        """生成圆台/圆柱（r0->r1 loft），底面在 z=z0，顶面在 z=z0+h"""
        if h <= 0:
            raise ValueError("loft_frustum: h<=0")
        if r0 <= 0 or r1 <= 0:
            raise ValueError("loft_frustum: r<=0")
        return (
            cq.Workplane("XY")
            .workplane(offset=z0)
            .circle(r0)
            .workplane(offset=h)
            .circle(r1)
            .loft(combine=True)
        )

    def _ellipse_loft(
        self,
        profile_a: list[tuple[float, float]],
        profile_b: list[tuple[float, float]],
    ) -> cq.Workplane:
        """用椭圆截面 loft 生成非对称瓶身。
        直接使用控制点作为截面（5-7 个），让 OCCT loft 做 B-spline 曲面平滑插值。
        比起 numpy 线性插值 25 截面：速度快 3-5 倍，表面更光滑。
        profile_a: [(r, z), ...] X 方向半径控制点
        profile_b: [(r, z), ...] Y 方向半径控制点（Z 坐标与 A 相同）
        """
        wp = cq.Workplane("XY")
        for i in range(len(profile_a)):
            ra, za = profile_a[i]
            rb, _ = profile_b[i]
            offset = float(za) if i == 0 else float(za - profile_a[i - 1][1])
            rx = max(float(ra), 0.1)
            ry = max(float(rb), 0.1)
            wp = wp.workplane(offset=offset).ellipse(rx, ry)

        return wp.loft(combine=True)

    def _validate_profile_pair(
        self,
        profile_a: list[tuple[float, float]],
        profile_b: list[tuple[float, float]],
        max_r: float,
        min_r_body: float | None = None,
        min_r_z_max: float | None = None,
    ) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        """校验非对称轮廓控制点对。
        - 两组点数必须相同
        - Z 坐标必须一致
        - 首尾 R 值必须相同（圆形配合）
        - 各自通过 _validate_profile 校验
        """
        if len(profile_a) != len(profile_b):
            raise ValueError("非对称轮廓：两组控制点数量必须相同")
        for i, (pa, pb) in enumerate(zip(profile_a, profile_b)):
            if abs(pa[1] - pb[1]) > 0.01:
                raise ValueError(
                    f"非对称轮廓：点 {i} 的 Z 坐标不一致 (A={pa[1]:.2f}, B={pb[1]:.2f})"
                )
        if abs(profile_a[0][0] - profile_b[0][0]) > 0.01:
            raise ValueError(
                f"非对称轮廓：首点 R 必须相同（底部圆形），"
                f"A={profile_a[0][0]:.2f}, B={profile_b[0][0]:.2f}"
            )
        if abs(profile_a[-1][0] - profile_b[-1][0]) > 0.01:
            raise ValueError(
                f"非对称轮廓：末点 R 必须相同（颈部圆形配合），"
                f"A={profile_a[-1][0]:.2f}, B={profile_b[-1][0]:.2f}"
            )
        profile_a, warnings_a = self._validate_profile(profile_a, max_r, min_r_body, min_r_z_max)
        profile_b, warnings_b = self._validate_profile(profile_b, max_r, min_r_body, min_r_z_max)
        return profile_a, profile_b, warnings_a + warnings_b

    def _spline_revolve(self, profile_points: list[tuple[float, float]]) -> cq.Workplane:
        """用 circle loft 生成旋转体（等效于 B-spline 半轮廓旋转 360°）。
        profile_points: [(r, z), ...] 从底部到顶部的半轮廓控制点（至少 3 个）

        实现：先构建精确 B-spline 曲线，沿曲线密集采样 (r, z) 坐标，
        再用等半径圆截面 loft 连接。避免 OCCT 在 revolve 时按 spline knot
        分裂旋转面——分裂会在外壁产生水平几何边缘（可见接缝）。
        """
        import numpy as np

        # Step 1: 构建精确 B-spline 并采样
        n_samples = 40
        try:
            from OCP.gp import gp_Pnt
            from OCP.GeomAPI import GeomAPI_PointsToBSpline
            from OCP.TColgp import TColgp_Array1OfPnt

            arr = TColgp_Array1OfPnt(1, len(profile_points))
            for i, (r, z) in enumerate(profile_points):
                arr.SetValue(i + 1, gp_Pnt(float(r), 0, float(z)))
            bspline = GeomAPI_PointsToBSpline(arr).Curve()

            u0, u1 = bspline.FirstParameter(), bspline.LastParameter()
            sampled = []
            for i in range(n_samples):
                u = u0 + (u1 - u0) * i / (n_samples - 1)
                pt = bspline.Value(u)
                sampled.append((pt.X(), pt.Z()))
        except Exception:
            # Fallback: 线性插值
            zs = np.array([p[1] for p in profile_points])
            rs = np.array([p[0] for p in profile_points])
            z_fine = np.linspace(zs[0], zs[-1], n_samples)
            r_fine = np.interp(z_fine, zs, rs)
            sampled = [(float(r), float(z)) for r, z in zip(r_fine, z_fine)]

        # Step 1.5: 保证 Z 严格递增（B-spline 插值可能产生微小回退）
        cleaned = [sampled[0]]
        for r, z in sampled[1:]:
            if z <= cleaned[-1][1]:
                z = cleaned[-1][1] + 0.01
            cleaned.append((r, z))
        sampled = cleaned

        # Step 2: circle loft 构建闭合实体
        wp = cq.Workplane("XY")
        for i, (r, z) in enumerate(sampled):
            offset = float(z) if i == 0 else float(z - sampled[i - 1][1])
            wp = wp.workplane(offset=offset).circle(max(float(r), 0.1))
        return wp.loft(combine=True)

    def _validate_profile(
        self,
        points: list[tuple[float, float]],
        max_r: float,
        min_r_body: float | None = None,
        min_r_z_max: float | None = None,
    ) -> tuple[list[tuple[float, float]], list[str]]:
        """校验并自动修正轮廓控制点。
        返回 (修正后的点列表, 警告列表)。
        仅在点数不足时抛异常，其他违规自动修正。
        """
        warnings: list[str] = []

        if len(points) < 3:
            raise ValueError("轮廓至少需要 3 个控制点")

        # Z 非单调 → 按 Z 排序 + 合并过近点（间距 < 0.1mm）
        points = sorted(points, key=lambda p: p[1])
        merged = [points[0]]
        for p in points[1:]:
            if p[1] - merged[-1][1] < 0.1:
                merged[-1] = ((merged[-1][0] + p[0]) / 2, p[1])
                warnings.append(f"合并过近点 z≈{p[1]:.1f}")
            else:
                merged.append(p)
        points = merged

        if len(points) < 3:
            raise ValueError("合并过近点后不足 3 个控制点")

        # 半径越界 → 裁剪到合法范围
        for i, (r, z) in enumerate(points):
            new_r = r
            if r <= 0:
                new_r = 0.5
                warnings.append(f"点{i} 半径{r:.2f}→0.5（不允许非正值）")
            if new_r > max_r:
                warnings.append(f"点{i} 半径{new_r:.2f}→{max_r:.2f}（超出包络）")
                new_r = max_r
            if min_r_body is not None:
                if min_r_z_max is None or z < min_r_z_max:
                    if new_r < min_r_body:
                        warnings.append(f"点{i} 半径{new_r:.2f}→{min_r_body:.2f}（壁厚安全）")
                        new_r = min_r_body
            if new_r != r:
                points[i] = (new_r, z)

        return points, warnings

    def _polar_union(self, solids: list[cq.Workplane]) -> cq.Workplane:
        out = solids[0]
        for s in solids[1:]:
            out = out.union(s)
        return out

    # ═══════════════════════════════════════════════════════════════════
    # 共享组件方法（cap / wand 通用）
    # ═══════════════════════════════════════════════════════════════════

    def _build_internal_thread(
        self, body: cq.Workplane, inner_cavity_r: float,
        thr: dict, cavity_depth: float, meta: Dict[str, Any],
    ) -> cq.Workplane:
        """内螺纹生成（cap/wand 共用）

        在 body 内腔壁上生成三角牙型内螺纹。
        支持连续螺纹和分段螺纹两种模式。
        """
        thr_on = bool(thr.get("enabled", False))
        thr_crest = float(thr.get("crest_dia_mm", 18.0))
        thr_depth = float(thr.get("depth_mm", 0.75))
        thr_pitch = float(thr.get("pitch_mm", 2.7))
        thr_turns = int(thr.get("turns", 2))
        thr_lead_angle = float(thr.get("lead_angle_deg", 3.0))
        thr_segmented = bool(thr.get("segmented", False))

        thr_crest_r = thr_crest / 2.0

        if not (thr_on and thr_turns > 0 and thr_pitch > 0):
            meta["thread_status"] = {"requested": bool(thr_on), "attempted": False, "degraded": False}
            return body

        thread_len = thr_pitch * thr_turns
        thread_z0 = 0.5
        thread_z1 = min(thread_z0 + thread_len, cavity_depth - 0.5)
        actual_thread_len = thread_z1 - thread_z0
        actual_turns = max(1, int(actual_thread_len / thr_pitch))

        if actual_thread_len > 1.0:
            t = thr_pitch * 0.4
            thread_root_r = inner_cavity_r - 0.05
            pts = [
                (thread_root_r, -t / 2.0),
                (thread_root_r, t / 2.0),
                (thr_crest_r, 0.0),
            ]

            base_angle = 360.0 * actual_turns
            lead_factor = 1.0 + thr_lead_angle / 90.0
            twist_angle = base_angle * lead_factor

            if thr_segmented:
                gap_angle = float(thr.get("gap_angle_deg", 20.0))

                def _make_seg_thread() -> cq.Workplane:
                    segments_per_turn = 2
                    seg_angle = (360.0 - segments_per_turn * gap_angle) / segments_per_turn
                    seg_len = thr_pitch * (seg_angle / 360.0)
                    all_segs = []
                    for turn_i in range(actual_turns):
                        for seg_i in range(segments_per_turn):
                            start_angle = turn_i * 360.0 + seg_i * (seg_angle + gap_angle)
                            z_offset = thread_z0 + (start_angle / 360.0) * thr_pitch
                            if z_offset + seg_len > thread_z0 + actual_thread_len:
                                continue
                            angle_rad = math.radians(start_angle)
                            cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
                            rotated_pts = [(r * cos_a - y * sin_a, r * sin_a + y * cos_a)
                                           for (r, y) in pts]
                            seg = (cq.Workplane("XY").workplane(offset=z_offset)
                                   .polyline(rotated_pts).close()
                                   .twistExtrude(seg_len, angleDegrees=seg_angle))
                            all_segs.append(seg)
                    if not all_segs:
                        return body
                    thread_solid = all_segs[0]
                    for s in all_segs[1:]:
                        thread_solid = thread_solid.union(s)
                    return body.union(thread_solid)

                body = self.try_feature(meta, "inner_thread_segmented", _make_seg_thread, body)
            else:
                def _make_thread() -> cq.Workplane:
                    thread_solid = (cq.Workplane("XY").workplane(offset=thread_z0)
                                    .polyline(pts).close()
                                    .twistExtrude(actual_thread_len, angleDegrees=twist_angle))
                    return body.union(thread_solid)

                body = self.try_feature(meta, "inner_thread", _make_thread, body)

        # 碎片清理
        _solids = body.val().Solids()
        if len(_solids) > 1:
            _vols = [(abs(s.Volume()), s) for s in _solids]
            _vols.sort(key=lambda x: x[0], reverse=True)
            body = cq.Workplane("XY").newObject([_vols[0][1]])
            meta.setdefault("topology_fixes", []).append(
                f"thread_cleanup: 清理 {len(_solids)-1} 个螺纹碎片"
            )

        meta["thread_status"] = {
            "requested": True, "attempted": True,
            "degraded": any("thread" in d.get("feature", "") for d in meta.get("degraded", [])),
        }
        return body

    def _build_stem_rod(
        self, body: cq.Workplane, cap_h: float,
        stem: dict, inner_depth: float,
        cap_taper_deg: float, meta: Dict[str, Any],
    ) -> tuple:
        """杆身生成（cap/wand 共用）

        从盖顶向下延伸杆身。返回 (modified_body, stem_bottom_z)。
        """
        stem_r = float(stem.get("diameter_mm", 4.5)) / 2.0
        stem_len = float(stem.get("length_mm", 50.0))
        stem_profile = str(stem.get("profile", "round"))
        stem_taper = float(stem.get("taper_ratio", 1.0))
        stem_wall = float(stem.get("wall_mm", 0.8))

        eps = 0.05
        _stem_ol = max(eps, min(cap_h * 0.04, 2.0)) if cap_taper_deg > 1 else 0.5
        stem_top_z = cap_h
        stem_bottom_z = stem_top_z - stem_len

        if stem_profile == "tapered" and stem_taper < 1.0:
            stem_solid = self._loft_frustum(
                stem_r * stem_taper, stem_r, stem_len + _stem_ol, z0=stem_bottom_z)
        elif stem_profile == "oval":
            stem_solid = (cq.Workplane("XY").workplane(offset=stem_bottom_z)
                          .ellipse(stem_r, stem_r * 0.7)
                          .extrude(stem_len + _stem_ol))
        else:
            stem_solid = (cq.Workplane("XY").workplane(offset=stem_bottom_z)
                          .circle(stem_r).extrude(stem_len + _stem_ol))

        body = self._robust_union(body, stem_solid)

        # 空心杆腔
        if stem_wall > 0 and stem_wall < stem_r:
            inner_stem_r = stem_r - stem_wall
            if inner_stem_r > 0.5 and inner_depth > 0:
                stem_cavity = (cq.Workplane("XY")
                               .workplane(offset=stem_top_z - inner_depth)
                               .circle(inner_stem_r).extrude(inner_depth + eps))
                body = body.cut(stem_cavity)

        return body, stem_bottom_z

    def _build_seal_ring(
        self, body: cq.Workplane, cavity_depth: float,
        seal: dict, stem_r: float,
        cap_taper_deg: float, shell_r_bottom: float,
        meta: Dict[str, Any],
    ) -> cq.Workplane:
        """气密环生成（cap/wand 共用）"""
        seal_r = float(seal.get("od_mm", 12.0)) / 2.0
        seal_h = float(seal.get("height_mm", 2.0))
        seal_style = str(seal.get("style", "flat"))

        eps = 0.05
        seal_z0 = cavity_depth - seal_h
        if seal_z0 < 0:
            seal_z0 = 0

        # 锥盖模式：气密环不超出该高度的外壳半径
        if cap_taper_deg > 0:
            shell_r_at_seal = shell_r_bottom - math.tan(math.radians(cap_taper_deg)) * seal_z0
            seal_r = min(seal_r, shell_r_at_seal - 0.5)
            seal_r = max(seal_r, stem_r + 1.0)

        _seal_ol = max(eps, min(cavity_depth * 0.04, 2.0)) if cap_taper_deg > 1 else 0.5

        if seal_style == "conical":
            seal_ring = self._loft_frustum(seal_r * 0.95, seal_r, seal_h + _seal_ol, z0=seal_z0)
        elif seal_style == "ring":
            seal_ring = (cq.Workplane("XY").workplane(offset=seal_z0)
                         .circle(seal_r).circle(seal_r - 1.0)
                         .extrude(seal_h + _seal_ol))
        else:
            seal_ring = (cq.Workplane("XY").workplane(offset=seal_z0)
                         .circle(seal_r).extrude(seal_h + _seal_ol))

        # 杆身通道预孔
        seal_hole_r = stem_r + 0.5
        seal_passage = (cq.Workplane("XY").workplane(offset=seal_z0 - eps)
                        .circle(seal_hole_r).extrude(seal_h + _seal_ol + 2 * eps))
        seal_ring = seal_ring.cut(seal_passage)

        return self._robust_union(body, seal_ring)

    def _build_brush_head(
        self, body: cq.Workplane, brush_z0: float,
        stem_r: float, brush: dict,
        stem_taper_factor: float, meta: Dict[str, Any],
    ) -> cq.Workplane:
        """刷头生成（cap/wand 共用）"""
        brush_type = str(brush.get("type", "doe_foot"))
        brush_len = float(brush.get("length_mm", 12.0))
        brush_w = float(brush.get("width_mm", 8.0))
        brush_t = float(brush.get("thickness_mm", 3.0))

        connect_r = stem_r * stem_taper_factor

        if brush_type == "doe_foot":
            def _make():
                head = (cq.Workplane("XY").workplane(offset=brush_z0)
                        .ellipse(brush_w / 2.0, brush_t / 2.0)
                        .workplane(offset=brush_len).circle(connect_r)
                        .loft(combine=True))
                return body.union(head)
            return self.try_feature(meta, "brush_doe_foot", _make, body)

        elif brush_type == "silicone_spatula":
            def _make():
                head = (cq.Workplane("XY").workplane(offset=brush_z0)
                        .rect(brush_w, brush_t)
                        .workplane(offset=brush_len * 0.7).circle(stem_r)
                        .loft(combine=True))
                return body.union(head)
            return self.try_feature(meta, "brush_spatula", _make, body)

        elif brush_type == "pointed":
            def _make():
                tip_r = 0.3
                mid_r = brush_w / 3.0
                lower = (cq.Workplane("XY").workplane(offset=brush_z0)
                         .circle(tip_r)
                         .workplane(offset=brush_len * 0.4).circle(mid_r)
                         .loft(combine=True))
                upper = (cq.Workplane("XY").workplane(offset=brush_z0 + brush_len * 0.4)
                         .circle(mid_r)
                         .workplane(offset=brush_len * 0.6).circle(connect_r)
                         .loft(combine=True))
                return body.union(lower).union(upper)
            return self.try_feature(meta, "brush_pointed", _make, body)

        elif brush_type == "angled":
            def _make():
                head = (cq.Workplane("XY").workplane(offset=brush_z0)
                        .ellipse(brush_w / 2.0, brush_w / 2.0 * 0.6)
                        .workplane(offset=brush_len).circle(connect_r)
                        .loft(combine=True))
                return body.union(head)
            return self.try_feature(meta, "brush_angled", _make, body)

        else:
            def _make():
                head = self._loft_frustum(brush_w / 4.0, stem_r, brush_len, z0=brush_z0)
                return body.union(head)
            return self.try_feature(meta, "brush_fiber", _make, body)

    # -----------------------------
    # build_cap (重构版 - 无冲突参数)
    # -----------------------------
    def build_cap(self, p: Dict[str, Any], meta: Dict[str, Any]) -> cq.Workplane:
        """
        瓶盖建模（重构版 - 无内螺纹）
        - 参数按重要性排序：外径 > 总高 > 内径 > 内腔深
        - 壁厚自动计算：wall = (OD - ID) / 2，避免参数冲突
        - 无内螺纹设计，依靠刷杆内螺纹与瓶身外螺纹配合
        """
        # ---- main dims (A. 外形尺寸) ----
        OD = float(p["outer_od_mm"])
        H = float(p["height_mm"])
        taper_deg = float(p.get("taper_deg", 0.0))
        top_shape = str(p.get("top_shape", "flat"))
        cross_section = str(p.get("cross_section", "round"))
        corner_radius_mm = float(p.get("corner_radius_mm", 3.0))

        # ---- inner cavity (B. 内腔配合) ----
        ID = float(p["inner_id_mm"])
        cav = float(p["cavity_depth_mm"])
        # 壁厚由 OD 和 ID 自动计算，不从参数读取
        wall = (OD - ID) / 2.0
        edge_fillet = float(p.get("edge_fillet_mm", 0.5))

        # grip (防滑纹)
        grip = p.get("grip", {}) or {}
        grip_style = str(grip.get("style", "none"))
        grip_count = int(grip.get("count", 24))
        grip_depth = float(grip.get("depth_mm", 0.3))

        # ---- 计算锥度（含最小拔模角保证） ----
        # 注塑件最低要求 0.5° 拔模角，确保脱模
        MFG_MIN_DRAFT = 0.5
        eff_taper = max(taper_deg, MFG_MIN_DRAFT)
        if taper_deg < MFG_MIN_DRAFT:
            meta.setdefault("mfg_adjustments", []).append(
                f"cap外壁拔模角从{taper_deg:.1f}°提升至{MFG_MIN_DRAFT}°（注塑最低要求）"
            )

        taper_rad = math.radians(eff_taper)
        delta_r = math.tan(taper_rad) * H  # 单侧半径变化量
        OD_top = max(OD - 2 * delta_r, OD * 0.3)  # 直径变化 = 2×半径变化

        # ★ 层2A: 非圆截面需更大顶部尺寸，防止壁厚退化
        if cross_section == "square":
            OD_top = max(OD_top, 10.0)
        elif _is_polygon(cross_section):
            OD_top = max(OD_top, 8.0)
        # 如果守卫生效，记录实际有效锥度
        actual_delta_r = (OD - OD_top) / 2.0
        if actual_delta_r < delta_r - 0.01:
            eff_taper_adj = math.degrees(math.atan(actual_delta_r / H)) if H > 0 else 0
            meta.setdefault("mfg_adjustments", []).append(
                f"cap锥度从{taper_deg:.1f}°降至{eff_taper_adj:.1f}°(顶部最小尺寸约束)"
            )

        r0 = OD / 2.0  # 底部半径（开口侧）
        r1 = OD_top / 2.0  # 顶部半径
        r_inner = ID / 2.0

        eps = 0.15  # 重叠量

        # ---- Step 1: build outer shell ----
        profile_mode = str(p.get("profile_mode", "classic"))

        if profile_mode == "spline" and cross_section == "square":
            # ========== 方形截面 + spline：多截面方形 loft ==========
            import json
            from products.lip_gloss.derived_params import generate_default_cap_profile

            raw = p.get("profile_points_json", "[]")
            pts = json.loads(raw) if isinstance(raw, str) else raw
            profile_pts = [(float(pt[0]), float(pt[1])) for pt in pts]

            if len(profile_pts) < 3:
                profile_pts = generate_default_cap_profile(r0, r1, H)

            profile_pts[0] = (profile_pts[0][0], 0.0)
            profile_pts[-1] = (profile_pts[-1][0], H)

            min_r = r_inner + 0.3
            profile_pts, _cap_sq_warnings = self._validate_profile(
                profile_pts, OD / 2.0 * 1.05,
                min_r_body=min_r, min_r_z_max=cav,
            )
            if _cap_sq_warnings:
                meta.setdefault("profile_warnings", []).extend(_cap_sq_warnings)

            # 用控制点驱动多截面 rounded-rect loft
            wp = cq.Workplane("XY")
            for _i, (_r, _z) in enumerate(profile_pts):
                _side = _r * 2
                _cr = min(corner_radius_mm, _side * 0.45)
                _cr = max(_cr, 0.5)
                _off = _z if _i == 0 else _z - profile_pts[_i - 1][1]
                wp = (wp.workplane(offset=_off)
                      .sketch().rect(_side, _side).vertices().fillet(_cr).finalize())
            cap = wp.loft(combine=True)

            meta["profile_mode"] = "spline"
            meta["cross_section"] = "square"
            meta["profile_points"] = profile_pts

        elif profile_mode == "spline":
            # ========== SPLINE 模式：曲线旋转体 ==========
            import json
            from products.lip_gloss.derived_params import generate_default_cap_profile

            raw = p.get("profile_points_json", "[]")
            pts = json.loads(raw) if isinstance(raw, str) else raw
            profile_pts = [(float(pt[0]), float(pt[1])) for pt in pts]

            if len(profile_pts) < 3:
                profile_pts = generate_default_cap_profile(r0, r1, H)

            profile_pts[0] = (profile_pts[0][0], 0.0)
            profile_pts[-1] = (profile_pts[-1][0], H)

            min_r = r_inner + 0.3
            profile_pts, _cap_sp_warnings = self._validate_profile(
                profile_pts, OD / 2.0 * 1.05,
                min_r_body=min_r, min_r_z_max=cav,
            )
            if _cap_sp_warnings:
                meta.setdefault("profile_warnings", []).extend(_cap_sp_warnings)

            cap = self._spline_revolve(profile_pts)

            meta["profile_mode"] = "spline"
            meta["profile_points"] = profile_pts
        elif cross_section == "square":
            # ========== 方形截面模式 ==========
            meta["profile_mode"] = "classic"
            meta["cross_section"] = "square"
            side_bottom = OD  # OD 当作方形边长
            side_top = OD_top
            cap = self._rounded_rect_loft(side_bottom, side_top, corner_radius_mm, H, z0=0.0)
        elif _is_polygon(cross_section):
            # ========== 多边形截面模式（triangle/hexagon/octagon）==========
            meta["profile_mode"] = "classic"
            meta["cross_section"] = cross_section
            n = _n_sides(cross_section)

            if top_shape in ("pointed", "dome"):
                # ★ 一体化 loft：body + pointed/dome 无接缝，消除 union 边界
                if top_shape == "pointed":
                    if eff_taper > 2:
                        _cone_h = max(3.0, min(r1 * 1.5, H * 0.5))
                    else:
                        _cone_h = max(1.5, min(r1 * 0.7, H * 0.3))
                    _tip_r = 0.15
                else:  # dome
                    _cone_h = max(1.0, min(r1 * 0.35, H * 0.25))
                    _tip_r = r1 * 0.6
                cap = self._polygon_pointed_loft(
                    n, r0, r1, corner_radius_mm, H, _cone_h, _tip_r)
                meta["_top_shape_integrated"] = True
                # 更新 H 用于后续内腔计算（含锥顶）
                H = H + _cone_h
            else:
                cap = self._polygon_loft(n, r0, r1, corner_radius_mm, H, z0=0.0)
        else:
            meta["profile_mode"] = "classic"
            meta["cross_section"] = "round"
            cap = self._loft_frustum(r0, r1, H, z0=0.0)

        # ---- Step 2: edge fillets (non-critical, enforce minimums) ----
        # 注塑件最低圆角：外角 R≥0.5mm，内角 R≥0.3mm
        MIN_EXT_FILLET = 0.5
        MIN_INT_FILLET = 0.3
        if cross_section == "square" or _is_polygon(cross_section):
            # 非圆截面：loft 已内置圆角处理，跳过额外 fillet
            pass
        elif profile_mode == "spline":
            # spline 模式：用极小 fillet 柔化锐边，避免大 fillet 在
            # B-spline 旋转面上形成明显的水平接缝（fillet 面与 spline 面交界）
            _tiny = 0.3
            cap = self.try_feature(
                meta, "bottom_fillet",
                lambda: cap.edges("<Z").fillet(_tiny),
                cap
            )
            cap = self.try_feature(
                meta, "top_fillet",
                lambda: cap.edges(">Z").fillet(_tiny),
                cap
            )
        else:
            eff_fillet = max(edge_fillet, MIN_EXT_FILLET)
            fillet_r = min(eff_fillet, min(OD, OD_top) * 0.15)
            fillet_r = max(fillet_r, MIN_EXT_FILLET)
            # 底边圆角（内角，稍小）
            cap = self.try_feature(
                meta, "bottom_fillet",
                lambda: cap.edges("<Z").fillet(max(fillet_r * 0.8, MIN_INT_FILLET)),
                cap
            )
            # 顶边圆角（外角）
            cap = self.try_feature(
                meta, "top_fillet",
                lambda: cap.edges(">Z").fillet(fillet_r),
                cap
            )

        # ---- Step 2b: top shape (dome / pointed) ----
        # 多边形一体化 loft 已在 Step 1 处理完毕，跳过
        if meta.get("_top_shape_integrated"):
            pass
        elif top_shape == "dome":
            # 获取顶部有效半径（spline 模式取最后一个控制点半径）
            _dome_top_r = r1
            if profile_mode == "spline" and "profile_points" in meta:
                _dome_top_r = meta["profile_points"][-1][0]
            # 球冠高度 = 顶部半径的 35%，确保视觉明显
            _dome_h = max(1.0, min(_dome_top_r * 0.35, H * 0.25))

            # 方形/三角截面 fillet 会侵蚀顶面，overlap 必须 > fillet 半径
            if cross_section == "square" or _is_polygon(cross_section):
                _dome_overlap = max(corner_radius_mm * 0.6, 1.5)
            else:
                _dome_overlap = 0.5
            if cross_section == "square":
                # 方形截面 dome：用 loft 从方形顶面过渡到圆形球冠
                _sq_side = r1 * 2  # 方形边长 ≈ 顶部外径
                _cr = min(corner_radius_mm, _sq_side * 0.45)
                def _do_square_dome():
                    dome_solid = self._square_to_circle_loft(
                        _sq_side, _cr, _dome_top_r * 0.6,
                        _dome_h + _dome_overlap, z0=H - _dome_overlap
                    )
                    return self._robust_union(cap, dome_solid)
                cap = self.try_feature(meta, "top_dome_square", _do_square_dome, cap)
            elif _is_polygon(cross_section):
                # 多边形截面 dome：多边形→圆形过渡
                _poly_n = _n_sides(cross_section)
                def _do_poly_dome():
                    dome_solid = self._polygon_to_circle_loft(
                        _poly_n, r1, corner_radius_mm, _dome_top_r * 0.6,
                        _dome_h + _dome_overlap, z0=H - _dome_overlap
                    )
                    return self._robust_union(cap, dome_solid)
                cap = self.try_feature(meta, f"top_dome_{cross_section}", _do_poly_dome, cap)
            else:
                # 圆形/spline：threePointArc revolve 生成真球冠
                def _do_dome():
                    _arc_mid_r = _dome_top_r * 0.707  # 45° 处
                    _h0 = H - _dome_overlap
                    _arc_mid_z = _h0 + (_dome_h + _dome_overlap) * 0.707
                    dome_solid = (
                        cq.Workplane("XZ")
                        .moveTo(0, _h0)
                        .lineTo(_dome_top_r, _h0)
                        .threePointArc((_arc_mid_r, _arc_mid_z), (0, H + _dome_h))
                        .close()
                        .revolve(360, (0, 0), (0, 1))
                    )
                    return self._robust_union(cap, dome_solid)
                cap = self.try_feature(meta, "top_dome", _do_dome, cap)

        elif top_shape == "pointed":
            _pt_top_r = r1
            if profile_mode == "spline" and "profile_points" in meta:
                _pt_top_r = meta["profile_points"][-1][0]
            if eff_taper > 2:
                # 锥盖：更高的锥顶，斜率更接近盖主体，视觉连续
                cone_h = max(3.0, min(_pt_top_r * 1.5, H * 0.5))
            else:
                cone_h = max(1.5, min(_pt_top_r * 0.7, H * 0.3))
            tip_r = 0.15  # 避免无穷尖点

            if cross_section == "square" or _is_polygon(cross_section):
                _pt_overlap = max(corner_radius_mm * 0.6, 1.5)
            else:
                _pt_overlap = 0.5
            if cross_section == "square":
                # 方形截面 pointed：方形底→极小圆形顶 loft
                _sq_side = r1 * 2
                _cr = min(corner_radius_mm, _sq_side * 0.45)
                def _do_square_pointed():
                    pt_solid = self._square_to_circle_loft(
                        _sq_side, _cr, tip_r,
                        cone_h + _pt_overlap, z0=H - _pt_overlap
                    )
                    return self._robust_union(cap, pt_solid)
                cap = self.try_feature(meta, "top_pointed_square", _do_square_pointed, cap)
            elif _is_polygon(cross_section):
                # 多边形截面 pointed：多边形底→极小圆形顶 loft
                _poly_n = _n_sides(cross_section)
                def _do_poly_pointed():
                    pt_solid = self._polygon_to_circle_loft(
                        _poly_n, r1, corner_radius_mm, tip_r,
                        cone_h + _pt_overlap, z0=H - _pt_overlap
                    )
                    return self._robust_union(cap, pt_solid)
                cap = self.try_feature(meta, f"top_pointed_{cross_section}", _do_poly_pointed, cap)
            else:
                # 圆形/spline：revolve 三角轮廓
                _h0 = H - _pt_overlap
                cone = (
                    cq.Workplane("XZ")
                    .moveTo(0, _h0)
                    .lineTo(_pt_top_r, _h0)
                    .lineTo(tip_r, H + cone_h)
                    .lineTo(0, H + cone_h)
                    .close()
                    .revolve(360, (0, 0), (0, 1))
                )
                cap = self.try_feature(
                    meta, "top_pointed",
                    lambda: self._robust_union(cap, cone),
                    cap
                )

        # ---- Step 3: cavity cut (critical) ----
        if cav <= 0 or cav >= H:
            raise RuntimeError(f"cavity_depth_mm invalid: cav={cav}, H={H}")

        if profile_mode == "spline" and "profile_points" in meta:
            # spline 模式：限制内腔高度，确保外壁有足够壁厚
            # 找到外壁半径首次降至 r_inner + MIN_WALL 以下的 Z
            _MIN_WALL = 0.8
            _safe_r = r_inner + _MIN_WALL
            _prof_pts = meta["profile_points"]
            _eff_cav = cav
            for _i in range(len(_prof_pts) - 1):
                _pr0, _pz0 = _prof_pts[_i]
                _pr1, _pz1 = _prof_pts[_i + 1]
                if _pr0 >= _safe_r and _pr1 < _safe_r:
                    _frac = (_pr0 - _safe_r) / (_pr0 - _pr1) if _pr0 > _pr1 else 0
                    _eff_cav = min(_eff_cav, _pz0 + _frac * (_pz1 - _pz0) - 1.0)
                    break
                elif _pr0 < _safe_r:
                    _eff_cav = min(_eff_cav, _pz0 - 1.0)
                    break
            _eff_cav = max(_eff_cav, cav * 0.5)  # 至少保留一半内腔深度

            # 内腔顶部半径随外壁收窄（保持壁厚）
            # 在 _eff_cav 处找外壁半径
            _r_at_top = r0  # 默认
            for _i in range(len(_prof_pts) - 1):
                _pr0, _pz0 = _prof_pts[_i]
                _pr1, _pz1 = _prof_pts[_i + 1]
                if _pz0 <= _eff_cav <= _pz1:
                    _t = (_eff_cav - _pz0) / (_pz1 - _pz0) if _pz1 > _pz0 else 0
                    _r_at_top = _pr0 + _t * (_pr1 - _pr0)
                    break
            r_inner_top = _r_at_top - _MIN_WALL
            r_inner_top = max(r_inner_top, r_inner * 0.6)

            if abs(r_inner - r_inner_top) > 0.1:
                cav_solid = self._loft_frustum(r_inner, r_inner_top, _eff_cav + 2 * eps, z0=-eps)
            else:
                cav_solid = (
                    cq.Workplane("XY")
                    .workplane(offset=-eps)
                    .circle(r_inner)
                    .extrude(_eff_cav + 2 * eps)
                )
            meta["effective_cavity_depth"] = _eff_cav
        elif cross_section == "square":
            # 方形内腔：边长 = ID，圆角 = 外圆角 - 壁厚（至少 0.5）
            inner_side = ID
            inner_cr = max(0.5, corner_radius_mm - wall)
            if taper_deg > 0:
                # 锥度模式：内腔顶部也收窄，用 _rounded_rect_loft 统一处理
                # 等壁厚锥度：内腔边长 = 腔顶高度处外壁边长 - 2×壁厚
                _tan_t = math.tan(math.radians(eff_taper))
                _outer_side_at_cav = OD - 2 * _tan_t * cav
                inner_side_top = _outer_side_at_cav - 2 * wall
                if inner_side_top <= 0:
                    cav = (OD - 4 * wall) / (2 * _tan_t)
                    _outer_side_at_cav = OD - 2 * _tan_t * cav
                    inner_side_top = _outer_side_at_cav - 2 * wall
                    meta.setdefault("mfg_adjustments", []).append(
                        f"内腔深度缩短至{cav:.1f}mm（锥度收窄限制）")
                cav_solid = self._rounded_rect_loft(
                    inner_side, inner_side_top, inner_cr, cav + 2 * eps, z0=-eps
                )
            else:
                cav_solid = (
                    cq.Workplane("XY").workplane(offset=-eps)
                    .rect(inner_side, inner_side)
                    .extrude(cav + 2 * eps)
                )
                cav_solid = cav_solid.edges("|Z").fillet(inner_cr)
        elif _is_polygon(cross_section):
            # 多边形内腔：内切圆半径 = r_inner，壁厚 = wall
            n = _n_sides(cross_section)
            inner_cr = max(0.3, corner_radius_mm - wall)
            if taper_deg > 0:
                # 等壁厚锥度：内腔顶部 = 腔顶高度处外壁半径 - 壁厚
                _tan_t = math.tan(math.radians(eff_taper))
                _r_outer_at_cav = r0 - _tan_t * cav
                r_inner_top = _r_outer_at_cav - wall
                if r_inner_top <= 0:
                    # 外壁已收窄到无法容纳内腔 → 缩短腔深
                    cav = (r0 - 2 * wall) / _tan_t
                    _r_outer_at_cav = r0 - _tan_t * cav
                    r_inner_top = _r_outer_at_cav - wall
                    meta.setdefault("mfg_adjustments", []).append(
                        f"内腔深度缩短至{cav:.1f}mm（锥度收窄限制）")
                cav_solid = self._tapered_cavity_segmented(
                    r_inner, r_inner_top, inner_cr, wall, eff_taper,
                    cav, eps, cross_section=cross_section, n_sides=n)
            else:
                cav_solid = self._polygon_loft(n, r_inner, r_inner, inner_cr, cav + 2 * eps, z0=-eps)
        elif taper_deg > 0:
            # 等壁厚锥度：内腔顶部 = 腔顶高度处外壁半径 - 壁厚
            _tan_t = math.tan(math.radians(eff_taper))
            _r_outer_at_cav = r0 - _tan_t * cav
            r_inner_top = _r_outer_at_cav - wall
            if r_inner_top <= 0:
                cav = (r0 - 2 * wall) / _tan_t
                _r_outer_at_cav = r0 - _tan_t * cav
                r_inner_top = _r_outer_at_cav - wall
                meta.setdefault("mfg_adjustments", []).append(
                    f"内腔深度缩短至{cav:.1f}mm（锥度收窄限制）")
            cav_solid = self._tapered_cavity_segmented(
                r_inner, r_inner_top, 0, wall, eff_taper,
                cav, eps, cross_section="round")
        else:
            cav_solid = (
                cq.Workplane("XY")
                .workplane(offset=-eps)
                .circle(r_inner)
                .extrude(cav + 2 * eps)
            )

        cap = cap.cut(cav_solid)

        # ---- Step 3b: 内底导入倒角（lead-in chamfer）----
        # 真实瓶盖内壁底部有锥形倒角，使 cap 能更低地套住瓶身肩部
        # 从 inner_id 渐变到 outer_od - CHAMFER_WALL（仅留极薄壁厚边缘）
        # spline 模式下跳过：薄壁曲面不支持激进倒角
        CHAMFER_WALL = 0.15  # 倒角边缘最小壁厚 mm
        if wall <= 0.5:
            # 薄壁 body_top 模式：减小倒角壁厚避免切穿
            CHAMFER_WALL = min(0.10, wall * 0.2)
        # 动态倒角高度：覆盖瓶身肩部+颈部重叠区域
        # 厚壁 cap（wall ≥ 1.5mm）: 加大倒角覆盖完整重叠区，防止瓶颈干涉
        if wall >= 1.5:
            CHAMFER_H = max(5.0, min(cav * 0.50, 30.0))
        else:
            CHAMFER_H = max(5.0, min(cav * 0.30, 20.0))
        r_chamfer_bottom = r0 - CHAMFER_WALL  # r0 = OD/2（底部外半径）

        # ★ 锥度感知: 锥形 cap 外壁随高度缩小，倒角高度必须受限
        # 否则内腔会在某个高度超过外壁 → 切穿外壁 → cap 出现大洞
        if eff_taper > 0.5 and r_chamfer_bottom > r_inner:
            tan_t = math.tan(math.radians(eff_taper))
            wall_at_z0 = r0 - r_inner  # 名义壁厚（底部）
            # 在 Z=CHAMFER_H 处: wall = wall_at_z0 - tan_t * CHAMFER_H
            # 必须 ≥ MIN_WALL_CH_TOP 保证外壳完整
            MIN_WALL_CH_TOP = 0.3
            max_ch_h = (wall_at_z0 - MIN_WALL_CH_TOP) / tan_t if tan_t > 0 else 999
            if max_ch_h < 2.0:
                # 壁太薄，完全跳过倒角
                CHAMFER_H = 0
                r_chamfer_bottom = 0
            else:
                CHAMFER_H = min(CHAMFER_H, max_ch_h)
        if profile_mode != "spline" and r_chamfer_bottom > r_inner and CHAMFER_H > 0:
            if cross_section == "round":
                chamfer_cut = self._loft_frustum(
                    r_chamfer_bottom, r_inner, CHAMFER_H,
                    z0=-eps
                )
            elif _is_polygon(cross_section):
                n = _n_sides(cross_section)
                chamfer_cr = max(0.1, corner_radius_mm - CHAMFER_WALL)
                chamfer_cut = self._polygon_loft(
                    n, r_chamfer_bottom, r_inner, chamfer_cr, CHAMFER_H,
                    z0=-eps
                )
            elif cross_section == "square":
                chamfer_side_bot = 2 * r_chamfer_bottom
                chamfer_side_top = ID
                chamfer_cr = max(0.3, corner_radius_mm - CHAMFER_WALL)
                chamfer_cut = self._rounded_rect_loft(
                    chamfer_side_bot, chamfer_side_top, chamfer_cr,
                    CHAMFER_H, z0=-eps
                )
            else:
                chamfer_cut = None
            if chamfer_cut is not None:
                cap = self.try_feature(
                    meta, "inner_lead_chamfer",
                    lambda: cap.cut(chamfer_cut),
                    cap
                )

        # 开口倒角
        open_chamfer = min(0.5, wall * 0.15)
        if open_chamfer > 0.1:
            cap = self.try_feature(
                meta, "opening_chamfer",
                lambda: cap.faces("<Z").edges().chamfer(open_chamfer),
                cap
            )

        # ---- Step 4: grip texture (non-critical) ----
        _grip_n_faces = _n_sides(cross_section) if _is_polygon(cross_section) else (4 if cross_section == "square" else 0)
        if _grip_n_faces > 0 and grip_style not in ("none", "smooth"):
            # 非圆截面：在各个平面上做线性竖向沟槽
            def _do_square_grip() -> cq.Workplane:
                _half_side = r0  # 方形半边长 ≈ r0
                _g_z0 = 2.0
                _g_h = max(3.0, H - 4.0)
                _g_depth = max(grip_depth, 0.1)
                _g_w = max(0.5, _half_side * 0.04)
                _n = min(max(grip_count, 4), 24)
                # 沿各面做沟槽
                _per_face = max(2, _n // _grip_n_faces)
                _face_width = _half_side * 2 * 0.8  # 面宽 80% 区域
                _spacing = _face_width / (_per_face + 1)
                all_cuts = []
                for face_i in range(_grip_n_faces):
                    _angle = face_i * (360.0 / _grip_n_faces)
                    for gi in range(_per_face):
                        _offset = -_face_width / 2 + _spacing * (gi + 1)
                        groove = (
                            cq.Workplane("XY")
                            .workplane(offset=_g_z0)
                            .center(_half_side + _g_depth / 2, _offset)
                            .rect(_g_depth, _g_w)
                            .extrude(_g_h)
                        )
                        groove = groove.rotate((0, 0, 0), (0, 0, 1), _angle)
                        all_cuts.append(groove)
                cutter = all_cuts[0]
                for c in all_cuts[1:]:
                    cutter = cutter.union(c)
                return cap.cut(cutter)
            cap = self.try_feature(meta, "grip_square", _do_square_grip, cap)

        elif profile_mode == "spline" and grip_style not in ("none", "smooth"):
            # spline 模式：使用固定半径径向切割 + try_feature 兜底
            # 取外壁中段平均半径作为切割半径
            _spline_r = r0  # 用底部半径（最大处）
            def _do_spline_grip() -> cq.Workplane:
                _g_depth = max(grip_depth, 0.1)
                _g_w = max(0.5, OD * 0.02)
                _g_z0 = 2.0
                _g_h = max(3.0, H - 4.0)
                _n = min(max(grip_count, 6), 36)
                _surf_r = _spline_r - _g_depth / 2.0
                single = (
                    cq.Workplane("XY")
                    .workplane(offset=_g_z0)
                    .center(_surf_r, 0)
                    .rect(_g_depth, _g_w)
                    .extrude(_g_h)
                )
                cuts = [single.rotate((0, 0, 0), (0, 0, 1), 360.0 * i / _n)
                        for i in range(_n)]
                cutter = self._polar_union(cuts)
                return cap.cut(cutter)
            cap = self.try_feature(meta, "grip_spline", _do_spline_grip, cap)
        elif grip_style == "ribs" and grip_count >= 6 and grip_depth > 0.05:
            def _do_ribs() -> cq.Workplane:
                rib_w = max(0.5, OD * 0.02)  # 筋宽度自动计算
                rib_z0 = 2.0  # 起始高度
                rib_h = max(3.0, H - 4.0)  # 覆盖高度
                surf_r = r0 - grip_depth / 2.0

                single_rib = (
                    cq.Workplane("XY")
                    .workplane(offset=rib_z0)
                    .center(surf_r, 0)
                    .rect(grip_depth, rib_w)
                    .extrude(rib_h)
                )

                ribs = [single_rib.rotate((0, 0, 0), (0, 0, 1), 360.0 * i / grip_count)
                        for i in range(grip_count)]
                cutter = self._polar_union(ribs)
                return cap.cut(cutter)

            cap = self.try_feature(meta, "grip_ribs", _do_ribs, cap)

        elif grip_style == "knurl" and grip_depth > 0.05:
            def _do_knurl() -> cq.Workplane:
                # 简化版滚花：用斜向竖筋代替复杂的螺旋交叉
                # 这样可以大幅减少计算时间（从 50s+ 降到 <5s）
                rib_w = max(0.4, grip_depth * 1.2)
                z0k = 2.0
                zlen = max(3.0, H - 6.0)
                n_ribs = min(grip_count, 48)  # 限制数量
                r_mid = r0 - grip_depth / 2.0

                # 单根斜筋
                single_rib = (
                    cq.Workplane("XY")
                    .workplane(offset=z0k)
                    .center(r_mid, 0)
                    .rect(grip_depth, rib_w)
                    .twistExtrude(zlen, angleDegrees=45.0)  # 固定45度斜角，只转1/8圈
                )

                ribs = [single_rib.rotate((0, 0, 0), (0, 0, 1), 360.0 * i / n_ribs)
                        for i in range(n_ribs)]
                cutter = self._polar_union(ribs)
                return cap.cut(cutter)

            cap = self.try_feature(meta, "grip_knurl", _do_knurl, cap)

        elif grip_style == "horizontal_grooves" and grip_depth > 0.05:
            def _do_hgrooves() -> cq.Workplane:
                # 横向环纹：等间距水平凹槽
                z0g = 2.0
                z1g = max(z0g + 3.0, H - 3.0)
                groove_h = max(0.4, grip_depth * 0.8)  # 槽宽
                spacing = max(groove_h * 2, 1.5)  # 间距
                n_grooves = int((z1g - z0g) / spacing)
                n_grooves = max(2, min(n_grooves, 30))
                actual_spacing = (z1g - z0g) / n_grooves

                # 用环形切割
                cutter = cq.Workplane("XY")
                for i in range(n_grooves):
                    z_center = z0g + actual_spacing * (i + 0.5)
                    ring = (
                        cq.Workplane("XY")
                        .workplane(offset=z_center - groove_h / 2)
                        .circle(r0 + 0.1)
                        .circle(r0 - grip_depth)
                        .extrude(groove_h)
                    )
                    cutter = cutter.union(ring) if i > 0 else ring
                return cap.cut(cutter)

            cap = self.try_feature(meta, "grip_hgrooves", _do_hgrooves, cap)

        elif grip_style == "stripe" and grip_count >= 4 and grip_depth > 0.05:
            def _do_stripe() -> cq.Workplane:
                # 竖条纹：等间距竖向凹槽（与 ribs 类似但更宽）
                stripe_w = max(0.8, OD * 0.04)
                z0s = 2.0
                stripe_h = max(3.0, H - 4.0)
                n_stripes = min(grip_count, 36)
                surf_r = r0 - grip_depth / 2.0

                single_stripe = (
                    cq.Workplane("XY")
                    .workplane(offset=z0s)
                    .center(surf_r, 0)
                    .rect(grip_depth, stripe_w)
                    .extrude(stripe_h)
                )

                stripes = [single_stripe.rotate((0, 0, 0), (0, 0, 1), 360.0 * i / n_stripes)
                           for i in range(n_stripes)]
                cutter = self._polar_union(stripes)
                return cap.cut(cutter)

            cap = self.try_feature(meta, "grip_stripe", _do_stripe, cap)

        # ---- Step 5: 内置杆子（可选，cap/wand 共用逻辑） ----
        stem = p.get("stem", {}) or {}
        stem_enabled = bool(stem.get("enabled", False))

        if stem_enabled:
            # 5a: 内螺纹（与瓶身外螺纹配合）
            thr = p.get("thread", {}) or {}
            if bool(thr.get("enabled", False)):
                # 安全检查：螺纹峰径必须 < 内腔直径，且不击穿外壁
                _thr_crest = float(thr.get("crest_dia_mm", 18.0))
                _thr_depth = float(thr.get("depth_mm", 0.75))
                _max_crest = min(ID - 2 * _thr_depth - 0.3, OD - 2.0)
                if _thr_crest > _max_crest:
                    if _max_crest >= 10.0:
                        meta.setdefault("auto_adjusted", []).append({
                            "param": "thread.crest_dia_mm",
                            "original": _thr_crest,
                            "adjusted": round(_max_crest, 1),
                            "reason": f"cap内螺纹峰径({_thr_crest:.1f}mm)过大，"
                                      f"缩至{_max_crest:.1f}mm(内径{ID:.1f}mm)",
                        })
                        thr["crest_dia_mm"] = round(_max_crest, 1)
                    else:
                        thr["enabled"] = False
                        meta.setdefault("auto_adjusted", []).append({
                            "param": "thread.enabled",
                            "original": True, "adjusted": False,
                            "reason": f"cap内腔({ID:.1f}mm)过窄，无法容纳螺纹",
                        })
                if bool(thr.get("enabled", False)):
                    cap = self._build_internal_thread(cap, r_inner, thr, cav, meta)

            # 5b: 杆身（从盖顶向下延伸）
            _stem_inner_depth = cav
            cap, stem_bottom_z = self._build_stem_rod(
                cap, H, stem, _stem_inner_depth, eff_taper, meta)

            # 5c: 气密环
            seal = p.get("seal_ring", {}) or {}
            _stem_r = float(stem.get("diameter_mm", 4.5)) / 2.0
            cap = self._build_seal_ring(
                cap, cav, seal, _stem_r, eff_taper, r0, meta)

            # 5d: 刷头
            brush = p.get("brush", {}) or {}
            _brush_len = float(brush.get("length_mm", 12.0))
            _brush_z0 = stem_bottom_z - _brush_len
            _stem_taper = float(stem.get("taper_ratio", 1.0))
            _stem_profile = str(stem.get("profile", "round"))
            _taper_factor = _stem_taper if _stem_profile == "tapered" else 1.0
            cap = self._build_brush_head(
                cap, _brush_z0, _stem_r, brush, _taper_factor, meta)

        # ---- final sanity ----
        try:
            shp = cap.val()
            if not hasattr(shp, "Volume"):
                raise RuntimeError("val() is not a Shape")
            if shp.Volume() < 1e-6:  # type: ignore[union-attr]
                raise RuntimeError("volume ~ 0")
        except Exception as e:
            raise RuntimeError(f"cap sanity failed: {e}")

        return cap

    # -----------------------------
    # build_bottle
    # -----------------------------
    def build_bottle(self, p: Dict[str, Any], meta: Dict[str, Any]) -> cq.Workplane:
        """
        瓶身建模：唇釉瓶容器
        几何结构：底部 -> 瓶身 -> 肩部过渡 -> 颈部 -> 外螺纹
        """
        # ---- main dims ----
        H = float(p["height_mm"])
        body_od = float(p["body_od_mm"])
        wall = float(p["wall_thickness_mm"])
        bottom_t = float(p["bottom_thickness_mm"])
        inner_depth = float(p["inner_depth_mm"])

        shape = str(p.get("shape", "cyl"))
        taper_deg = float(p.get("taper_deg", 0.0))
        cross_section = str(p.get("cross_section", "round"))
        corner_radius_mm = float(p.get("corner_radius_mm", 3.0))

        # neck
        neck_od = float(p["neck_od_mm"])
        neck_h = float(p["neck_height_mm"])
        lip_t = float(p["lip_thickness_mm"])

        # shoulder
        shoulder_h = float(p["shoulder_height_mm"])
        shoulder_style = str(p.get("shoulder_style", "round"))
        shoulder_fillet = float(p.get("shoulder_fillet_mm", 3.0))

        # bottom
        bottom_style = str(p.get("bottom_style", "flat"))
        bottom_concave = float(p.get("bottom_concave_mm", 0.0))
        bottom_fillet = float(p.get("bottom_fillet_mm", 1.5))

        # thread
        thr = p.get("thread", {}) or {}
        thr_on = bool(thr.get("enabled", True))
        thr_pitch = float(thr.get("pitch_mm", 2.7))
        thr_turns = int(thr.get("turns", 2))
        thr_depth = float(thr.get("depth_mm", 0.5))
        thr_bottom_dia = float(thr.get("bottom_dia_mm", neck_od - 2 * thr_depth))
        thr_lead_angle = float(thr.get("lead_angle_deg", 3.0))  # 导程角
        thr_segmented = bool(thr.get("segmented", False))  # 分段螺纹

        # derived
        body_r = body_od / 2.0
        neck_r = neck_od / 2.0
        body_id = body_od - 2 * wall
        neck_id = neck_od - 2 * lip_t

        # body height = total - neck - shoulder - (part of bottom in geometry)
        body_h = H - neck_h - shoulder_h

        if body_h <= 0:
            raise RuntimeError(f"body height <= 0: H={H}, neck_h={neck_h}, shoulder_h={shoulder_h}")

        # ---- Step 1: build outer shell (critical) ----
        # 底部到肩底的瓶身段
        # 注意：为了确保 union 时各部分正确合并，相邻部分需要有重叠
        eps = 0.15  # 重叠量

        # 轮廓模式：classic（直线锥台）或 spline（B-spline 曲线旋转体）
        profile_mode = str(p.get("profile_mode", "classic"))

        # 注塑最低拔模角 0.5°（正锥/直筒），倒锥跳过（需特殊模具）
        MFG_MIN_DRAFT = 0.5
        eff_taper_deg = taper_deg
        if taper_deg < 0:
            # 倒锥：底窄顶宽，需分模/侧抽模具
            meta.setdefault("mfg_adjustments", []).append(
                f"倒锥设计(锥度{taper_deg:.1f}°)，需分模或侧抽芯模具"
            )
        elif shape != "taper" or taper_deg < MFG_MIN_DRAFT:
            eff_taper_deg = max(taper_deg, MFG_MIN_DRAFT)
            if taper_deg < MFG_MIN_DRAFT:
                meta.setdefault("mfg_adjustments", []).append(
                    f"瓶身外壁拔模角从{taper_deg:.1f}°提升至{MFG_MIN_DRAFT}°（注塑最低要求）"
                )

        eff_taper_rad = math.radians(eff_taper_deg)
        delta_r = math.tan(eff_taper_rad) * body_h
        bottom_r_body = body_r                # body_od 就是瓶底最大直径
        top_r_body = body_r - delta_r         # 正锥:顶部收窄; 倒锥:顶部外扩
        # 安全限制：顶部半径不超过底部的 1.5 倍
        top_r_body = max(body_r * 0.3, min(body_r * 1.5, top_r_body))

        shoulder_top_z = body_h + shoulder_h

        if profile_mode == "spline":
            # ========== SPLINE 模式：body + shoulder 由 spline 旋转体生成 ==========
            import json
            from products.lip_gloss.derived_params import generate_default_bottle_profile

            raw = p.get("profile_points_json", "[]")
            pts = json.loads(raw) if isinstance(raw, str) else raw
            profile_pts = [(float(pt[0]), float(pt[1])) for pt in pts]

            # 控制点不足时自动生成默认轮廓
            if len(profile_pts) < 3:
                profile_pts = generate_default_bottle_profile(
                    body_r, body_h, shoulder_h, neck_r, eff_taper_deg
                )

            # 强制首尾约束：首点 Z=0，末点半径=neck_r & Z=shoulder_top_z
            profile_pts[0] = (profile_pts[0][0], 0.0)
            profile_pts[-1] = (neck_r, shoulder_top_z)

            # 壁厚安全校验：瓶身区域(z ≤ body_h) 半径 ≥ 内腔半径 + 0.3mm
            inner_r_body_check = (body_od - 2 * wall) / 2.0
            min_r = inner_r_body_check + 0.3
            max_r_check = body_od / 2.0 * 1.05

            profile_symmetry = str(p.get("profile_symmetry", "symmetric"))

            if profile_symmetry == "asymmetric":
                # ===== 非对称模式：读取 B 轮廓，用椭圆截面 loft =====
                raw_b = p.get("profile_b_points_json", "[]")
                pts_b = json.loads(raw_b) if isinstance(raw_b, str) else raw_b
                profile_b_pts = [(float(pt[0]), float(pt[1])) for pt in pts_b]

                if len(profile_b_pts) < 3:
                    # B 轮廓不足时退化为 A 轮廓
                    profile_b_pts = list(profile_pts)

                # 强制 B 轮廓首尾与 A 相同
                profile_b_pts[0] = (profile_pts[0][0], 0.0)
                profile_b_pts[-1] = (neck_r, shoulder_top_z)

                # 强制 B 轮廓 Z 坐标与 A 对齐
                for i in range(len(profile_b_pts)):
                    if i < len(profile_pts):
                        profile_b_pts[i] = (profile_b_pts[i][0], profile_pts[i][1])

                profile_pts, profile_b_pts, _pair_warnings = self._validate_profile_pair(
                    profile_pts, profile_b_pts,
                    max_r_check, min_r_body=min_r, min_r_z_max=body_h,
                )
                if _pair_warnings:
                    meta.setdefault("profile_warnings", []).extend(_pair_warnings)

                # spline 只管瓶身+肩部造型，颈部由 Step 3 独立生成圆柱体
                bottle = self._ellipse_loft(profile_pts, profile_b_pts)
                # 不设 _neck_in_loft → Step 3 用 _robust_union 加颈部

                meta["profile_mode"] = "spline"
                meta["profile_symmetry"] = "asymmetric"
                meta["profile_points"] = profile_pts
                meta["profile_b_points"] = profile_b_pts
            else:
                # ===== 对称模式：现有 B-spline 旋转体 =====
                profile_pts, _sym_warnings = self._validate_profile(
                    profile_pts, max_r_check,
                    min_r_body=min_r, min_r_z_max=body_h,
                )
                if _sym_warnings:
                    meta.setdefault("profile_warnings", []).extend(_sym_warnings)
                # spline 只管瓶身+肩部造型，颈部由 Step 3 独立生成圆柱体
                # （B-spline 无法维持圆柱颈部，会把颈部曲线糊掉）
                bottle = self._spline_revolve(profile_pts)
                # 不设 _neck_in_loft → Step 3 用 _robust_union 加颈部

                meta["profile_mode"] = "spline"
                meta["profile_symmetry"] = "symmetric"
                meta["profile_points"] = profile_pts
        else:
            # ========== CLASSIC 模式：原有直线锥台 ==========
            meta["profile_mode"] = "classic"

            if cross_section == "square":
                # ---- 方形截面模式 ----
                meta["cross_section"] = "square"
                # body_od 当作方形边长
                side_bottom = body_od
                # 锥度：顶部边长缩小
                side_top = side_bottom - 2 * delta_r
                side_top = max(side_bottom * 0.3, min(side_bottom * 1.5, side_top))

                bottle = self._rounded_rect_loft(
                    side_bottom, side_top, corner_radius_mm,
                    body_h + eps, z0=0.0,
                )

                # 肩部：方形到圆形过渡（增加重叠确保 union 可靠）
                _shoulder_overlap = 0.3
                shoulder_bottom_z = body_h - _shoulder_overlap
                shoulder = self._square_to_circle_loft(
                    side_top, corner_radius_mm, neck_r,
                    shoulder_h + _shoulder_overlap, z0=shoulder_bottom_z,
                )
                bottle = self._robust_union(bottle, shoulder)
            elif _is_polygon(cross_section):
                # ---- 多边形截面模式（triangle/hexagon/octagon）----
                meta["cross_section"] = cross_section
                n = _n_sides(cross_section)
                # body_od 当作外接圆直径
                r_bottom = body_od / 2.0
                r_top = r_bottom - delta_r
                r_top = max(r_bottom * 0.3, min(r_bottom * 1.5, r_top))

                bottle = self._polygon_loft(
                    n, r_bottom, r_top, corner_radius_mm,
                    body_h + eps, z0=0.0,
                )

                # 肩部：多边形到圆形过渡（增加重叠确保 union 可靠）
                _shoulder_overlap = 0.3
                shoulder_bottom_z = body_h - _shoulder_overlap
                shoulder = self._polygon_to_circle_loft(
                    n, r_top, corner_radius_mm, neck_r,
                    shoulder_h + _shoulder_overlap, z0=shoulder_bottom_z,
                )
                bottle = self._robust_union(bottle, shoulder)
            else:
                # ---- 圆形截面模式（默认） ----
                meta["cross_section"] = "round"
                # 统一使用 loft 生成带拔模角的瓶身
                bottle = self._loft_frustum(bottom_r_body, top_r_body, body_h + eps, z0=0.0)

                # ---- shoulder transition (critical) ----
                shoulder_bottom_z = body_h - eps
                shoulder_start_r = top_r_body

                if shoulder_style == "angular":
                    # 直线锥台：锐利过渡
                    shoulder = self._loft_frustum(shoulder_start_r, neck_r, shoulder_h + eps, z0=shoulder_bottom_z)
                elif shoulder_style == "sloped":
                    # 缓斜面：两段直线，先缓后陡
                    _s_h = shoulder_h + eps
                    _mid_r = shoulder_start_r * 0.6 + neck_r * 0.4
                    shoulder = (
                        cq.Workplane("XY")
                        .workplane(offset=shoulder_bottom_z)
                        .circle(shoulder_start_r)
                        .workplane(offset=_s_h * 0.65)
                        .circle(_mid_r)
                        .workplane(offset=_s_h * 0.35)
                        .circle(neck_r)
                        .loft(combine=True)
                    )
                else:
                    # round: 弧线过渡（四分之一椭圆revolve）
                    _dr = shoulder_start_r - neck_r
                    _s_h = shoulder_h + eps
                    if _dr > 0.5 and _s_h > 1.0:
                        _mid_r = neck_r + _dr * 0.707
                        _mid_z = shoulder_bottom_z + _s_h * 0.707
                        shoulder = self.try_feature(
                            meta, "shoulder_round_arc",
                            lambda: (
                                cq.Workplane("XZ")
                                .moveTo(0, shoulder_bottom_z)
                                .lineTo(shoulder_start_r, shoulder_bottom_z)
                                .threePointArc((_mid_r, _mid_z), (neck_r, shoulder_bottom_z + _s_h))
                                .lineTo(0, shoulder_bottom_z + _s_h)
                                .close()
                                .revolve(360, (0, 0), (0, 1))
                            ),
                            # 失败则回退到直线锥台
                            self._loft_frustum(shoulder_start_r, neck_r, _s_h, z0=shoulder_bottom_z),
                        )
                    else:
                        # 半径差或肩高太小，回退到直线锥台
                        shoulder = self._loft_frustum(shoulder_start_r, neck_r, _s_h, z0=shoulder_bottom_z)

                bottle = self._robust_union(bottle, shoulder)

        # ---- Step 1.5: collar band with ribs (non-critical) ----
        collar_on = bool(p.get("collar_enabled", False))
        collar_h = float(p.get("collar_height_mm", 4.0))
        collar_rib_count = int(p.get("collar_rib_count", 30))
        collar_rib_depth = float(p.get("collar_rib_depth_mm", 0.2))
        collar_w_excess = float(p.get("collar_width_excess_mm", 0.0))

        if collar_on and collar_h > 0.5 and cross_section == "round":
            def _do_collar() -> cq.Workplane:
                c_z0 = max(1.0, body_h - collar_h)
                collar_r = body_r + max(0.0, collar_w_excess)
                collar_band = (
                    cq.Workplane("XY")
                    .workplane(offset=c_z0 - eps)
                    .circle(collar_r)
                    .extrude(collar_h + 2 * eps)
                )
                result = self._robust_union(bottle, collar_band)
                if collar_rib_count >= 6 and collar_rib_depth > 0.03:
                    rib_w = max(0.3, collar_r * 2 * 0.015)
                    surf_r = collar_r - collar_rib_depth / 2.0
                    single = (
                        cq.Workplane("XY")
                        .workplane(offset=c_z0 - eps)
                        .center(surf_r, 0)
                        .rect(collar_rib_depth, rib_w)
                        .extrude(collar_h + 2 * eps)
                    )
                    ribs = [single.rotate((0, 0, 0), (0, 0, 1), 360.0 * i / collar_rib_count)
                            for i in range(collar_rib_count)]
                    cutter = self._polar_union(ribs)
                    result = result.cut(cutter)
                return result

            bottle = self.try_feature(meta, "collar_ribs", _do_collar, bottle)

        # ---- Step 3: neck cylinder (critical, with minimum draft) ----
        # 非对称模式下颈部已包含在 loft 体中，跳过布尔 union
        if not meta.get("_neck_in_loft"):
            neck_draft_deg = 0.3
            neck_draft_r = math.tan(math.radians(neck_draft_deg)) * neck_h
            neck_r_bottom = neck_r + neck_draft_r / 2.0
            neck_r_top = neck_r - neck_draft_r / 2.0
            neck = self._loft_frustum(neck_r_bottom, neck_r_top, neck_h + eps,
                                      z0=shoulder_top_z - eps)
            bottle = self._robust_union(bottle, neck)

        # ---- Step 4: hollow out cavity (critical) ----
        # 内腔从瓶口顶面向下挖
        inner_r_body = body_id / 2.0
        inner_r_neck = neck_id / 2.0

        # 简化：内腔为从顶部向下的圆柱，半径取瓶身内径
        # 实际可能需要分段处理颈部和瓶身的内径差异
        cavity_top_z = H + eps
        cavity_bottom_z = H - inner_depth

        if cavity_bottom_z < bottom_t - eps:
            cavity_bottom_z = bottom_t

        # 颈部内腔（较窄）
        neck_cavity = (
            cq.Workplane("XY")
            .workplane(offset=shoulder_top_z - eps)
            .circle(inner_r_neck)
            .extrude(neck_h + 2 * eps)
        )

        # 瓶身内腔（较宽）- 仅覆盖圆柱体段（底厚到肩部起始处）
        # 不能延伸到肩部区域，否则 inner_r_body > neck_r 时会穿透肩壁
        body_cavity_top = body_h
        body_cavity_bottom = bottom_t

        # spline 模式下：限制 body cavity 上限，确保外壁半径 > 内腔半径 + 壁厚余量
        # B-spline 曲线在控制点之间可能下凹，需要足够的安全余量防止布尔运算失败
        if profile_mode == "spline" and "profile_points" in meta:
            _prof_pts = meta["profile_points"]
            _safe_r = inner_r_body + 1.0  # 安全阈值：内腔半径 + 1mm 余量
            for _i in range(len(_prof_pts) - 1):
                _r0, _z0 = _prof_pts[_i]
                _r1, _z1 = _prof_pts[_i + 1]
                if _r0 >= _safe_r and _r1 < _safe_r:
                    _frac = (_r0 - _safe_r) / (_r0 - _r1) if _r0 > _r1 else 0
                    body_cavity_top = min(body_cavity_top, _z0 + _frac * (_z1 - _z0) - 1.0)
                    break
                elif _r1 <= _safe_r:
                    body_cavity_top = min(body_cavity_top, _z0 - 1.0)
                    break

        body_cavity_h = body_cavity_top - body_cavity_bottom
        inner_r_body_top = inner_r_body  # 默认：直筒，顶底一致

        body_cavity = None
        if body_cavity_h > 0:
            if cross_section == "square":
                # 方形内腔：圆角矩形
                inner_side = body_id
                inner_cr = max(0.5, corner_radius_mm - wall)
                if eff_taper_deg > 0:
                    # 锥形方形内腔：跟随外壳收窄，保持等壁厚
                    inner_side_top = max(inner_side * 0.3, side_top - 2 * wall)
                    body_cavity = self._rounded_rect_loft(
                        inner_side, inner_side_top, inner_cr,
                        body_cavity_h + eps, z0=body_cavity_bottom,
                    )
                else:
                    body_cavity = (
                        cq.Workplane("XY")
                        .workplane(offset=body_cavity_bottom)
                        .sketch().rect(inner_side, inner_side).vertices().fillet(inner_cr).finalize()
                        .extrude(body_cavity_h + eps)
                    )
            elif _is_polygon(cross_section):
                # 多边形内腔
                n = _n_sides(cross_section)
                inner_cr = max(0.3, corner_radius_mm - wall)
                if eff_taper_deg > 0:
                    inner_r_body_top = max(inner_r_body * 0.3, r_top - wall)
                    body_cavity = self._polygon_loft(
                        n, inner_r_body, inner_r_body_top, inner_cr,
                        body_cavity_h + eps, z0=body_cavity_bottom,
                    )
                else:
                    body_cavity = self._polygon_loft(
                        n, inner_r_body, inner_r_body, inner_cr,
                        body_cavity_h + eps, z0=body_cavity_bottom,
                    )
            else:
                if eff_taper_deg > 0:
                    # 锥形内腔：内壁随外壁收窄，保持等壁厚
                    inner_r_body_top = max(inner_r_neck, top_r_body - wall)
                    inner_r_body_top = max(inner_r_body * 0.3, inner_r_body_top)
                    body_cavity = self._loft_frustum(
                        inner_r_body, inner_r_body_top,
                        body_cavity_h + eps, z0=body_cavity_bottom,
                    )
                else:
                    inner_r_body_top = inner_r_body  # 直筒：顶底一致
                    body_cavity = (
                        cq.Workplane("XY")
                        .workplane(offset=body_cavity_bottom)
                        .circle(inner_r_body)
                        .extrude(body_cavity_h + eps)
                    )

        # 肩部内腔过渡（从 body 顶部内径到 neck 内径）
        # 锥度模式下 inner_r_body_top 已在上方计算；spline 模式下从 body_cavity_top 开始
        shoulder_cav_start_r = inner_r_body_top if body_cavity_h > 0 else inner_r_body
        shoulder_cav_z0 = body_cavity_top if body_cavity_h > 0 else body_h
        shoulder_cav_h = shoulder_top_z - shoulder_cav_z0
        if shoulder_cav_h <= 0:
            shoulder_cav_h = shoulder_h
            shoulder_cav_z0 = body_h - eps / 2
        if cross_section == "square":
            # 方形截面：肩部内腔用 square→circle loft（匹配外壁过渡）
            # ★ 锥度模式下用顶部边长（与 body cavity 顶部对齐）
            if body_cavity_h > 0 and eff_taper_deg > 0:
                _sq_inner_side = max(body_id * 0.3, side_top - 2 * wall)
            else:
                _sq_inner_side = body_id
            inner_cr = max(0.5, corner_radius_mm - wall)
            shoulder_cavity = self._square_to_circle_loft(
                _sq_inner_side, inner_cr, inner_r_neck,
                shoulder_cav_h + eps, z0=shoulder_cav_z0 - eps / 2,
            )
        elif _is_polygon(cross_section):
            # 多边形截面：肩部内腔用 polygon→circle loft
            # ★ 锥度模式下用 inner_r_body_top（与 body cavity 顶部对齐），
            #   避免用 inner_r_body（瓶底内径）穿透已收窄的肩部外壁
            n = _n_sides(cross_section)
            _shoulder_inner_r = inner_r_body_top if body_cavity_h > 0 else inner_r_body
            shoulder_cavity = self._polygon_to_circle_loft(
                n, _shoulder_inner_r, corner_radius_mm, inner_r_neck,
                shoulder_cav_h + eps, z0=shoulder_cav_z0 - eps / 2,
            )
        else:
            shoulder_cavity = self._loft_frustum(
                shoulder_cav_start_r, inner_r_neck, shoulder_cav_h + eps, z0=shoulder_cav_z0 - eps / 2
            )

        # spline 模式下：合并所有腔体后一次性切割，提高 B-spline 表面布尔运算稳定性
        if profile_mode == "spline":
            combined_cavity = neck_cavity
            if body_cavity is not None:
                combined_cavity = combined_cavity.union(body_cavity)
            combined_cavity = combined_cavity.union(shoulder_cavity)
            bottle = bottle.cut(combined_cavity)
        else:
            bottle = bottle.cut(neck_cavity)
            if body_cavity is not None:
                bottle = bottle.cut(body_cavity)
            bottle = bottle.cut(shoulder_cavity)

        # ---- Step 4b: lip chamfer (在螺纹前执行，此时顶面是干净的环形面) ----
        lip_chamfer = min(0.3, lip_t * 0.2)
        if lip_chamfer > 0.05:
            bottle = self.try_feature(
                meta, "lip_chamfer",
                lambda: bottle.faces(">Z").edges().chamfer(lip_chamfer),
                bottle
            )

        # ---- Step 5: outer thread (non-critical, allow degrade) ----
        if thr_on:
            thread_len = thr_pitch * thr_turns
            thread_z0 = H - neck_h + 0.5  # 螺纹起始位置（从颈部底部略上）
            thread_z1 = thread_z0 + thread_len

            if thread_z1 > H - 0.5:
                thread_z1 = H - 0.5
                thread_len = thread_z1 - thread_z0

            if thread_len < thr_pitch:
                # 不足一圈，跳过螺纹
                meta["thread_status"] = {
                    "requested": True, "attempted": False, "degraded": False,
                    "reason": f"颈部空间不足（需要{thr_pitch:.1f}mm，仅有{thread_len:.1f}mm）",
                }
                thread_len = 0  # 标记跳过

            if thread_len > 0:
                # 外螺纹：在颈部外表面添加螺旋凸起
                r_outer = neck_r
                r_thread_peak = r_outer + thr_depth
                t = thr_pitch * 0.4  # 齿厚

                pts = [
                    (r_outer - 0.05, -t / 2.0),
                    (r_outer - 0.05, t / 2.0),
                    (r_thread_peak, 0.0),
                ]

                # 计算扭转角度（考虑导程角）
                base_angle = 360.0 * thr_turns
                lead_factor = 1.0 + thr_lead_angle / 90.0
                twist_angle = base_angle * lead_factor

                if thr_segmented:
                    # 分段螺纹：一圈两断
                    def make_segmented_thread_union() -> cq.Workplane:
                        segments_per_turn = 2
                        gap_angle = float(thr.get("gap_angle_deg", 20.0))  # 间隔角度（可配置）
                        seg_angle = (360.0 - segments_per_turn * gap_angle) / segments_per_turn
                        seg_len = thr_pitch * (seg_angle / 360.0)

                        all_segs = []
                        for turn_i in range(thr_turns):
                            for seg_i in range(segments_per_turn):
                                start_angle = turn_i * 360.0 + seg_i * (seg_angle + gap_angle)
                                z_offset = thread_z0 + (start_angle / 360.0) * thr_pitch

                                if z_offset + seg_len > thread_z0 + thread_len:
                                    continue

                                # 关键修复：数学旋转截面点
                                angle_rad = math.radians(start_angle)
                                cos_a = math.cos(angle_rad)
                                sin_a = math.sin(angle_rad)

                                rotated_pts = []
                                for (r, y) in pts:
                                    x_new = r * cos_a - y * sin_a
                                    y_new = r * sin_a + y * cos_a
                                    rotated_pts.append((x_new, y_new))

                                seg = (
                                    cq.Workplane("XY")
                                    .workplane(offset=z_offset)
                                    .polyline(rotated_pts)
                                    .close()
                                    .twistExtrude(seg_len, angleDegrees=seg_angle)
                                )
                                all_segs.append(seg)

                        if not all_segs:
                            return bottle

                        thread_solid = all_segs[0]
                        for s in all_segs[1:]:
                            thread_solid = self._robust_union(thread_solid, s)
                        return self._robust_union(bottle, thread_solid)

                    bottle = self.try_feature(meta, "outer_thread_segmented", make_segmented_thread_union, bottle)
                else:
                    # 连续螺纹
                    def make_thread_union() -> cq.Workplane:
                        thread_solid = (
                            cq.Workplane("XY")
                            .workplane(offset=thread_z0)
                            .polyline(pts)
                            .close()
                            .twistExtrude(thread_len, angleDegrees=twist_angle)
                        )
                        return self._robust_union(bottle, thread_solid)

                    bottle = self.try_feature(meta, "outer_thread", make_thread_union, bottle)

        # 记录螺纹实际生成状态
        meta["thread_status"] = {
            "requested": bool(thr_on),
            "attempted": bool(thr_on and thr_pitch * thr_turns > 0),
            "degraded": any("thread" in d.get("feature", "")
                            for d in meta.get("degraded", [])),
        }

        # ---- Step 6: bottom treatment (non-critical) ----
        if bottom_style == "concave" and bottom_concave > 0:
            # 底部内凹
            def _do_concave() -> cq.Workplane:
                concave = (
                    cq.Workplane("XY")
                    .workplane(offset=-eps)
                    .circle(body_r * 0.7)
                    .extrude(bottom_concave + eps)
                )
                return bottle.cut(concave)
            bottle = self.try_feature(meta, "bottom_concave", _do_concave, bottle)
        elif bottom_style == "convex" and bottom_concave > 0:
            # 底部外凸：threePointArc revolve 球冠向下突出
            def _do_convex() -> cq.Workplane:
                _cvx_r = body_r * 0.7  # 凸起半径范围
                _cvx_h = min(bottom_concave, 3.0)  # 限制凸起高度
                _mid_r = _cvx_r * 0.707
                _mid_z = -_cvx_h * 0.707
                bump = (
                    cq.Workplane("XZ")
                    .moveTo(0, 0)
                    .lineTo(_cvx_r, 0)
                    .threePointArc((_mid_r, _mid_z), (0, -_cvx_h))
                    .close()
                    .revolve(360, (0, 0), (0, 1))
                )
                return self._robust_union(bottle, bump)
            bottle = self.try_feature(meta, "bottom_convex", _do_convex, bottle)

        # ---- Step 6.5: base ring (non-critical) ----
        base_ring_on = bool(p.get("base_ring_enabled", False))
        base_ring_h = float(p.get("base_ring_height_mm", 2.0))
        base_ring_excess = float(p.get("base_ring_width_excess_mm", 0.5))

        if base_ring_on and base_ring_h > 0.3 and cross_section == "round":
            def _do_base_ring() -> cq.Workplane:
                ring_r = body_r + max(0.2, base_ring_excess)
                ring = (
                    cq.Workplane("XY")
                    .workplane(offset=0)
                    .circle(ring_r)
                    .extrude(base_ring_h)
                )
                return self._robust_union(bottle, ring)

            bottle = self.try_feature(meta, "base_ring", _do_base_ring, bottle)

        # ---- Step 7: edge fillets (non-critical, enforce minimums) ----
        MIN_EXT_FILLET = 0.5
        rf = max(bottom_fillet, MIN_EXT_FILLET)
        rf = min(rf, body_r * 0.3)
        rf = max(rf, MIN_EXT_FILLET)

        if cross_section == "square" or _is_polygon(cross_section):
            # 非圆截面：loft 已内置圆角处理，跳过重复操作
            pass
        elif profile_mode == "spline":
            # spline 模式：底部 fillet 用较小半径（spline 本身可能带有曲率）
            bottle = self.try_feature(
                meta, "bottom_fillet",
                lambda: bottle.faces("<Z").edges().fillet(min(rf, 1.0)),
                bottle
            )
            # 肩部 fillet 在 spline 模式下跳过（spline 曲线已替代线性肩部过渡）
        else:
            bottle = self.try_feature(
                meta, "bottom_fillet",
                lambda: bottle.faces("<Z").edges().fillet(rf),
                bottle
            )

            if shoulder_fillet > 1e-6:
                _dr = max(body_r - neck_r, 0.1)
                if shoulder_style == "round":
                    # round 已是弧线，用较小辅助 fillet
                    sf = min(shoulder_fillet, min(_dr, shoulder_h) * 0.4)
                elif shoulder_style == "sloped":
                    # sloped 两段直线，中等 fillet
                    sf = min(shoulder_fillet, min(_dr, shoulder_h) * 0.3)
                else:
                    # angular 硬边最需要 fillet
                    sf = min(shoulder_fillet, min(_dr, shoulder_h) * 0.35)
                if sf > 0.5:
                    bottle = self.try_feature(
                        meta, "shoulder_fillet",
                        lambda: bottle.faces(">Z").edges().fillet(sf * 0.3),
                        bottle
                    )

        # ---- final sanity ----
        try:
            shp = bottle.val()
            if not hasattr(shp, "Volume"):
                raise RuntimeError("val() is not a Shape")
            if shp.Volume() < 1e-6:  # type: ignore[union-attr]
                raise RuntimeError("volume ~ 0")
        except Exception as e:
            raise RuntimeError(f"bottle sanity failed: {e}")

        return bottle

    # -----------------------------
    # build_wiper
    # -----------------------------
    def build_wiper(self, p: Dict[str, Any], meta: Dict[str, Any]) -> cq.Workplane:
        """
        内塞建模：唇釉瓶刮片/密封塞
        几何结构：主体套筒 + 底部凸环 + 顶部隔膜（带中心孔口）
        """
        # ---- main dims ----
        H = float(p["height_mm"])
        outer_od = float(p["outer_od_mm"])
        inner_id = float(p["inner_id_mm"])
        orifice = float(p["orifice_mm"])
        orifice_edge = float(p.get("orifice_edge_mm", 0.3))

        # flange
        flange_od = float(p["flange_od_mm"])
        flange_id = float(p["flange_id_mm"])
        flange_h = float(p.get("flange_height_mm", 1.5))
        flange_pos = str(p.get("flange_position", "bottom"))

        # diaphragm
        diaphragm_style = str(p.get("diaphragm_style", "flat"))
        diaphragm_t = float(p.get("diaphragm_thickness_mm", 0.8))
        diaphragm_depth = float(p.get("diaphragm_depth_mm", 1.0))

        # ribs
        rib = p.get("rib", {}) or {}
        rib_on = bool(rib.get("enabled", False))
        rib_count = int(rib.get("count", 4))
        rib_w = float(rib.get("width_mm", 0.6))
        rib_h = float(rib.get("height_mm", 0.4))

        # derived
        outer_r = outer_od / 2.0
        inner_r = inner_id / 2.0
        orifice_r = orifice / 2.0
        flange_outer_r = flange_od / 2.0
        flange_inner_r = flange_id / 2.0
        wall_t = outer_r - inner_r

        # ---- Step 1: main body sleeve (critical, with minimum draft) ----
        # 主体套筒：外径为 outer_od，内腔为 inner_id
        # 最小拔模角 0.3°（弹性件，稍小即可）
        wiper_draft_deg = 0.3
        wiper_draft_r = math.tan(math.radians(wiper_draft_deg)) * H
        wiper_r_bottom = outer_r
        wiper_r_top = outer_r - wiper_draft_r
        if wiper_r_top < outer_r * 0.9:
            wiper_r_top = outer_r * 0.95
        wiper = self._loft_frustum(wiper_r_bottom, wiper_r_top, H, z0=0.0)

        # 挖空内腔（从顶部向下，保留底部隔膜厚度）
        cavity_depth = H - diaphragm_t
        if cavity_depth > 0:
            cavity = (
                cq.Workplane("XY")
                .workplane(offset=diaphragm_t)
                .circle(inner_r)
                .extrude(cavity_depth + 0.1)
            )
            wiper = wiper.cut(cavity)

        # ---- Step 2: flange / rim (critical) ----
        # 凸环：用于卡在瓶口边缘
        if flange_pos == "bottom":
            flange_z = 0.0
        elif flange_pos == "middle":
            flange_z = (H - flange_h) / 2.0
        else:  # top
            flange_z = H - flange_h

        # 凸环是一个环形：外径 flange_od，内径 flange_id
        flange = (
            cq.Workplane("XY")
            .workplane(offset=flange_z)
            .circle(flange_outer_r)
            .circle(flange_inner_r)
            .extrude(flange_h)
        )
        wiper = wiper.union(flange)

        # ---- Step 3: diaphragm orifice (critical) ----
        # 中心孔口：穿透隔膜
        orifice_cutter = (
            cq.Workplane("XY")
            .workplane(offset=-0.1)
            .circle(orifice_r)
            .extrude(diaphragm_t + 0.2)
        )
        wiper = wiper.cut(orifice_cutter)

        # ---- Step 4: diaphragm shape (non-critical) ----
        if diaphragm_style == "concave" and diaphragm_depth > 0:
            # 凹面隔膜：从顶部向下凹陷
            def _do_concave() -> cq.Workplane:
                # 创建一个球形切割器来形成凹面
                # 使用圆环loft近似凹面效果
                concave_r = inner_r - 0.2
                if concave_r > orifice_r + 0.5:
                    concave = (
                        cq.Workplane("XY")
                        .workplane(offset=diaphragm_t - diaphragm_depth)
                        .circle(concave_r)
                        .workplane(offset=diaphragm_depth + 0.1)
                        .circle(orifice_r + 0.3)
                        .loft(combine=True)
                    )
                    return wiper.cut(concave)
                return wiper
            wiper = self.try_feature(meta, "diaphragm_concave", _do_concave, wiper)

        elif diaphragm_style == "convex" and diaphragm_depth > 0:
            # 凸面隔膜：向下凸起
            def _do_convex() -> cq.Workplane:
                convex_r = inner_r - 0.3
                if convex_r > orifice_r + 0.5:
                    convex = (
                        cq.Workplane("XY")
                        .workplane(offset=-diaphragm_depth)
                        .circle(orifice_r + 0.2)
                        .workplane(offset=diaphragm_depth)
                        .circle(convex_r)
                        .loft(combine=True)
                    )
                    return wiper.union(convex)
                return wiper
            wiper = self.try_feature(meta, "diaphragm_convex", _do_convex, wiper)

        # ---- Step 5: reinforcement ribs (non-critical) ----
        if rib_on and rib_count >= 2 and rib_w > 0 and rib_h > 0:
            def _do_ribs() -> cq.Workplane:
                # 加强筋：从隔膜向上延伸到内腔
                rib_z0 = diaphragm_t
                rib_len = min(cavity_depth - 0.5, H * 0.6)
                if rib_len < 1.0:
                    return wiper

                # 筋条位置：在内腔壁上
                rib_r = inner_r - rib_h / 2.0
                single_rib = (
                    cq.Workplane("XY")
                    .workplane(offset=rib_z0)
                    .center(rib_r, 0)
                    .rect(rib_h, rib_w)
                    .extrude(rib_len)
                )

                all_ribs = single_rib
                for i in range(1, rib_count):
                    angle = 360.0 * i / rib_count
                    rotated = single_rib.rotate((0, 0, 0), (0, 0, 1), angle)
                    all_ribs = all_ribs.union(rotated)

                return wiper.union(all_ribs)

            wiper = self.try_feature(meta, "reinforcement_ribs", _do_ribs, wiper)

        # ---- Step 6: edge treatment (non-critical) ----
        # 顶部边缘倒角
        top_chamfer = min(0.2, wall_t * 0.15)
        if top_chamfer > 0.05:
            wiper = self.try_feature(
                meta, "top_chamfer",
                lambda: wiper.edges(">Z").chamfer(top_chamfer),
                wiper
            )

        # 孔口边缘圆角（改善刮擦手感）
        orifice_fillet = min(orifice_edge * 0.5, 0.15)
        if orifice_fillet > 0.03:
            wiper = self.try_feature(
                meta, "orifice_fillet",
                lambda: wiper.edges("<Z").fillet(orifice_fillet),
                wiper
            )

        # ---- final sanity ----
        try:
            shp = wiper.val()
            if not hasattr(shp, "Volume"):
                raise RuntimeError("val() is not a Shape")
            if shp.Volume() < 1e-6:  # type: ignore[union-attr]
                raise RuntimeError("volume ~ 0")
        except Exception as e:
            raise RuntimeError(f"wiper sanity failed: {e}")

        return wiper

    # -----------------------------
    # build_wand
    # -----------------------------
    def build_wand(self, p: Dict[str, Any], meta: Dict[str, Any]) -> cq.Workplane:
        """
        刷杆建模：唇釉瓶涂抹棒
        两种结构类型：
        - cap_integrated：帽盖一体式，刷杆嵌入盖子内部
        - separate_stem：独立杆式，刷杆头部独立于外盖

        几何结构：盖子主体 + 杆身 + 内螺纹 + 气密环 + 刷头
        """
        # ---- main dims ----
        wand_type = str(p.get("wand_type", "cap_integrated"))
        total_h = float(p["total_height_mm"])
        outer_od = float(p["outer_od_mm"])
        cap_h = float(p["cap_height_mm"])

        # stem
        stem_d = float(p["stem_diameter_mm"])
        stem_len = float(p["stem_length_mm"])
        stem_profile = str(p.get("stem_profile", "round"))
        stem_taper = float(p.get("stem_taper_ratio", 1.0))
        stem_wall = float(p.get("stem_wall_mm", 0.8))

        # connection
        mouth_to_top = float(p["mouth_to_top_mm"])
        orifice = float(p["orifice_mm"])
        cavity_depth = float(p.get("cavity_depth_mm", 12.0))
        inner_depth = float(p.get("inner_depth_mm", 45.0))

        # taper (锥盖模式)
        cap_taper_deg = float(p.get("cap_taper_deg", 0.0))

        # thread
        thr = p.get("thread", {}) or {}
        thr_on = bool(thr.get("enabled", True))
        thr_crest = float(thr.get("crest_dia_mm", 18.0))
        thr_depth = float(thr.get("depth_mm", 0.5))
        # root_dia 自动计算 = crest_dia - 2*depth（不再从参数读取）
        thr_root = thr_crest - 2 * thr_depth
        thr_pitch = float(thr.get("pitch_mm", 2.7))
        thr_turns = int(thr.get("turns", 2))
        thr_lead_angle = float(thr.get("lead_angle_deg", 3.0))  # 导程角
        thr_segmented = bool(thr.get("segmented", False))  # 分段螺纹

        # seal ring
        seal = p.get("seal_ring", {}) or {}
        seal_od = float(seal.get("od_mm", 17.5))
        seal_h = float(seal.get("height_mm", 3.0))
        seal_style = str(seal.get("style", "flat"))

        # brush
        brush = p.get("brush", {}) or {}
        brush_type = str(brush.get("type", "doe_foot"))
        brush_len = float(brush.get("length_mm", 12.0))
        brush_w = float(brush.get("width_mm", 10.0))
        brush_t = float(brush.get("thickness_mm", 4.0))

        # derived
        outer_r = outer_od / 2.0
        stem_r = stem_d / 2.0
        thr_crest_r = thr_crest / 2.0
        thr_root_r = thr_root / 2.0
        seal_r = seal_od / 2.0
        orifice_r = orifice / 2.0

        eps = 0.05

        # 截面类型（提前读取，后续螺纹检查需要用到）
        wand_cross_section = str(p.get("cross_section", "round"))
        wand_corner_r = float(p.get("corner_radius_mm", 1.5))

        # 多边形截面的内切圆半径（apothem），圆形截面等于外接圆半径
        _shell_inner_r = outer_r
        if _is_polygon(wand_cross_section):
            _shell_inner_r = outer_r * math.cos(math.pi / _n_sides(wand_cross_section))

        # ---- 参数合理性检查 ----
        # 螺纹必须能放进外壳内：缩小螺纹而非放大外壳（放大会导致刷杆溢出瓶盖）
        if thr_on:
            wall_need = 0.8  # 最小壁厚
            max_cavity_r = _shell_inner_r - wall_need
            max_crest_r = max_cavity_r - thr_depth - 0.3
            if thr_crest_r > max_crest_r:
                if max_crest_r > stem_r + 1.0:
                    old_crest = thr_crest
                    thr_crest_r = max_crest_r
                    thr_crest = thr_crest_r * 2.0
                    thr_root_r = thr_crest_r - thr_depth
                    thr_root = thr_root_r * 2.0
                    meta.setdefault("auto_adjusted", []).append({
                        "param": "thread.crest_dia_mm",
                        "original": old_crest,
                        "adjusted": thr_crest,
                        "reason": f"螺纹峰径({old_crest:.1f}mm)过大，缩小至{thr_crest:.1f}mm以适配外壳({outer_od:.1f}mm)"
                    })
                else:
                    thr_on = False
                    meta.setdefault("auto_adjusted", []).append({
                        "param": "thread.enabled",
                        "original": True,
                        "adjusted": False,
                        "reason": f"外壳({outer_od:.1f}mm)太小无法容纳螺纹，已禁用"
                    })

        # 顶部壁厚检查
        top_thickness = cap_h - cavity_depth
        if top_thickness < 1.0:
            # 自动调整内腔深度
            adjusted_cavity = cap_h - 1.5  # 保持1.5mm顶部壁厚
            meta.setdefault("auto_adjusted", []).append({
                "param": "cavity_depth_mm",
                "original": cavity_depth,
                "adjusted": adjusted_cavity,
                "reason": f"顶部壁厚({top_thickness:.1f}mm)过薄，已自动调整"
            })
            cavity_depth = adjusted_cavity

        # ---- Step 1: cap body (critical) ----
        if cap_taper_deg > 0:
            # 锥盖模式：外壳锥度匹配瓶盖内腔
            wand_taper_r = math.tan(math.radians(cap_taper_deg)) * cap_h
            wand_r_bottom = outer_r
            wand_r_top = max(outer_r - wand_taper_r, stem_r + 1.0, outer_r * 0.4)
        else:
            # 标准模式：0.3° 最小拔模角
            wand_draft_r = math.tan(math.radians(0.3)) * cap_h
            wand_r_bottom = outer_r
            wand_r_top = outer_r - wand_draft_r
            if wand_r_top < outer_r * 0.9:
                wand_r_top = outer_r * 0.95

        if wand_cross_section == "square":
            side_bottom = wand_r_bottom * 2
            side_top = wand_r_top * 2
            cap = self._rounded_rect_loft(side_bottom, side_top, wand_corner_r, cap_h, z0=0.0)
        elif _is_polygon(wand_cross_section):
            n = _n_sides(wand_cross_section)
            cap = self._polygon_loft(n, wand_r_bottom, wand_r_top, wand_corner_r, cap_h, z0=0.0)
        else:
            cap = self._loft_frustum(wand_r_bottom, wand_r_top, cap_h, z0=0.0)

        meta["cross_section"] = wand_cross_section  # 记录实际使用的截面

        # 盖子内腔（从底部向上挖空）
        wall = 0.8
        if cap_taper_deg > 0 and thr_on:
            # ★ 锥盖+螺纹模式：底部圆柱螺纹区 + 上部锥形过渡
            inner_cavity_r = thr_crest_r + thr_depth + 0.5
            # 确保内腔不超出外壳（多边形用内切圆半径）
            inner_cavity_r = min(inner_cavity_r, _shell_inner_r - wall) if _is_polygon(wand_cross_section) else min(inner_cavity_r, wand_r_bottom - wall)
            thread_zone_h = min(thr_pitch * thr_turns + 1.0, cavity_depth * 0.6)
            taper_zone_h = cavity_depth - thread_zone_h
            if cavity_depth > 0:
                # (a) 底部圆柱内腔 — 螺纹生存空间
                cyl_cavity = (
                    cq.Workplane("XY")
                    .workplane(offset=-eps)
                    .circle(inner_cavity_r)
                    .extrude(thread_zone_h + eps)
                )
                if taper_zone_h > 0.5:
                    # (b) 上部锥形过渡
                    inner_r_taper_top = max(wand_r_top - wall, stem_r + 0.5)
                    taper_cavity = self._loft_frustum(
                        inner_cavity_r, inner_r_taper_top,
                        taper_zone_h + eps, z0=thread_zone_h - eps
                    )
                    combined_cavity = cyl_cavity.union(taper_cavity)
                else:
                    combined_cavity = cyl_cavity
                cap = cap.cut(combined_cavity)
        elif cap_taper_deg > 0 and not thr_on:
            # 锥盖无螺纹：锥形内腔，保持等壁厚
            inner_r_bottom = max(wand_r_bottom - wall, stem_r + 0.5)
            inner_r_top = max(wand_r_top - wall, stem_r + 0.5)
            if cavity_depth > 0:
                if wand_cross_section == "square":
                    inner_side_b = max(inner_r_bottom * 2, stem_r * 2 + 1)
                    inner_side_t = max(inner_r_top * 2, stem_r * 2 + 1)
                    # ★ 层2C: 壁厚保障 — 内腔边长不超出外壳
                    inner_side_t = min(inner_side_t, side_top - 2 * wall)
                    inner_side_t = max(inner_side_t, stem_r * 2 + 0.5)  # 至少容纳杆身
                    inner_cr = max(0.5, wand_corner_r - wall)
                    cavity = self._rounded_rect_loft(
                        inner_side_b, inner_side_t, inner_cr, cavity_depth + eps, z0=-eps
                    )
                elif _is_polygon(wand_cross_section):
                    n = _n_sides(wand_cross_section)
                    inner_cr = max(0.3, wand_corner_r - wall)
                    cavity = self._polygon_loft(
                        n, inner_r_bottom, inner_r_top, inner_cr, cavity_depth + eps, z0=-eps
                    )
                else:
                    cavity = self._loft_frustum(
                        inner_r_bottom, inner_r_top,
                        cavity_depth + eps, z0=-eps
                    )
                cap = cap.cut(cavity)
        else:
            # 标准模式：圆柱内腔（螺纹需固定半径）
            inner_cavity_r = thr_crest_r + thr_depth + 0.5
            # 确保内腔不超出外壳
            inner_cavity_r = min(inner_cavity_r, _shell_inner_r - wall) if _is_polygon(wand_cross_section) else min(inner_cavity_r, outer_r - wall)
            if cavity_depth > 0:
                cavity = (
                    cq.Workplane("XY")
                    .workplane(offset=-eps)
                    .circle(inner_cavity_r)
                    .extrude(cavity_depth + eps)
                )
                cap = cap.cut(cavity)

        # 顶部圆角
        top_fillet = min(1.5, outer_r * 0.1)
        if top_fillet > 0.3:
            cap = self.try_feature(
                meta, "cap_top_fillet",
                lambda: cap.edges(">Z").fillet(top_fillet),
                cap
            )

        # ---- Step 2-5: 内螺纹 + 杆身 + 气密环 + 刷头（共享方法） ----
        thr_dict = {
            "enabled": thr_on, "crest_dia_mm": thr_crest,
            "depth_mm": thr_depth, "pitch_mm": thr_pitch,
            "turns": thr_turns, "lead_angle_deg": thr_lead_angle,
            "segmented": thr_segmented,
            "gap_angle_deg": float((p.get("thread", {}) or {}).get("gap_angle_deg", 20.0)),
        }
        cap = self._build_internal_thread(cap, inner_cavity_r, thr_dict, cavity_depth, meta)

        stem_dict = {
            "diameter_mm": stem_d, "length_mm": stem_len,
            "profile": stem_profile, "taper_ratio": stem_taper,
            "wall_mm": stem_wall,
        }
        cap, stem_bottom_z = self._build_stem_rod(cap, cap_h, stem_dict, inner_depth, cap_taper_deg, meta)

        seal_dict = {"od_mm": seal_od, "height_mm": seal_h, "style": seal_style}
        cap = self._build_seal_ring(cap, cavity_depth, seal_dict, stem_r, cap_taper_deg, wand_r_bottom, meta)

        brush_dict = {
            "type": brush_type, "length_mm": brush_len,
            "width_mm": brush_w, "thickness_mm": brush_t,
        }
        brush_z0 = stem_bottom_z - brush_len
        stem_taper_factor = stem_taper if stem_profile == "tapered" else 1.0
        cap = self._build_brush_head(cap, brush_z0, stem_r, brush_dict, stem_taper_factor, meta)

        # ---- Step 6: edge treatment (non-critical) ----
        # 盖子底边倒角
        bottom_chamfer = min(0.5, cap_h * 0.05)
        if bottom_chamfer > 0.1:
            cap = self.try_feature(
                meta, "bottom_chamfer",
                lambda: cap.faces("<Z").edges().chamfer(bottom_chamfer),
                cap
            )

        # ---- final sanity ----
        try:
            shp = cap.val()
            if not hasattr(shp, "Volume"):
                raise RuntimeError("val() is not a Shape")
            if shp.Volume() < 1e-6:  # type: ignore[union-attr]
                raise RuntimeError("volume ~ 0")
        except Exception as e:
            raise RuntimeError(f"wand sanity failed: {e}")

        return cap


def compute_profile_constraints(component_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute profile editing constraints for a component.
    Returns safe zone boundaries for the ProfileEditor SVG canvas.
    """
    if component_id == "cap":
        OD = float(params.get("outer_od_mm", 24))
        H = float(params.get("height_mm", 28))
        ID = float(params.get("inner_id_mm", OD - 1.6))
        cav = float(params.get("cavity_depth_mm", H - 1.5))
        taper_deg = max(float(params.get("taper_deg", 0)), 0.5)

        r0 = OD / 2.0
        r1 = max(OD / 2.0 - math.tan(math.radians(taper_deg)) * H, OD * 0.35)
        r_inner = ID / 2.0

        return {
            "r_start": round(r0, 2),
            "z_start": 0.0,
            "r_end": round(r1, 2),
            "z_end": round(H, 2),
            "r_min": round(r_inner + 0.3, 2),
            "r_max": round(r0 * 1.05, 2),
            "r_min_z_max": round(cav, 2),  # r_min 仅在 z < cavity 的区域生效
            "cavity_r": round(r_inner, 2),
            "cavity_z_max": round(cav, 2),
        }

    elif component_id == "bottle":
        body_od = float(params.get("body_od_mm", 24))
        H = float(params.get("height_mm", params.get("total_height_mm", 65)))
        neck_od = float(params.get("neck_od_mm", 18))
        neck_h = float(params.get("neck_height_mm", 8))
        shoulder_h = float(params.get("shoulder_height_mm", 6))
        wall = float(params.get("wall_thickness_mm", 1.5))

        body_r = body_od / 2.0
        neck_r = neck_od / 2.0
        body_h = H - neck_h - shoulder_h
        inner_r = (body_od - 2 * wall) / 2.0

        return {
            "r_start": round(body_r, 2),
            "z_start": 0.0,
            "r_end": round(neck_r, 2),
            "z_end": round(body_h + shoulder_h, 2),
            "r_min": round(inner_r + 0.3, 2),
            "r_max": round(body_r * 1.05, 2),
            "r_min_z_max": round(body_h, 2),  # r_min 仅在 z < body_h 的瓶身区域生效
            "cavity_r": round(inner_r, 2),
            "cavity_z_max": round(body_h, 2),
            "supports_asymmetric": True,
        }

    else:
        raise ValueError(f"No profile constraints for component: {component_id}")
