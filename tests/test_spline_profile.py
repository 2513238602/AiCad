# -*- coding: utf-8 -*-
"""
Spline 轮廓生成测试 — Bottle + Cap spline 模式 + 配合关系验证

用法：
    conda activate AiCad
    cd g:/AiCad
    python -m pytest tests/test_spline_profile.py -v
"""
from __future__ import annotations

import sys
import json
import math

sys.path.insert(0, "g:/AiCad/src")

import pytest

try:
    import cadquery as cq  # noqa: F401
    HAS_CQ = True
except ImportError:
    HAS_CQ = False

# 确保派生规则已注册
import products.lip_gloss.derived_params  # noqa: F401

from core.modeler import Modeler
from core.assembly import (
    compute_assembly_positions,
    check_radial_interference,
    verify_assembly_quality,
    _bottle_od_at_z,
)

# ── 公共参数 ───────────────────────────────────────────────────────────

BOTTLE_BASE = {
    "height_mm": 70.0,
    "body_od_mm": 24.0,
    "shape": "cyl",
    "taper_deg": 0.5,
    "neck_od_mm": 18.0,
    "neck_height_mm": 10.0,
    "lip_thickness_mm": 1.0,
    "thread": {"enabled": False},
    "shoulder_height_mm": 10.0,
    "shoulder_style": "round",
    "shoulder_fillet_mm": 3.0,
    "inner_depth_mm": 55.0,
    "wall_thickness_mm": 1.2,
    "bottom_thickness_mm": 2.0,
    "bottom_style": "flat",
    "bottom_concave_mm": 0.0,
    "bottom_fillet_mm": 1.5,
}

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

WAND_PARAMS = {
    "wand_type": "cap_integrated",
    "total_height_mm": 65.0,
    "outer_od_mm": 21.5,
    "cap_height_mm": 19.0,
    "stem_diameter_mm": 4.0,
    "stem_length_mm": 40.0,
    "stem_profile": "round",
    "mouth_to_top_mm": 12.0,
    "orifice_mm": 7.0,
    "cavity_depth_mm": 13.0,
    "inner_depth_mm": 45.0,
    "thread": {
        "enabled": True,
        "crest_dia_mm": 18.0,
        "pitch_mm": 2.7,
        "turns": 2,
        "depth_mm": 0.5,
        "lead_angle_deg": 3.0,
    },
    "seal_ring": {"od_mm": 16.0, "height_mm": 3.0, "style": "flat"},
    "brush": {
        "type": "doe_foot",
        "length_mm": 12.0,
        "width_mm": 10.0,
        "thickness_mm": 4.0,
    },
    "finish": "18-415",
    "fit_clearance_mm": 0.15,
}

WIPER_PARAMS = {
    "height_mm": 4.0,
    "outer_od_mm": 15.5,
    "inner_id_mm": 12.0,
    "orifice_mm": 7.0,
    "orifice_edge_mm": 0.3,
    "flange_od_mm": 15.8,
    "flange_id_mm": 14.5,
    "flange_height_mm": 1.5,
    "flange_position": "bottom",
    "diaphragm_style": "flat",
    "diaphragm_thickness_mm": 0.8,
    "fit_clearance_mm": 0.1,
    "material": "LDPE",
    "finish": "18-415",
}


# ── 测试用例 ───────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_CQ, reason="CadQuery 未安装")
class TestBottleClassicRegression:
    """Bottle classic 模式回归测试：确保原有功能不受影响"""

    def test_classic_generates_valid_solid(self):
        modeler = Modeler()
        meta = {}
        solid = modeler.build("bottle", {**BOTTLE_BASE, "profile_mode": "classic"}, meta=meta)
        vol = solid.val().Volume()
        assert vol > 100, f"体积过小: {vol}"
        assert meta.get("profile_mode") == "classic"

    def test_classic_default_when_no_profile_mode(self):
        """不传 profile_mode 时应默认为 classic"""
        modeler = Modeler()
        meta = {}
        solid = modeler.build("bottle", BOTTLE_BASE, meta=meta)
        vol = solid.val().Volume()
        assert vol > 100


@pytest.mark.skipif(not HAS_CQ, reason="CadQuery 未安装")
class TestBottleSpline:
    """Bottle spline 模式测试"""

    def test_spline_default_profile(self):
        """空 JSON 自动生成有效实体"""
        modeler = Modeler()
        meta = {}
        params = {**BOTTLE_BASE, "profile_mode": "spline", "profile_points_json": "[]"}
        solid = modeler.build("bottle", params, meta=meta)
        vol = solid.val().Volume()
        assert vol > 100, f"spline 默认轮廓体积过小: {vol}"
        assert meta.get("profile_mode") == "spline"
        assert "profile_points" in meta

    def test_spline_custom_profile(self):
        """自定义 6 点轮廓生成有效 STEP"""
        pts = [
            [12.0, 0.0],
            [12.3, 10.0],
            [12.5, 25.0],
            [12.2, 40.0],
            [10.5, 52.0],
            [9.0, 60.0],
        ]
        modeler = Modeler()
        meta = {}
        params = {
            **BOTTLE_BASE,
            "profile_mode": "spline",
            "profile_points_json": json.dumps(pts),
        }
        solid = modeler.build("bottle", params, meta=meta)
        vol = solid.val().Volume()
        assert vol > 100, f"spline 自定义轮廓体积过小: {vol}"

    def test_spline_wall_thickness_safety(self):
        """半径过小导致壁厚不足时应报错（瓶身区域 z ≤ body_h）"""
        # inner_r_body = (24 - 2*1.2)/2 = 10.8, min_r = 10.8 + 0.8 = 11.6
        # body_h = 70 - 10 - 10 = 50, 点 Z=20 在瓶身区域内，r=5 应被拒绝
        pts = [
            [12.0, 0.0],
            [5.0, 20.0],  # 半径远小于最小壁厚要求（且在 body 区域内）
            [9.0, 60.0],
        ]
        modeler = Modeler()
        with pytest.raises(ValueError, match="壁厚"):
            modeler.build("bottle", {
                **BOTTLE_BASE,
                "profile_mode": "spline",
                "profile_points_json": json.dumps(pts),
            }, meta={})

    def test_spline_invalid_z_order(self):
        """Z 值非单调递增应报错"""
        pts = [
            [12.0, 0.0],
            [12.0, 30.0],
            [11.0, 20.0],  # Z 回退
            [9.0, 60.0],
        ]
        modeler = Modeler()
        with pytest.raises(ValueError, match="单调递增"):
            modeler.build("bottle", {
                **BOTTLE_BASE,
                "profile_mode": "spline",
                "profile_points_json": json.dumps(pts),
            }, meta={})

    def test_spline_too_few_points(self):
        """少于 3 个点时自动补充默认轮廓（不报错）"""
        modeler = Modeler()
        meta = {}
        params = {
            **BOTTLE_BASE,
            "profile_mode": "spline",
            "profile_points_json": json.dumps([[12, 0], [9, 60]]),
        }
        solid = modeler.build("bottle", params, meta=meta)
        # 应自动生成默认轮廓，成功构建
        assert solid.val().Volume() > 100


@pytest.mark.skipif(not HAS_CQ, reason="CadQuery 未安装")
class TestCapSpline:
    """Cap spline 模式测试"""

    def test_cap_classic_regression(self):
        """Cap classic 模式回归"""
        modeler = Modeler()
        meta = {}
        solid = modeler.build("cap", {**CAP_BASE, "profile_mode": "classic"}, meta=meta)
        assert solid.val().Volume() > 50

    def test_cap_spline_default_profile(self):
        """Cap 空 JSON 自动生成有效瓶盖"""
        modeler = Modeler()
        meta = {}
        params = {**CAP_BASE, "profile_mode": "spline", "profile_points_json": "[]"}
        solid = modeler.build("cap", params, meta=meta)
        assert solid.val().Volume() > 50
        assert meta.get("profile_mode") == "spline"

    def test_cap_spline_custom_profile(self):
        """弧形瓶盖自定义轮廓"""
        pts = [
            [12.0, 0.0],
            [12.2, 8.0],
            [12.1, 18.0],
            [11.5, 25.0],
        ]
        modeler = Modeler()
        meta = {}
        params = {
            **CAP_BASE,
            "profile_mode": "spline",
            "profile_points_json": json.dumps(pts),
        }
        solid = modeler.build("cap", params, meta=meta)
        assert solid.val().Volume() > 50

    def test_cap_spline_grip_degradation(self):
        """spline 模式下防滑纹应降级"""
        modeler = Modeler()
        meta = {}
        params = {
            **CAP_BASE,
            "profile_mode": "spline",
            "profile_points_json": "[]",
            "grip": {"style": "ribs", "count": 24, "depth_mm": 0.3},
        }
        solid = modeler.build("cap", params, meta=meta)
        assert solid.val().Volume() > 50
        # 检查降级记录
        degraded = meta.get("degraded", [])
        has_grip_skip = any(
            "grip_texture_spline_skip" in str(d) for d in degraded
        )
        assert has_grip_skip, "spline 模式下 grip 应被降级"


@pytest.mark.skipif(not HAS_CQ, reason="CadQuery 未安装")
class TestSplineAssemblyFit:
    """四组件装配配合关系验证（核心评估指标）"""

    def _make_spline_params(self):
        """生成 spline 模式的 bottle + cap 参数"""
        bottle_pts = [
            [12.0, 0.0],
            [12.3, 10.0],
            [12.5, 25.0],
            [12.2, 40.0],
            [9.8, 52.0],   # 肩部收窄更快，避免与 wand 干涉
            [9.0, 60.0],
        ]
        cap_pts = [
            [12.0, 0.0],
            [12.2, 8.0],
            [12.1, 18.0],
            [11.5, 25.0],
        ]
        bottle_p = {
            **BOTTLE_BASE,
            "profile_mode": "spline",
            "profile_points_json": json.dumps(bottle_pts),
            "thread": {
                "enabled": True,
                "pitch_mm": 2.7,
                "turns": 2,
                "depth_mm": 0.5,
                "lead_angle_deg": 3.0,
            },
        }
        cap_p = {
            **CAP_BASE,
            "profile_mode": "spline",
            "profile_points_json": json.dumps(cap_pts),
        }
        return {
            "bottle": bottle_p,
            "cap": cap_p,
            "wand": WAND_PARAMS,
            "wiper": WIPER_PARAMS,
        }

    def test_spline_four_component_assembly(self):
        """spline cap + spline bottle + wiper + wand 装配无干涉"""
        component_params = self._make_spline_params()

        # 1. 验证所有组件可以独立构建
        modeler = Modeler()
        for comp_id in ["bottle", "cap", "wand", "wiper"]:
            meta = {}
            solid = modeler.build(comp_id, component_params[comp_id], meta=meta)
            vol = solid.val().Volume()
            assert vol > 10, f"{comp_id} 体积过小: {vol}"

        # 2. 装配定位
        positions = compute_assembly_positions(component_params)
        assert "bottle" in positions
        assert "cap" in positions

        # 3. 径向干涉检测
        issues = check_radial_interference(component_params, positions)
        hard_issues = [i for i in issues if i["severity"] == "hard"]
        assert len(hard_issues) == 0, f"发现硬干涉: {hard_issues}"

        # 4. 质量验收
        quality = verify_assembly_quality(component_params, positions)
        failed = [c for c in quality["checks"] if not c["pass"]]
        assert quality["pass"], f"质量验收失败: {failed}"

    def test_spline_cap_inner_cavity_intact(self):
        """spline 瓶盖内腔深度/内径不受影响"""
        component_params = self._make_spline_params()
        cap_p = component_params["cap"]
        modeler = Modeler()
        meta = {}
        solid = modeler.build("cap", cap_p, meta=meta)

        # 内腔参数仍为标量值
        assert cap_p["inner_id_mm"] == 22.4
        assert cap_p["cavity_depth_mm"] == 23.5

        # 实体有效
        vol = solid.val().Volume()
        assert vol > 50

    def test_spline_thread_parameters_match(self):
        """spline 模式下螺纹参数传递正确"""
        component_params = self._make_spline_params()
        b_thr = component_params["bottle"]["thread"]
        w_thr = component_params["wand"]["thread"]

        # 螺距/圈数/牙深应匹配
        assert abs(b_thr["pitch_mm"] - w_thr["pitch_mm"]) < 0.01
        assert b_thr["turns"] == w_thr["turns"]
        assert abs(b_thr["depth_mm"] - w_thr["depth_mm"]) < 0.01

    def test_spline_wiper_neck_fit(self):
        """spline 模式下内塞外径 < 颈部内径"""
        component_params = self._make_spline_params()
        neck_od = component_params["bottle"]["neck_od_mm"]
        lip_t = component_params["bottle"]["lip_thickness_mm"]
        neck_id = neck_od - 2 * lip_t
        wiper_od = component_params["wiper"]["outer_od_mm"]
        assert wiper_od < neck_id, f"内塞外径({wiper_od}) >= 颈内径({neck_id})"


class TestBottleOdAtZSpline:
    """_bottle_od_at_z() spline 模式单元测试"""

    def test_spline_interpolation(self):
        """spline 控制点插值正确"""
        pts = [(12.0, 0.0), (12.5, 30.0), (9.0, 60.0)]
        # Z=15 在第一段 (0,30)，t=0.5，r = 12 + 0.5*(12.5-12) = 12.25 → OD=24.5
        od = _bottle_od_at_z(
            15.0, 70.0, 10.0, 10.0, 24.0, 18.0,
            profile_mode="spline", profile_points=pts,
        )
        assert abs(od - 24.5) < 0.01, f"OD at Z=15 = {od}, expected 24.5"

    def test_spline_neck_region(self):
        """颈部区域仍返回 neck_od"""
        pts = [(12.0, 0.0), (12.5, 30.0), (9.0, 60.0)]
        od = _bottle_od_at_z(
            65.0, 70.0, 10.0, 10.0, 24.0, 18.0,
            profile_mode="spline", profile_points=pts,
        )
        assert od == 18.0, f"颈部 OD = {od}, expected 18.0"

    def test_classic_unchanged(self):
        """classic 模式行为不变"""
        od1 = _bottle_od_at_z(0.0, 70.0, 10.0, 10.0, 24.0, 18.0)
        od2 = _bottle_od_at_z(
            0.0, 70.0, 10.0, 10.0, 24.0, 18.0,
            profile_mode="classic", profile_points=None,
        )
        assert abs(od1 - od2) < 0.001


class TestValidateProfile:
    """_validate_profile() 单元测试"""

    def test_valid_profile(self):
        modeler = Modeler()
        pts = [(12.0, 0.0), (12.5, 30.0), (9.0, 60.0)]
        result = modeler._validate_profile(pts, max_r=13.0)
        assert result == pts

    def test_too_few_points(self):
        modeler = Modeler()
        with pytest.raises(ValueError, match="至少需要 3"):
            modeler._validate_profile([(12, 0), (9, 60)], max_r=13)

    def test_z_not_increasing(self):
        modeler = Modeler()
        with pytest.raises(ValueError, match="单调递增"):
            modeler._validate_profile([(12, 0), (12, 30), (9, 20)], max_r=13)

    def test_negative_radius(self):
        modeler = Modeler()
        with pytest.raises(ValueError, match="半径必须为正"):
            modeler._validate_profile([(12, 0), (-1, 30), (9, 60)], max_r=13)

    def test_radius_exceeds_max(self):
        modeler = Modeler()
        with pytest.raises(ValueError, match="超出最大值"):
            modeler._validate_profile([(12, 0), (15, 30), (9, 60)], max_r=13)

    def test_radius_below_min_wall(self):
        modeler = Modeler()
        with pytest.raises(ValueError, match="壁厚"):
            modeler._validate_profile(
                [(12, 0), (10, 30), (9, 60)],
                max_r=13, min_r_body=11.0, min_r_z_max=60.0,
            )


class TestDefaultProfileGeneration:
    """默认轮廓生成函数测试"""

    def test_bottle_default_profile(self):
        from products.lip_gloss.derived_params import generate_default_bottle_profile
        pts = generate_default_bottle_profile(12.0, 50.0, 10.0, 9.0, 0.5)
        assert len(pts) >= 3
        # 首点 Z=0
        assert pts[0][1] == 0.0
        # 末点半径=neck_r, Z=body_h+shoulder_h
        assert pts[-1][0] == 9.0
        assert pts[-1][1] == 60.0
        # Z 单调递增
        for i in range(1, len(pts)):
            assert pts[i][1] > pts[i - 1][1]

    def test_cap_default_profile(self):
        from products.lip_gloss.derived_params import generate_default_cap_profile
        pts = generate_default_cap_profile(12.0, 11.0, 25.0)
        assert len(pts) >= 3
        assert pts[0][1] == 0.0
        assert pts[-1][1] == 25.0
        for i in range(1, len(pts)):
            assert pts[i][1] > pts[i - 1][1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
