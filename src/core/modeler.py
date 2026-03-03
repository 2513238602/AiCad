# -*- coding: utf-8 -*-
from __future__ import annotations

import math
from typing import Any, Callable, Dict, cast

import cadquery as cq


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
            return fn()
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
        cq.exporters.export(wp, out_path)

    def build(self, component_id: str, params: Dict[str, Any], meta: Dict[str, Any] | None = None) -> cq.Workplane:
        meta = meta or {}
        fn = getattr(self, f"build_{component_id}", None)
        if not callable(fn):
            raise KeyError(f"no builder: build_{component_id}")
        return cast(cq.Workplane, fn(params, meta))

    # -----------------------------
    # geometry primitives
    # -----------------------------
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

    def _polar_union(self, solids: list[cq.Workplane]) -> cq.Workplane:
        out = solids[0]
        for s in solids[1:]:
            out = out.union(s)
        return out

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
        delta_r = math.tan(taper_rad) * H
        OD_top = max(OD - delta_r, OD * 0.7)

        r0 = OD / 2.0  # 底部半径（开口侧）
        r1 = OD_top / 2.0  # 顶部半径
        r_inner = ID / 2.0

        eps = 0.15  # 重叠量

        # ---- Step 1: build outer shell (always use loft for draft) ----
        cap = self._loft_frustum(r0, r1, H, z0=0.0)

        # ---- Step 2: edge fillets (non-critical, enforce minimums) ----
        # 注塑件最低圆角：外角 R≥0.5mm，内角 R≥0.3mm
        MIN_EXT_FILLET = 0.5
        MIN_INT_FILLET = 0.3
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

        # 圆顶效果
        if top_shape == "dome":
            dome_r = min(r1 * 0.4, H * 0.15)
            if dome_r > 0.5:
                cap = self.try_feature(
                    meta, "top_dome",
                    lambda: cap.edges(">Z").fillet(dome_r),
                    cap
                )

        # ---- Step 3: cavity cut (critical) ----
        if cav <= 0 or cav >= H:
            raise RuntimeError(f"cavity_depth_mm invalid: cav={cav}, H={H}")

        # 内腔跟随外形锥度
        if taper_deg > 0:
            # 计算内腔顶部半径（保持壁厚）
            r_inner_top = r1 - wall
            if r_inner_top < r_inner * 0.5:
                r_inner_top = r_inner * 0.8
            cav_solid = self._loft_frustum(r_inner, r_inner_top, cav + 2 * eps, z0=-eps)
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
        # 从 inner_id 渐变到 outer_od - 0.4mm（仅留 0.2mm 壁厚边缘）
        CHAMFER_WALL = 0.05  # 倒角边缘最小壁厚 mm（更激进以减小cap-肩部缝隙）
        CHAMFER_H = 3.0      # 倒角高度 mm
        r_chamfer_bottom = r0 - CHAMFER_WALL  # r0 = OD/2（底部外半径）
        if r_chamfer_bottom > r_inner and CHAMFER_H > 0:
            chamfer_cut = self._loft_frustum(
                r_chamfer_bottom, r_inner, CHAMFER_H,
                z0=-eps
            )
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
        if grip_style == "ribs" and grip_count >= 6 and grip_depth > 0.05:
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
        thr_on = bool(thr.get("enabled", False))
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

        # 注塑最低拔模角 0.5°
        MFG_MIN_DRAFT = 0.5
        eff_taper_deg = taper_deg
        if shape != "taper" or taper_deg < MFG_MIN_DRAFT:
            eff_taper_deg = max(taper_deg, MFG_MIN_DRAFT)
            if taper_deg < MFG_MIN_DRAFT:
                meta.setdefault("mfg_adjustments", []).append(
                    f"瓶身外壁拔模角从{taper_deg:.1f}°提升至{MFG_MIN_DRAFT}°（注塑最低要求）"
                )

        # 统一使用 loft 生成带拔模角的瓶身
        # body_od = 最大直径（瓶底），拔模角全部向顶部收窄
        # 这样 body_od == cap_od 时外观完全齐平
        eff_taper_rad = math.radians(eff_taper_deg)
        delta_r = math.tan(eff_taper_rad) * body_h
        bottom_r_body = body_r                # body_od 就是瓶底最大直径
        top_r_body = body_r - delta_r         # 顶部因拔模角收窄
        bottle = self._loft_frustum(bottom_r_body, top_r_body, body_h + eps, z0=0.0)

        # ---- Step 2: shoulder transition (critical) ----
        # 从瓶身顶部半径过渡到颈部半径
        # 使用 top_r_body 确保与带拔模角的瓶身顺滑衔接
        shoulder_bottom_z = body_h - eps
        shoulder_top_z = body_h + shoulder_h
        shoulder_start_r = top_r_body  # 与瓶身顶部衔接

        if shoulder_style == "angular":
            shoulder = self._loft_frustum(shoulder_start_r, neck_r, shoulder_h + eps, z0=shoulder_bottom_z)
        elif shoulder_style == "sloped":
            shoulder = self._loft_frustum(shoulder_start_r, neck_r, shoulder_h + eps, z0=shoulder_bottom_z)
        else:
            # round：先用 loft，然后尝试 fillet
            shoulder = self._loft_frustum(shoulder_start_r, neck_r, shoulder_h + eps, z0=shoulder_bottom_z)

        bottle = bottle.union(shoulder)

        # ---- Step 3: neck cylinder (critical, with minimum draft) ----
        # 颈部从 shoulder_top_z - eps 开始，确保与肩部有重叠
        # 颈部也需要最小拔模角（0.3°，因为有螺纹配合所以稍小）
        neck_draft_deg = 0.3
        neck_draft_r = math.tan(math.radians(neck_draft_deg)) * neck_h
        neck_r_bottom = neck_r + neck_draft_r / 2.0
        neck_r_top = neck_r - neck_draft_r / 2.0
        neck = self._loft_frustum(neck_r_bottom, neck_r_top, neck_h + eps,
                                  z0=shoulder_top_z - eps)
        bottle = bottle.union(neck)

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
        bottle = bottle.cut(neck_cavity)

        # 瓶身内腔（较宽）- 仅覆盖圆柱体段（底厚到肩部起始处）
        # 不能延伸到肩部区域，否则 inner_r_body > neck_r 时会穿透肩壁
        body_cavity_top = body_h
        body_cavity_bottom = bottom_t
        body_cavity_h = body_cavity_top - body_cavity_bottom

        if body_cavity_h > 0:
            body_cavity = (
                cq.Workplane("XY")
                .workplane(offset=body_cavity_bottom)
                .circle(inner_r_body)
                .extrude(body_cavity_h + eps)
            )
            bottle = bottle.cut(body_cavity)

        # 肩部内腔过渡（从 neck 内径到 body 内径）
        # 注意：使用 body_h 作为基准（实际肩部起始位置）
        shoulder_cavity = self._loft_frustum(
            inner_r_body, inner_r_neck, shoulder_h + eps, z0=body_h - eps / 2
        )
        bottle = bottle.cut(shoulder_cavity)

        # ---- Step 5: outer thread (non-critical, allow degrade) ----
        if thr_on:
            thread_len = thr_pitch * thr_turns
            thread_z0 = H - neck_h + 0.5  # 螺纹起始位置（从颈部底部略上）
            thread_z1 = thread_z0 + thread_len

            if thread_z1 > H - 0.5:
                thread_z1 = H - 0.5
                thread_len = thread_z1 - thread_z0

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
                            thread_solid = thread_solid.union(s)
                        return bottle.union(thread_solid)

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
                        return bottle.union(thread_solid)

                    bottle = self.try_feature(meta, "outer_thread", make_thread_union, bottle)

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
            # 底部外凸（使用 fillet 近似）
            pass  # 暂不实现

        # ---- Step 7: edge fillets (non-critical, enforce minimums) ----
        MIN_EXT_FILLET = 0.5
        rf = max(bottom_fillet, MIN_EXT_FILLET)
        rf = min(rf, body_r * 0.3)
        rf = max(rf, MIN_EXT_FILLET)
        bottle = self.try_feature(
            meta, "bottom_fillet",
            lambda: bottle.edges("<Z").fillet(rf),
            bottle
        )

        if shoulder_style == "round" and shoulder_fillet > 1e-6:
            # 尝试在肩部添加圆角
            sf = min(shoulder_fillet, min(body_r - neck_r, shoulder_h) * 0.4)
            if sf > 0.5:
                bottle = self.try_feature(
                    meta, "shoulder_fillet",
                    lambda: bottle.faces(">Z").edges().fillet(sf * 0.3),
                    bottle
                )

        # 瓶口顶部倒角
        lip_chamfer = min(0.3, lip_t * 0.2)
        if lip_chamfer > 0.05:
            bottle = self.try_feature(
                meta, "lip_chamfer",
                lambda: bottle.edges(">Z").chamfer(lip_chamfer),
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

        # ---- 参数合理性检查 ----
        # 盖子外径必须大于螺纹峰径+壁厚，否则螺纹会露在外面
        min_wall_total = thr_depth + 0.5 + 1.0  # 牙深 + 间隙 + 最小壁厚
        min_outer_od = thr_crest + 2 * min_wall_total
        if outer_od < min_outer_od:
            # 自动调整外径
            meta.setdefault("auto_adjusted", []).append({
                "param": "outer_od_mm",
                "original": outer_od,
                "adjusted": min_outer_od,
                "reason": f"外径({outer_od:.1f}mm)小于螺纹峰径({thr_crest:.1f}mm)+壁厚，已自动调整"
            })
            outer_od = min_outer_od
            outer_r = outer_od / 2.0

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

        # ---- Step 1: cap body (critical, with minimum draft) ----
        # 盖子主体：外径为 outer_od，高度为 cap_h
        # 最小拔模角 0.3°（内部配合件，稍小即可）
        wand_draft_deg = 0.3
        wand_draft_r = math.tan(math.radians(wand_draft_deg)) * cap_h
        wand_r_bottom = outer_r
        wand_r_top = outer_r - wand_draft_r
        if wand_r_top < outer_r * 0.9:
            wand_r_top = outer_r * 0.95
        cap = self._loft_frustum(wand_r_bottom, wand_r_top, cap_h, z0=0.0)

        # 盖子内腔（从底部向上挖空）
        # 内螺纹设计：螺纹峰（尖端）向中心凸出，螺纹底（根部）与内腔壁融合
        # 内腔半径 = 螺纹峰径（这样螺牙可以从内腔壁向中心凸出）
        # 修正：先切一个较大的内腔，让螺纹有足够空间
        inner_cavity_r = thr_crest_r + thr_depth + 0.5  # 内腔半径（给螺纹留空间）
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

        # ---- Step 2: internal thread (critical if enabled) ----
        if thr_on and thr_turns > 0 and thr_pitch > 0:
            thread_len = thr_pitch * thr_turns
            thread_z0 = 0.5  # 螺纹从盖子底部开始
            thread_z1 = min(thread_z0 + thread_len, cavity_depth - 0.5)
            actual_thread_len = thread_z1 - thread_z0
            actual_turns = max(1, int(actual_thread_len / thr_pitch))

            if actual_thread_len > 1.0:
                # 内螺纹：三角牙型，从内腔壁向中心凸出
                # 螺纹根部（外侧）与内腔壁融合，螺纹峰（内侧）向中心凸出
                t = thr_pitch * 0.4
                # 螺纹根部半径 = 内腔半径（与内腔壁融合）
                thread_root_r = inner_cavity_r - 0.05
                # 螺纹峰部半径 = 峰径（向中心凸出）
                pts = [
                    (thread_root_r, -t / 2.0),
                    (thread_root_r, t / 2.0),
                    (thr_crest_r, 0.0),  # 尖端向中心凸出到峰径
                ]

                # 计算扭转角度（考虑导程角）
                base_angle = 360.0 * actual_turns
                lead_factor = 1.0 + thr_lead_angle / 90.0
                twist_angle = base_angle * lead_factor

                if thr_segmented:
                    # 分段螺纹
                    def make_segmented_inner_thread() -> cq.Workplane:
                        segments_per_turn = 2
                        gap_angle = float(thr.get("gap_angle_deg", 20.0))  # 间隔角度（可配置）
                        seg_angle = (360.0 - segments_per_turn * gap_angle) / segments_per_turn
                        seg_len = thr_pitch * (seg_angle / 360.0)

                        all_segs = []
                        for turn_i in range(actual_turns):
                            for seg_i in range(segments_per_turn):
                                start_angle = turn_i * 360.0 + seg_i * (seg_angle + gap_angle)
                                z_offset = thread_z0 + (start_angle / 360.0) * thr_pitch

                                if z_offset + seg_len > thread_z0 + actual_thread_len:
                                    continue

                                # 数学旋转截面点
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
                            return cap

                        thread_solid = all_segs[0]
                        for s in all_segs[1:]:
                            thread_solid = thread_solid.union(s)
                        return cap.union(thread_solid)  # 内螺纹用 union 添加

                    cap = self.try_feature(meta, "inner_thread_segmented", make_segmented_inner_thread, cap)
                else:
                    # 连续螺纹
                    def make_inner_thread() -> cq.Workplane:
                        thread_solid = (
                            cq.Workplane("XY")
                            .workplane(offset=thread_z0)
                            .polyline(pts)
                            .close()
                            .twistExtrude(actual_thread_len, angleDegrees=twist_angle)
                        )
                        return cap.union(thread_solid)  # 内螺纹用 union 添加

                    cap = self.try_feature(meta, "inner_thread", make_inner_thread, cap)

        # ---- Step 3: stem rod (critical) ----
        # 杆身：从盖子顶部向下延伸
        stem_top_z = cap_h
        stem_bottom_z = stem_top_z - stem_len

        if stem_profile == "tapered" and stem_taper < 1.0:
            # 锥形杆身：顶部粗，底部细
            stem_r_top = stem_r
            stem_r_bottom = stem_r * stem_taper
            stem = self._loft_frustum(stem_r_bottom, stem_r_top, stem_len, z0=stem_bottom_z)
        elif stem_profile == "oval":
            # 椭圆形杆身
            stem = (
                cq.Workplane("XY")
                .workplane(offset=stem_bottom_z)
                .ellipse(stem_r, stem_r * 0.7)
                .extrude(stem_len)
            )
        else:
            # 圆形杆身
            stem = (
                cq.Workplane("XY")
                .workplane(offset=stem_bottom_z)
                .circle(stem_r)
                .extrude(stem_len)
            )

        cap = cap.union(stem)

        # 杆身空心（如果有壁厚）
        if stem_wall > 0 and stem_wall < stem_r:
            inner_stem_r = stem_r - stem_wall
            if inner_stem_r > 0.5 and inner_depth > 0:
                stem_cavity = (
                    cq.Workplane("XY")
                    .workplane(offset=stem_top_z - inner_depth)
                    .circle(inner_stem_r)
                    .extrude(inner_depth + eps)
                )
                cap = cap.cut(stem_cavity)

        # ---- Step 4: seal ring (critical) ----
        # 气密环：位于盖子底部内侧
        seal_z0 = cavity_depth - seal_h
        if seal_z0 < 0:
            seal_z0 = 0

        if seal_style == "conical":
            # 锥形密封环
            seal_ring = self._loft_frustum(seal_r * 0.95, seal_r, seal_h, z0=seal_z0)
        elif seal_style == "ring":
            # 环形凸起
            seal_ring = (
                cq.Workplane("XY")
                .workplane(offset=seal_z0)
                .circle(seal_r)
                .circle(seal_r - 1.0)
                .extrude(seal_h)
            )
        else:
            # 平面密封（实心圆柱环）
            seal_ring = (
                cq.Workplane("XY")
                .workplane(offset=seal_z0)
                .circle(seal_r)
                .extrude(seal_h)
            )

        cap = cap.union(seal_ring)

        # 在密封环中心开孔（仅让杆身通过）
        seal_hole_r = stem_r + 0.5
        seal_hole_height = seal_h + 2 * eps  # 仅贯穿密封环自身
        seal_hole = (
            cq.Workplane("XY")
            .workplane(offset=seal_z0 - eps)
            .circle(seal_hole_r)
            .extrude(seal_hole_height)
        )
        cap = cap.cut(seal_hole)

        # ---- Step 5: brush head (non-critical) ----
        # 刷头：在杆身底部
        brush_z0 = stem_bottom_z - brush_len

        if brush_type == "doe_foot":
            # Doe-foot 刷头：扁平椭圆形
            def _make_doe_foot() -> cq.Workplane:
                # Loft 连接
                brush_head = (
                    cq.Workplane("XY")
                    .workplane(offset=brush_z0)
                    .ellipse(brush_w / 2.0, brush_t / 2.0)
                    .workplane(offset=brush_len)
                    .circle(stem_r * (stem_taper if stem_profile == "tapered" else 1.0))
                    .loft(combine=True)
                )
                return cap.union(brush_head)

            cap = self.try_feature(meta, "brush_doe_foot", _make_doe_foot, cap)

        elif brush_type == "silicone_spatula":
            # 硅胶刮刀：扁平矩形
            def _make_spatula() -> cq.Workplane:
                spatula = (
                    cq.Workplane("XY")
                    .workplane(offset=brush_z0)
                    .rect(brush_w, brush_t)
                    .workplane(offset=brush_len * 0.7)
                    .circle(stem_r)
                    .loft(combine=True)
                )
                return cap.union(spatula)

            cap = self.try_feature(meta, "brush_spatula", _make_spatula, cap)

        else:
            # 纤维刷头：简化为锥形
            def _make_fiber_brush() -> cq.Workplane:
                brush_head = self._loft_frustum(brush_w / 4.0, stem_r, brush_len, z0=brush_z0)
                return cap.union(brush_head)

            cap = self.try_feature(meta, "brush_fiber", _make_fiber_brush, cap)

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
