# -*- coding: utf-8 -*-
"""Generate the reusable empty showroom scene with Blender.

Run from the project root:
    blender --background --python scripts/create_showroom.py

Outputs:
    artifacts/showroom/empty_showroom.glb
    artifacts/showroom/manifest.json
"""
from __future__ import annotations

import json
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "artifacts" / "showroom"
OUT_DIR.mkdir(parents=True, exist_ok=True)
GLB_PATH = OUT_DIR / "empty_showroom.glb"
MANIFEST_PATH = OUT_DIR / "manifest.json"


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def mat_principled(
    name: str,
    color: tuple[float, float, float, float],
    roughness: float = 0.55,
    metallic: float = 0.0,
    alpha: float = 1.0,
    transmission: float = 0.0,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Alpha"].default_value = alpha
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = transmission
    mat.blend_method = "BLEND" if alpha < 1.0 else "OPAQUE"
    mat.use_screen_refraction = alpha < 1.0
    return mat


def mat_emission(
    name: str,
    color: tuple[float, float, float, float],
    strength: float = 2.0,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Emission Color"].default_value = color
        bsdf.inputs["Emission Strength"].default_value = strength
    return mat


MATS = {}


def make_materials() -> None:
    MATS["floor"] = mat_principled("warm polished concrete", (0.34, 0.34, 0.31, 1), 0.38)
    MATS["wall"] = mat_principled("soft gallery wall", (0.58, 0.58, 0.54, 1), 0.72)
    MATS["ceiling"] = mat_principled("quiet ceiling panels", (0.08, 0.09, 0.1, 1), 0.55)
    MATS["metal"] = mat_principled("brushed dark metal", (0.08, 0.085, 0.09, 1), 0.38, 0.65)
    MATS["plinth"] = mat_principled("matte stone plinth", (0.42, 0.42, 0.39, 1), 0.54)
    MATS["glass"] = mat_principled("soft display glass", (0.64, 0.82, 0.95, 0.28), 0.08, 0.0, 0.28, 0.45)
    MATS["light"] = mat_emission("warm linear light", (1.0, 0.82, 0.56, 1), 1.8)
    MATS["label"] = mat_principled("black label plaque", (0.025, 0.025, 0.025, 1), 0.42)


def cube(
    name: str,
    loc: tuple[float, float, float],
    scale: tuple[float, float, float],
    material: bpy.types.Material,
    bevel: float = 0.0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if bevel > 0:
        mod = obj.modifiers.new(name="soft bevel", type="BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.affect = "EDGES"
        obj.modifiers.new(name="weighted normals", type="WEIGHTED_NORMAL")
    return obj


def add_text(
    name: str,
    text: str,
    loc: tuple[float, float, float],
    rot: tuple[float, float, float],
    size: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.object.text_add(location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.data.body = text
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = size
    obj.data.extrude = 0.005
    obj.data.materials.append(material)
    return obj


def add_case(slot_id: str, x: float, y: float, yaw: float = 0.0) -> dict:
    base = cube(
        f"{slot_id}_plinth",
        (x, y, 0.55),
        (2.1, 1.35, 1.1),
        MATS["plinth"],
        bevel=0.06,
    )
    glass = cube(
        f"{slot_id}_glass_case",
        (x, y, 1.55),
        (2.0, 1.25, 1.05),
        MATS["glass"],
        bevel=0.035,
    )
    plaque = cube(
        f"{slot_id}_label_plaque",
        (x, y - 0.72, 1.12),
        (0.82, 0.04, 0.18),
        MATS["label"],
        bevel=0.01,
    )
    for obj in (base, glass, plaque):
        obj.rotation_euler[2] = yaw

    empty = bpy.data.objects.new(f"{slot_id}_anchor", None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = 0.35
    empty.location = (x, y, 1.38)
    empty.rotation_euler[2] = yaw
    bpy.context.collection.objects.link(empty)

    return {
        "id": slot_id,
        "position": [round(x, 3), round(y, 3), 1.38],
        "rotation": [0, 0, round(yaw, 4)],
        "camera_target": [round(x, 3), round(y, 3), 1.35],
        "camera_position": [round(x, 3), round(y - 3.2, 3), 2.25],
        "display_radius": 1.2,
    }


def add_area_light(name: str, loc: tuple[float, float, float], power: float, size: float) -> None:
    # glTF supports point/spot/directional lights, but not Blender area lights.
    # Use softened point lights so the exported GLB remains self-contained.
    data = bpy.data.lights.new(name=name, type="POINT")
    data.energy = power
    data.shadow_soft_size = size
    obj = bpy.data.objects.new(name, data)
    obj.location = loc
    bpy.context.collection.objects.link(obj)


def build_showroom() -> list[dict]:
    # Main room dimensions are in meters.
    width = 24.0
    depth = 16.0
    height = 5.2

    cube("floor_slab", (0, 0, -0.05), (width, depth, 0.1), MATS["floor"])
    cube("back_wall", (0, depth / 2, height / 2), (width, 0.18, height), MATS["wall"])
    cube("front_threshold", (0, -depth / 2, 0.9), (width, 0.16, 1.8), MATS["wall"])
    cube("left_wall", (-width / 2, 0, height / 2), (0.18, depth, height), MATS["wall"])
    cube("right_wall", (width / 2, 0, height / 2), (0.18, depth, height), MATS["wall"])
    cube("ceiling_grid_a", (0, -3.7, height), (width - 1.5, 0.08, 0.14), MATS["ceiling"])
    cube("ceiling_grid_b", (0, 3.7, height), (width - 1.5, 0.08, 0.14), MATS["ceiling"])
    cube("ceiling_grid_c", (-6.0, 0, height), (0.08, depth - 1.5, 0.14), MATS["ceiling"])
    cube("ceiling_grid_d", (6.0, 0, height), (0.08, depth - 1.5, 0.14), MATS["ceiling"])

    # Linear emissive accents.
    cube("back_wall_light_line", (0, depth / 2 - 0.11, 3.15), (width - 2, 0.035, 0.055), MATS["light"])
    cube("left_wall_light_line", (-width / 2 + 0.11, 0, 3.15), (0.035, depth - 2, 0.055), MATS["light"])
    cube("right_wall_light_line", (width / 2 - 0.11, 0, 3.15), (0.035, depth - 2, 0.055), MATS["light"])

    slots: list[dict] = []
    xs = [-8.4, -5.6, -2.8, 0.0, 2.8, 5.6, 8.4]
    for idx, x in enumerate(xs, 1):
        slots.append(add_case(f"A{idx:02d}", x, 4.95, 0.0))
    for idx, x in enumerate(xs, 1):
        slots.append(add_case(f"B{idx:02d}", x, -4.2, 0.0))
    slots.append(add_case("CENTER_01", -2.0, 0.15, 0.0))
    slots.append(add_case("CENTER_02", 2.0, 0.15, 0.0))

    add_text(
        "showroom_wall_title",
        "AiCad Virtual Showroom",
        (0, depth / 2 - 0.13, 3.72),
        (1.5708, 0, 0),
        0.42,
        MATS["label"],
    )

    add_area_light("soft_key_light", (0, -2.8, 4.4), 170, 7.0)
    add_area_light("warm_back_light", (0, 5.2, 4.2), 95, 6.0)
    add_area_light("left_fill_light", (-8.0, 0, 3.3), 50, 5.0)
    add_area_light("right_fill_light", (8.0, 0, 3.3), 50, 5.0)

    bpy.ops.object.camera_add(location=(0, -7.0, 2.15), rotation=(1.36, 0, 0))
    camera = bpy.context.object
    bpy.context.scene.camera = camera
    camera.name = "showroom_default_camera"
    camera.data.lens = 24

    return slots


def set_scene_settings() -> None:
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"
    bpy.context.scene.eevee.taa_render_samples = 64
    bpy.context.scene.eevee.taa_samples = 32
    bpy.context.scene.view_settings.view_transform = "Filmic"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.view_settings.exposure = 0
    bpy.context.scene.view_settings.gamma = 1


def export_glb() -> None:
    bpy.ops.export_scene.gltf(
        filepath=str(GLB_PATH),
        export_format="GLB",
        export_apply=True,
        export_lights=True,
        export_cameras=True,
        export_materials="EXPORT",
    )


def write_manifest(slots: list[dict]) -> None:
    manifest = {
        "id": "empty_showroom_v1",
        "asset": "empty_showroom.glb",
        "units": "meters",
        "default_camera": {
            "position": [0, -7.0, 2.15],
            "target": [0, -0.2, 1.2],
            "fov": 67,
        },
        "navigation": {
            "bounds": {
                "min": [-11.2, -7.2, 0.0],
                "max": [11.2, 7.2, 3.2],
            },
            "walk_speed": 3.0,
            "look_sensitivity": 0.0025,
        },
        "slots": slots,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    clear_scene()
    make_materials()
    slots = build_showroom()
    set_scene_settings()
    export_glb()
    write_manifest(slots)
    print(f"[showroom] wrote {GLB_PATH}")
    print(f"[showroom] wrote {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
