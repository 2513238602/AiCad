# -*- coding: utf-8 -*-
"""Reusable Blender display-case modules for the browser showroom."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

import bpy


BoxFn = Callable[
    [str, tuple[float, float, float], tuple[float, float, float], bpy.types.Material, float, int],
    bpy.types.Object,
]


@dataclass(frozen=True)
class ShowcaseModuleSpec:
    slot_id: str
    x: float
    y: float
    width: float
    depth: float
    plinth_height: float
    glass_height: float
    yaw: float = 0.0
    kind: str = "side_vitrine"


def _round_vec(values: tuple[float, float, float]) -> list[float]:
    return [round(value, 4) for value in values]


class CosmeticShowcaseModule:
    """Parametric cosmetics-package display case.

    Units are Blender meters. CAD packaging models are expected to arrive in
    millimeters and should be scaled by the manifest calibration.
    """

    def __init__(self, spec: ShowcaseModuleSpec, box: BoxFn, mats: dict[str, bpy.types.Material]) -> None:
        self.spec = spec
        self.box = box
        self.mats = mats
        self.objects: list[bpy.types.Object] = []

    def _world(self, local: tuple[float, float, float]) -> tuple[float, float, float]:
        sin_yaw = math.sin(self.spec.yaw)
        cos_yaw = math.cos(self.spec.yaw)
        lx, ly, lz = local
        return (
            self.spec.x + lx * cos_yaw - ly * sin_yaw,
            self.spec.y + lx * sin_yaw + ly * cos_yaw,
            lz,
        )

    def _box(
        self,
        name: str,
        local: tuple[float, float, float],
        dims: tuple[float, float, float],
        mat_key: str,
        bevel: float = 0.0,
        segments: int = 2,
    ) -> bpy.types.Object:
        obj = self.box(
            f"{self.spec.slot_id}_{name}",
            self._world(local),
            dims,
            self.mats[mat_key],
            bevel,
            segments,
        )
        obj.rotation_euler[2] = self.spec.yaw
        self.objects.append(obj)
        return obj

    def build(self) -> dict:
        w = self.spec.width
        d = self.spec.depth
        h = self.spec.plinth_height
        gh = self.spec.glass_height
        glass_base = h + 0.08
        anchor_z = glass_base + min(gh * 0.28, 0.34)
        usable_height = min(gh * 0.52, 0.42)
        usable_width = min(w * 0.36, 0.34)
        usable_depth = min(d * 0.34, 0.26)

        self._box("floor_shadow", (0, 0, 0.035), (w + 0.36, d + 0.34, 0.07), "floor_shadow", 0.04)
        self._box("floor_shadow_soft_spread", (0, -d * 0.03, 0.018), (w * 1.42, d * 1.28, 0.008), "floor_shadow", 0.065)
        self._box("toe_kick", (0, 0, 0.065), (w * 0.86, d * 0.84, 0.12), "label", 0.025, 3)
        self._box("lower_reveal", (0, -d * 0.48, 0.17), (w * 0.95, 0.035, 0.045), "champagne", 0.004)
        self._box("base_inset", (0, 0, 0.16), (w * 1.02, d * 1.02, 0.18), "white", 0.04, 4)
        self._box("plinth_body", (0, 0, h / 2 + 0.13), (w, d, h), "white", 0.055, 5)
        self._box("left_side_shade", (-w / 2 - 0.012, 0, h * 0.5 + 0.08), (0.018, d * 0.82, h * 0.72), "plinth_shade", 0.008)
        self._box("right_side_shade", (w / 2 + 0.012, 0, h * 0.5 + 0.08), (0.018, d * 0.82, h * 0.72), "plinth_shade", 0.008)
        self._box("top_reveal", (0, -d * 0.49, h + 0.145), (w * 0.94, 0.035, 0.04), "champagne", 0.004)
        self._box("display_deck", (0, 0, h + 0.62), (w * 0.9, d * 0.86, 0.07), "white", 0.035, 4)
        self._box("deck_shadow", (0, 0, h + 0.565), (w * 0.88, d * 0.84, 0.012), "soft_ao", 0.018)

        front_y = -d / 2 - 0.034
        self._box("front_recessed_panel", (0, front_y, h * 0.52 + 0.08), (w * 0.74, 0.022, h * 0.42), "plinth_panel", 0.012)
        self._box("front_frosted_inset", (0, front_y - 0.006, h * 0.53 + 0.08), (w * 0.52, 0.012, h * 0.22), "frosted_panel", 0.006)
        self._box("upper_front_bevel", (0, front_y - 0.004, h * 0.77 + 0.08), (w * 0.82, 0.012, 0.018), "plinth_line", 0.002)
        self._box("lower_front_bevel", (0, front_y - 0.004, h * 0.31 + 0.08), (w * 0.82, 0.012, 0.018), "plinth_line", 0.002)
        self._box("left_front_stile", (-w * 0.46, front_y - 0.006, h * 0.53 + 0.08), (0.028, 0.018, h * 0.54), "champagne", 0.003)
        self._box("right_front_stile", (w * 0.46, front_y - 0.006, h * 0.53 + 0.08), (0.028, 0.018, h * 0.54), "champagne", 0.003)
        self._box("slim_brand_label", (0, -d / 2 - 0.052, h * 0.64 + 0.08), (w * 0.23, 0.022, 0.045), "label", 0.006)

        self._box("glass_base_shadow", (0, 0, h + 0.12), (w * 0.82, d * 0.78, 0.012), "soft_ao", 0.03)
        self._build_glass_case(glass_base, w * 0.82, d * 0.78, gh)
        self._box("inner_back_occlusion", (0, d * 0.27, glass_base + gh * 0.46), (w * 0.62, 0.012, gh * 0.5), "soft_ao", 0.012)
        self._box("front_glass_reflection_wash", (0, -d * 0.395, glass_base + gh * 0.58), (w * 0.46, 0.01, gh * 0.62), "light_wash", 0.01)
        anchor = self._build_anchor(anchor_z)
        return self._manifest(anchor, usable_width, usable_depth, usable_height)

    def _build_glass_case(self, base_z: float, width: float, depth: float, height: float) -> None:
        z = base_z + height / 2
        t = 0.025
        self._box("glass_left", (-width / 2, 0, z), (t, depth, height), "glass", 0.01)
        self._box("glass_right", (width / 2, 0, z), (t, depth, height), "glass", 0.01)
        self._box("glass_front", (0, -depth / 2, z), (width, t, height), "glass", 0.01)
        self._box("glass_back", (0, depth / 2, z), (width, t, height), "glass", 0.01)
        self._box("glass_top", (0, 0, base_z + height), (width, depth, t), "glass", 0.01)
        self._box("frosted_back_panel", (0, depth / 2 - 0.045, base_z + height * 0.47), (width * 0.78, 0.018, height * 0.64), "frosted_panel", 0.006)
        for shelf_idx, shelf_z in enumerate((base_z + height * 0.36, base_z + height * 0.62)):
            self._box(f"clear_internal_shelf_{shelf_idx}", (0, 0, shelf_z), (width * 0.78, depth * 0.68, 0.014), "glass", 0.005)
            self._box(f"champagne_shelf_lip_{shelf_idx}", (0, -depth * 0.33, shelf_z + 0.018), (width * 0.72, 0.022, 0.026), "champagne", 0.004)
        self._box("lower_front_metal_rail", (0, -depth / 2 - 0.005, base_z + 0.035), (width + 0.035, 0.035, 0.052), "champagne", 0.006)
        self._box("upper_front_metal_rail", (0, -depth / 2 - 0.005, base_z + height - 0.005), (width + 0.035, 0.035, 0.052), "champagne", 0.006)
        self._box("left_lower_side_rail", (-width / 2 - 0.005, 0, base_z + 0.035), (0.035, depth, 0.045), "champagne", 0.005)
        self._box("right_lower_side_rail", (width / 2 + 0.005, 0, base_z + 0.035), (0.035, depth, 0.045), "champagne", 0.005)
        self._box("front_glass_edge", (0, -depth / 2, base_z + height), (width, 0.035, 0.035), "glass_edge", 0.006)
        self._box("left_front_glass_edge", (-width / 2, -depth / 2, z), (0.035, 0.035, height), "glass_edge", 0.005)
        self._box("right_front_glass_edge", (width / 2, -depth / 2, z), (0.035, 0.035, height), "glass_edge", 0.005)

    def _build_anchor(self, anchor_z: float) -> bpy.types.Object:
        anchor = bpy.data.objects.new(f"CAD_SLOT_{self.spec.slot_id}", None)
        anchor.empty_display_type = "PLAIN_AXES"
        anchor.empty_display_size = 0.12
        anchor.location = self._world((0, -self.spec.depth * 0.12, anchor_z))
        anchor.rotation_euler[2] = self.spec.yaw
        anchor["slot_id"] = self.spec.slot_id
        anchor["cad_units"] = "millimeters"
        anchor["base_scale_m_per_mm"] = 0.001
        bpy.context.collection.objects.link(anchor)
        return anchor

    def _manifest(self, anchor: bpy.types.Object, usable_width: float, usable_depth: float, usable_height: float) -> dict:
        position = (anchor.location.x, anchor.location.y, anchor.location.z)
        real_scale = 0.001
        presentation_boost = 1.35
        max_fit_scale = round(min(usable_height / 0.12, usable_width / 0.03, usable_depth / 0.03), 3)
        return {
            "id": self.spec.slot_id,
            "module": "cosmetic_showcase_v1",
            "kind": self.spec.kind,
            "anchor_name": anchor.name,
            "position": _round_vec(position),
            "rotation": [0, 0, round(self.spec.yaw, 4)],
            "usable_volume_m": {
                "width": round(usable_width, 4),
                "depth": round(usable_depth, 4),
                "height": round(usable_height, 4),
            },
            "cad_fit": {
                "cad_units": "millimeters",
                "meters_per_cad_mm": real_scale,
                "presentation_boost": presentation_boost,
                "max_fit_scale": max_fit_scale,
                "target_height_m": round(min(usable_height * 0.78, 0.32), 4),
                "max_diameter_m": round(min(usable_width, usable_depth) * 0.82, 4),
                "placement_z_offset_m": 0.0,
            },
            "lighting": {
                "key": [0.0, -0.42, 0.72],
                "fill": [0.32, 0.18, 0.45],
                "rim": [-0.28, 0.34, 0.58],
                "recommended_exposure": 0.98,
            },
            "glass": {
                "front_panel_y_m": round(-self.spec.depth * 0.39, 4),
                "opacity": 0.22,
                "roughness": 0.08,
                "ior": 1.45,
                "reflection_hint": "use showroom environment, avoid casting dynamic shadows through glass",
            },
        }


def build_cosmetic_showcase(
    spec: ShowcaseModuleSpec,
    box: BoxFn,
    mats: dict[str, bpy.types.Material],
) -> dict:
    return CosmeticShowcaseModule(spec, box, mats).build()
