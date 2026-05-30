# -*- coding: utf-8 -*-
"""Generate a premium empty gallery shell for the browser showroom.

Run from the project root:
    blender --background --python scripts/create_gallery_shell.py

Outputs:
    web/public/assets/showroom-gallery/gallery_shell.glb
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from showroom_display_modules import ShowcaseModuleSpec, build_cosmetic_showcase


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "web" / "public" / "assets" / "showroom-gallery"
GLB_PATH = OUT_DIR / "gallery_shell.glb"
MANIFEST_PATH = OUT_DIR / "gallery_manifest.json"

WIDTH = 15.2
Y_MIN = -5.4
Y_MAX = 29.0
LENGTH = Y_MAX - Y_MIN
HEIGHT = 5.25

MATS: dict[str, bpy.types.Material] = {}


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def mat_principled(
    name: str,
    color: tuple[float, float, float, float],
    roughness: float = 0.55,
    metallic: float = 0.0,
    alpha: float = 1.0,
    emission: tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Alpha"].default_value = alpha
        if emission and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = emission
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 1.0:
        mat.blend_method = "BLEND"
        mat.use_screen_refraction = True
        mat.show_transparent_back = True
    return mat


def mat_wood_floor_texture() -> bpy.types.Material:
    width = 1024
    height = 2048
    image = bpy.data.images.new("baked warm oak floor texture", width=width, height=height, alpha=True)
    rng = random.Random(15)
    plank_count = 34
    tones = [
        (0.600, 0.480, 0.355),
        (0.615, 0.495, 0.370),
        (0.585, 0.468, 0.345),
        (0.625, 0.505, 0.380),
        (0.605, 0.488, 0.363),
        (0.592, 0.474, 0.350),
        (0.620, 0.500, 0.374),
        (0.598, 0.480, 0.358),
    ]
    offsets = [rng.random() for _ in range(plank_count)]
    tone_indices = [rng.randrange(len(tones)) for _ in range(plank_count)]
    pixels = [0.0] * (width * height * 4)
    for y in range(height):
        v = y / (height - 1)
        for x in range(width):
            u = x / (width - 1)
            plank_f = u * plank_count
            plank = min(plank_count - 1, int(plank_f))
            local = plank_f - plank
            base = tones[tone_indices[plank]]
            seg_f = v * (7.5 + (plank % 5) * 0.22) + offsets[plank] * 1.9
            seg = math.floor(seg_f)
            seg_local = seg_f - seg
            segment_seed = math.sin((plank * 37.0 + seg * 19.0) * 12.9898) * 43758.5453
            segment_noise = segment_seed - math.floor(segment_seed)
            segment_tint = (segment_noise - 0.5) * 0.035
            grain = math.sin(v * 150 + offsets[plank] * 8.0 + math.sin(u * 14) * 0.55)
            fine = math.sin(v * 390 + offsets[plank] * 17 + math.sin(u * 31) * 0.18)
            wash = math.sin((u * 1.4 + v * 2.2) * math.tau + offsets[plank] * 2.0)
            knot_u = 0.25 + ((math.sin((plank * 11.0 + seg * 5.0) * 8.91) * 43758.12) % 1.0) * 0.5
            knot_v = 0.28 + ((math.sin((plank * 17.0 + seg * 13.0) * 5.13) * 33112.78) % 1.0) * 0.44
            knot_gate = ((math.sin((plank * 29.0 + seg * 7.0) * 3.71) * 9931.17) % 1.0) > 0.72
            knot = 0.0
            if knot_gate:
                dx = (local - knot_u) / 0.16
                dy = (seg_local - knot_v) / 0.06
                knot = math.exp(-(dx * dx + dy * dy) * 2.6)
            center_sheen = max(0.0, 1.0 - abs(u - 0.5) * 2.8) * 0.01
            wall_falloff = (abs(u - 0.5) * 2.0) ** 1.7 * 0.012
            delta = grain * 0.008 + fine * 0.002 + wash * 0.004 + segment_tint + center_sheen - wall_falloff - knot * 0.035
            seam = min(local, 1.0 - local) < 0.006
            end_seam = min(seg_local, 1.0 - seg_local) < 0.008
            darken = (0.016 if seam else 0.0) + (0.010 if end_seam else 0.0)
            idx = (y * width + x) * 4
            pixels[idx] = max(0.0, min(1.0, base[0] + delta - darken))
            pixels[idx + 1] = max(0.0, min(1.0, base[1] + delta - darken * 0.82))
            pixels[idx + 2] = max(0.0, min(1.0, base[2] + delta - darken * 0.62))
            pixels[idx + 3] = 1.0
    image.pixels.foreach_set(pixels)
    image.update()
    image.pack()

    mat = bpy.data.materials.new("baked oak gallery floor")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = image
        mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.34
        bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def mat_noise_texture(
    name: str,
    base: tuple[float, float, float],
    variation: float,
    roughness: float = 0.6,
    vertical_wash: bool = False,
) -> bpy.types.Material:
    width = 512
    height = 512
    image = bpy.data.images.new(f"{name} texture", width=width, height=height, alpha=True)
    rng = random.Random(sum((idx + 1) * ord(char) for idx, char in enumerate(name)))
    phase_a = rng.random() * math.tau
    phase_b = rng.random() * math.tau
    pixels = [0.0] * (width * height * 4)
    for y in range(height):
        v = y / (height - 1)
        for x in range(width):
            u = x / (width - 1)
            noise = (rng.random() - 0.5) * variation
            broad = math.sin(u * 8.0 + phase_a) * variation * 0.18 + math.sin(v * 5.5 + phase_b) * variation * 0.18
            wash = (0.07 * (1.0 - v) - 0.035) if vertical_wash else 0.0
            idx = (y * width + x) * 4
            pixels[idx] = max(0.0, min(1.0, base[0] + noise + broad + wash))
            pixels[idx + 1] = max(0.0, min(1.0, base[1] + noise + broad + wash))
            pixels[idx + 2] = max(0.0, min(1.0, base[2] + noise + broad + wash))
            pixels[idx + 3] = 1.0
    image.pixels.foreach_set(pixels)
    image.update()
    image.pack()

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = image
        mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def mat_campaign_poster(
    name: str,
    base: tuple[float, float, float],
    accent: tuple[float, float, float],
    shadow: tuple[float, float, float],
) -> bpy.types.Material:
    width = 512
    height = 512
    image = bpy.data.images.new(f"{name} texture", width=width, height=height, alpha=True)
    pixels = [0.0] * (width * height * 4)
    for y in range(height):
        v = y / (height - 1)
        for x in range(width):
            u = x / (width - 1)
            vignette = ((u - 0.5) ** 2 + (v - 0.54) ** 2) * 0.32
            r = base[0] + (1.0 - v) * 0.08 - vignette
            g = base[1] + (1.0 - v) * 0.07 - vignette
            b = base[2] + (1.0 - v) * 0.06 - vignette
            bottle = abs(u - 0.50) < 0.055 and 0.22 < v < 0.72
            cap = abs(u - 0.50) < 0.045 and 0.70 <= v < 0.86
            halo = (u - 0.5) ** 2 / 0.08 + (v - 0.45) ** 2 / 0.18 < 1.0
            stripe = 0.12 < v < 0.18 or 0.84 < v < 0.89
            if halo:
                r = r * 0.7 + accent[0] * 0.3
                g = g * 0.7 + accent[1] * 0.3
                b = b * 0.7 + accent[2] * 0.3
            if bottle:
                r = accent[0] * 0.78 + 0.18
                g = accent[1] * 0.78 + 0.18
                b = accent[2] * 0.78 + 0.18
            if cap or stripe:
                r = shadow[0]
                g = shadow[1]
                b = shadow[2]
            idx = (y * width + x) * 4
            pixels[idx] = max(0.0, min(1.0, r))
            pixels[idx + 1] = max(0.0, min(1.0, g))
            pixels[idx + 2] = max(0.0, min(1.0, b))
            pixels[idx + 3] = 1.0
    image.pixels.foreach_set(pixels)
    image.update()
    image.pack()

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = image
        mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.72
        bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def mat_soft_shadow_texture(name: str, color: tuple[float, float, float], max_alpha: float) -> bpy.types.Material:
    size = 256
    image = bpy.data.images.new(f"{name} texture", width=size, height=size, alpha=True)
    pixels = [0.0] * (size * size * 4)
    for y in range(size):
        v = y / (size - 1) * 2.0 - 1.0
        for x in range(size):
            u = x / (size - 1) * 2.0 - 1.0
            edge = max(abs(u) ** 1.65, abs(v) ** 1.9)
            falloff = max(0.0, min(1.0, (1.0 - edge) / 0.72))
            alpha = max_alpha * falloff * falloff * (3.0 - 2.0 * falloff)
            idx = (y * size + x) * 4
            pixels[idx] = color[0]
            pixels[idx + 1] = color[1]
            pixels[idx + 2] = color[2]
            pixels[idx + 3] = alpha
    image.pixels.foreach_set(pixels)
    image.update()
    image.pack()

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = "BLEND"
    mat.show_transparent_back = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = image
        mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        mat.node_tree.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
        bsdf.inputs["Roughness"].default_value = 0.96
    return mat


def make_materials() -> None:
    MATS["wall"] = mat_noise_texture("warm white gypsum wall", (0.92, 0.89, 0.84), 0.014, 0.72, True)
    MATS["ceiling"] = mat_noise_texture("matte gallery ceiling", (0.95, 0.93, 0.89), 0.009, 0.74, False)
    MATS["floor_base"] = mat_principled("warm plank underlayer", (0.45, 0.32, 0.17, 1), 0.55)
    MATS["oak_floor"] = mat_wood_floor_texture()
    MATS["black"] = mat_principled("satin black metal", (0.015, 0.016, 0.017, 1), 0.34, 0.55)
    MATS["white"] = mat_noise_texture("warm satin lacquer display finish", (0.90, 0.88, 0.83), 0.010, 0.52, True)
    MATS["plinth_panel"] = mat_principled("subtle recessed plinth panel", (0.83, 0.81, 0.76, 1), 0.5)
    MATS["plinth_line"] = mat_principled("thin plinth bevel shadow", (0.52, 0.50, 0.45, 1), 0.58)
    MATS["plinth_shade"] = mat_principled("soft plinth side shade", (0.055, 0.048, 0.04, 0.13), 0.9, 0.0, 0.13)
    MATS["wall_reveal"] = mat_principled("subtle plaster reveal line", (0.68, 0.64, 0.56, 1), 0.68)
    MATS["champagne"] = mat_principled("brushed champagne metal", (0.72, 0.60, 0.42, 1), 0.31, 0.82)
    MATS["frosted_panel"] = mat_principled("warm frosted acrylic panel", (0.88, 0.86, 0.79, 0.34), 0.35, 0.0, 0.34)
    MATS["light_wash"] = mat_principled(
        "subtle baked gallery light wash",
        (1.0, 0.84, 0.56, 0.055),
        0.82,
        0.0,
        0.055,
        (1.0, 0.78, 0.44, 1),
        0.04,
    )
    MATS["glass"] = mat_principled("soft transparent glass", (0.72, 0.9, 1.0, 0.22), 0.04, 0.0, 0.22)
    MATS["glass_edge"] = mat_principled("glass polished edge", (0.62, 0.86, 0.96, 0.46), 0.08, 0.0, 0.46)
    MATS["ceramic"] = mat_principled("warm ceramic planter", (0.84, 0.82, 0.76, 1), 0.31)
    MATS["soil"] = mat_principled("dark potting soil", (0.08, 0.055, 0.032, 1), 0.86)
    MATS["stem"] = mat_principled("fresh green stems", (0.12, 0.28, 0.09, 1), 0.62)
    MATS["leaf_a"] = mat_principled("deep satin gallery leaves", (0.06, 0.28, 0.12, 1), 0.48)
    MATS["leaf_b"] = mat_principled("soft new green leaves", (0.18, 0.42, 0.16, 1), 0.52)
    MATS["wood_frame"] = mat_principled("walnut frame", (0.42, 0.2, 0.075, 1), 0.42)
    MATS["label"] = mat_principled("dark bronze exhibition label", (0.095, 0.08, 0.06, 1), 0.42)
    MATS["hero_glass_product"] = mat_principled("clear cosmetic package calibration glass", (0.74, 0.92, 1.0, 0.48), 0.02, 0.0, 0.48)
    MATS["hero_liquid_rose"] = mat_principled("rose cosmetic fill calibration liquid", (0.95, 0.38, 0.46, 0.72), 0.18, 0.0, 0.72)
    MATS["hero_liquid_amber"] = mat_principled("amber cosmetic fill calibration liquid", (0.88, 0.58, 0.25, 0.78), 0.2, 0.0, 0.78)
    MATS["hero_black_cap"] = mat_principled("gloss black cosmetic cap", (0.006, 0.006, 0.007, 1), 0.16, 0.12)
    MATS["hero_pearl_cap"] = mat_principled("pearl enamel cosmetic cap", (0.88, 0.82, 0.72, 1), 0.22, 0.18)
    MATS["hero_display_marble"] = mat_noise_texture("warm white veined display stone", (0.88, 0.86, 0.80), 0.024, 0.38, True)
    MATS["hero_soft_glow"] = mat_principled(
        "hidden showcase warm light strip",
        (1.0, 0.78, 0.42, 1),
        0.28,
        0.0,
        1.0,
        (1.0, 0.72, 0.32, 1),
        2.8,
    )
    MATS["skylight"] = mat_principled(
        "bright frosted skylight",
        (0.68, 0.88, 1.0, 0.46),
        0.12,
        0.0,
        0.46,
        (0.78, 0.9, 1.0, 1),
        0.45,
    )
    MATS["warm_light"] = mat_principled(
        "warm spotlight lens",
        (1.0, 0.86, 0.54, 1),
        0.18,
        0.0,
        1.0,
        (1.0, 0.78, 0.38, 1),
        1.8,
    )
    MATS["sun_patch"] = mat_principled(
        "soft baked sunlight",
        (1.0, 0.78, 0.42, 0.045),
        0.82,
        0.0,
        0.045,
        (1.0, 0.74, 0.36, 1),
        0.035,
    )
    MATS["floor_shadow"] = mat_principled("baked contact shadow", (0.05, 0.035, 0.02, 0.08), 0.92, 0.0, 0.08)
    MATS["case_contact_shadow"] = mat_soft_shadow_texture("soft showcase contact shadow", (0.05, 0.035, 0.02), 0.34)
    MATS["floor_shadow_groove"] = mat_principled("subtle floor shadow groove", (0.045, 0.028, 0.012, 0.14), 0.96, 0.0, 0.14)
    MATS["soft_ao"] = mat_principled("soft architectural occlusion", (0.045, 0.035, 0.025, 0.16), 0.94, 0.0, 0.16)
    MATS["rail_shadow"] = mat_principled("soft rail ceiling shadow", (0.03, 0.025, 0.02, 0.16), 0.92, 0.0, 0.16)
    MATS["cove_shadow"] = mat_principled("soft upper wall cove shadow", (0.05, 0.045, 0.04, 0.048), 0.92, 0.0, 0.048)
    MATS["canvas_a"] = mat_campaign_poster("muted cosmetic campaign canvas", (0.70, 0.67, 0.59), (0.55, 0.70, 0.78), (0.22, 0.18, 0.13))
    MATS["canvas_b"] = mat_campaign_poster("warm cosmetic campaign canvas", (0.76, 0.60, 0.44), (0.92, 0.48, 0.52), (0.24, 0.12, 0.08))
    MATS["canvas_c"] = mat_campaign_poster("cool cosmetic campaign canvas", (0.55, 0.64, 0.66), (0.88, 0.74, 0.46), (0.12, 0.15, 0.17))
    for i, rgb in enumerate(
        [
            (0.54, 0.36, 0.19),
            (0.60, 0.42, 0.24),
            (0.50, 0.32, 0.16),
            (0.66, 0.48, 0.28),
            (0.56, 0.38, 0.21),
            (0.63, 0.45, 0.26),
            (0.58, 0.40, 0.22),
            (0.69, 0.51, 0.31),
        ]
    ):
        MATS[f"wood_{i}"] = mat_noise_texture(f"hero oak plank tone {i}", rgb, 0.018, 0.46, False)


def apply_bevel(obj: bpy.types.Object, amount: float, segments: int = 2) -> None:
    if amount <= 0:
        return
    bevel = obj.modifiers.new("soft bevel", "BEVEL")
    bevel.width = amount
    bevel.segments = segments
    bevel.affect = "EDGES"
    normal = obj.modifiers.new("weighted gallery normals", "WEIGHTED_NORMAL")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    bpy.ops.object.modifier_apply(modifier=normal.name)
    obj.select_set(False)


def box(
    name: str,
    loc: tuple[float, float, float],
    dims: tuple[float, float, float],
    mat: bpy.types.Material,
    bevel: float = 0.0,
    segments: int = 2,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    apply_bevel(obj, bevel, segments)
    return obj


def floor_plane(
    name: str,
    loc: tuple[float, float, float],
    dims: tuple[float, float],
    mat: bpy.types.Material,
    rotation_z: float = 0.0,
) -> bpy.types.Object:
    w, d = dims
    verts = [(-w / 2, -d / 2, 0), (w / 2, -d / 2, 0), (w / 2, d / 2, 0), (-w / 2, d / 2, 0)]
    mesh = bpy.data.meshes.new(f"{name} mesh")
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    uv = mesh.uv_layers.new(name="uv")
    for loop, coord in zip(uv.data, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        loop.uv = coord
    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    obj.rotation_euler[2] = rotation_z
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def cylinder(
    name: str,
    loc: tuple[float, float, float],
    radius: float,
    depth: float,
    mat: bpy.types.Material,
    rotation: tuple[float, float, float] = (0, 0, 0),
    vertices: int = 32,
    bevel: float = 0.0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    apply_bevel(obj, bevel, 2)
    return obj


def ellipsoid(
    name: str,
    loc: tuple[float, float, float],
    dims: tuple[float, float, float],
    mat: bpy.types.Material,
    rotation: tuple[float, float, float] = (0, 0, 0),
) -> bpy.types.Object:
    width = dims[0]
    length = dims[2]
    verts = [(0.0, 0.0, 0.0)]
    for i in range(8):
        angle = (i / 8.0) * math.tau
        verts.append((math.cos(angle) * width * 0.5, 0.0, math.sin(angle) * length * 0.5))
    faces = [(0, i, 1 + (i % 8)) for i in range(1, 9)]
    mesh = bpy.data.meshes.new(f"{name} mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    obj.rotation_euler = rotation
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def build_floor() -> None:
    box("floor dark subbase", (0, (Y_MIN + Y_MAX) / 2, -0.035), (WIDTH + 0.25, LENGTH + 0.25, 0.07), MATS["floor_base"])
    verts = [
        (-WIDTH / 2, Y_MIN, 0.004),
        (WIDTH / 2, Y_MIN, 0.004),
        (WIDTH / 2, Y_MAX, 0.004),
        (-WIDTH / 2, Y_MAX, 0.004),
    ]
    mesh = bpy.data.meshes.new("baked oak floor mesh")
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    uv = mesh.uv_layers.new(name="oak floor uv")
    for loop, coord in zip(uv.data, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        loop.uv = coord
    obj = bpy.data.objects.new("baked oak gallery floor", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(MATS["oak_floor"])


def build_shell() -> None:
    center_y = (Y_MIN + Y_MAX) / 2
    skylight_half_width = WIDTH * 0.255
    side_band_width = WIDTH / 2 - skylight_half_width
    side_band_center = (WIDTH / 2 + skylight_half_width) / 2
    box("left warm gallery wall", (-WIDTH / 2 - 0.08, center_y, HEIGHT / 2), (0.18, LENGTH + 0.4, HEIGHT), MATS["wall"], 0.015)
    box("right warm gallery wall", (WIDTH / 2 + 0.08, center_y, HEIGHT / 2), (0.18, LENGTH + 0.4, HEIGHT), MATS["wall"], 0.015)
    box("far gallery wall", (0, Y_MAX + 0.08, HEIGHT / 2), (WIDTH + 0.35, 0.18, HEIGHT), MATS["wall"], 0.015)
    box("left black baseboard", (-WIDTH / 2 + 0.05, center_y, 0.14), (0.14, LENGTH + 0.2, 0.22), MATS["black"], 0.015)
    box("right black baseboard", (WIDTH / 2 - 0.05, center_y, 0.14), (0.14, LENGTH + 0.2, 0.22), MATS["black"], 0.015)
    box("far black baseboard", (0, Y_MAX - 0.05, 0.14), (WIDTH, 0.14, 0.22), MATS["black"], 0.015)
    box("left wall floor ambient occlusion", (-WIDTH / 2 + 0.52, center_y, 0.018), (0.72, LENGTH, 0.006), MATS["soft_ao"], 0.03)
    box("right wall floor ambient occlusion", (WIDTH / 2 - 0.52, center_y, 0.018), (0.72, LENGTH, 0.006), MATS["soft_ao"], 0.03)
    box("far wall floor ambient occlusion", (0, Y_MAX - 0.48, 0.018), (WIDTH - 0.8, 0.72, 0.006), MATS["soft_ao"], 0.03)
    box("left upper wall cove shadow", (-WIDTH / 2 + 0.095, center_y, HEIGHT - 0.55), (0.018, LENGTH - 0.4, 0.28), MATS["cove_shadow"], 0.02)
    box("right upper wall cove shadow", (WIDTH / 2 - 0.095, center_y, HEIGHT - 0.55), (0.018, LENGTH - 0.4, 0.28), MATS["cove_shadow"], 0.02)
    box("left gallery wall soft wash", (-WIDTH / 2 + 0.086, center_y - 1.2, 2.55), (0.014, LENGTH - 4.0, 2.05), MATS["light_wash"], 0.025)
    box("right gallery wall soft wash", (WIDTH / 2 - 0.086, center_y + 1.1, 2.55), (0.014, LENGTH - 4.0, 2.05), MATS["light_wash"], 0.025)

    box("left ceiling band", (-side_band_center, center_y, HEIGHT), (side_band_width, LENGTH + 0.2, 0.18), MATS["ceiling"], 0.02)
    box("right ceiling band", (side_band_center, center_y, HEIGHT), (side_band_width, LENGTH + 0.2, 0.18), MATS["ceiling"], 0.02)
    box("left soffit face", (-skylight_half_width, center_y, HEIGHT - 0.32), (0.16, LENGTH + 0.2, 0.68), MATS["ceiling"], 0.018)
    box("right soffit face", (skylight_half_width, center_y, HEIGHT - 0.32), (0.16, LENGTH + 0.2, 0.68), MATS["ceiling"], 0.018)
    box("left soffit underside shadow", (-skylight_half_width - 0.08, center_y, HEIGHT - 0.69), (0.08, LENGTH, 0.035), MATS["rail_shadow"], 0.01)
    box("right soffit underside shadow", (skylight_half_width + 0.08, center_y, HEIGHT - 0.69), (0.08, LENGTH, 0.035), MATS["rail_shadow"], 0.01)

    skylights = [(-0.2, 7.1), (12.2, 19.5), (24.0, 28.6)]
    intervals = [(Y_MIN, -0.2), (7.1, 12.2), (19.5, 24.0), (28.6, Y_MAX)]
    for start, end in intervals:
        if end - start > 0.25:
            box(f"center ceiling panel {start:.1f}", (0, (start + end) / 2, HEIGHT), (skylight_half_width * 2 - 0.25, end - start, 0.18), MATS["ceiling"], 0.018)

    for idx, (start, end) in enumerate(skylights):
        mid = (start + end) / 2
        length = end - start
        glass_width = skylight_half_width * 2 - 0.7
        curb_x = glass_width / 2 + 0.18
        box(f"skylight glass {idx}", (0, mid, HEIGHT + 0.22), (glass_width, length - 0.28, 0.035), MATS["skylight"], 0.025)
        box(f"skylight left curb {idx}", (-curb_x, mid, HEIGHT + 0.02), (0.16, length, 0.42), MATS["ceiling"], 0.018)
        box(f"skylight right curb {idx}", (curb_x, mid, HEIGHT + 0.02), (0.16, length, 0.42), MATS["ceiling"], 0.018)
        box(f"skylight near curb {idx}", (0, start, HEIGHT + 0.02), (glass_width + 0.38, 0.16, 0.42), MATS["ceiling"], 0.018)
        box(f"skylight far curb {idx}", (0, end, HEIGHT + 0.02), (glass_width + 0.38, 0.16, 0.42), MATS["ceiling"], 0.018)
        box(f"skylight center mullion {idx}", (0, mid, HEIGHT + 0.27), (0.075, length - 0.35, 0.08), MATS["black"], 0.006)
        box(f"skylight cross mullion {idx}", (0, mid, HEIGHT + 0.28), (glass_width - 0.28, 0.075, 0.08), MATS["black"], 0.006)


def build_tracks_and_lights() -> None:
    center_y = (Y_MIN + Y_MAX) / 2
    rail_positions = (-WIDTH / 2 + 1.0, -WIDTH * 0.24, WIDTH * 0.24, WIDTH / 2 - 1.0)
    for x in rail_positions:
        box(f"black lighting rail {x}", (x, center_y, HEIGHT - 0.28), (0.065, LENGTH - 1.35, 0.055), MATS["black"], 0.008)
        box(f"soft shadow under rail {x}", (x, center_y, HEIGHT - 0.34), (0.12, LENGTH - 1.35, 0.018), MATS["rail_shadow"], 0.004)

    y_positions = [Y_MIN + 2.0 + i * 2.8 for i in range(12)]
    for x in (rail_positions[0], rail_positions[-1]):
        inward = 1 if x < 0 else -1
        for i, y in enumerate(y_positions):
            angle = math.radians(18 * inward)
            cylinder(
                f"angled spotlight body {x} {i}",
                (x + inward * 0.1, y, HEIGHT - 0.55),
                0.058,
                0.34,
                MATS["black"],
                rotation=(0, angle, 0),
                vertices=18,
                bevel=0.004,
            )
            cylinder(
                f"spotlight warm lens {x} {i}",
                (x + inward * 0.17, y, HEIGHT - 0.72),
                0.04,
                0.018,
                MATS["warm_light"],
                rotation=(0, angle, 0),
                vertices=18,
            )
    for x in (rail_positions[1], rail_positions[2]):
        for i, y in enumerate(y_positions[1::3]):
            cylinder(
                f"center spotlight body {x} {i}",
                (x, y, HEIGHT - 0.58),
                0.052,
                0.3,
                MATS["black"],
                rotation=(math.radians(4), 0, 0),
                vertices=18,
                bevel=0.004,
            )
            cylinder(
                f"center warm lens {x} {i}",
                (x, y, HEIGHT - 0.75),
                0.038,
                0.018,
                MATS["warm_light"],
                vertices=18,
            )


def build_architectural_reveals() -> None:
    center_y = (Y_MIN + Y_MAX) / 2
    wall_y_len = LENGTH - 1.0
    for side, label in ((-1, "left"), (1, "right")):
        wall_x = side * (WIDTH / 2 - 0.075)
        box(f"{label} waist plaster reveal", (wall_x, center_y, 1.18), (0.018, wall_y_len, 0.028), MATS["wall_reveal"], 0.002)
        box(f"{label} upper plaster reveal", (wall_x, center_y, 3.68), (0.016, wall_y_len - 1.2, 0.024), MATS["wall_reveal"], 0.002)
        box(f"{label} ceiling cove dark hairline", (wall_x, center_y, HEIGHT - 0.86), (0.016, wall_y_len - 0.5, 0.02), MATS["plinth_line"], 0.001)
        for idx, y in enumerate((0.2, 4.8, 9.3, 13.9, 18.4, 23.0, 27.2)):
            height = 1.85 if idx % 2 else 2.2
            z = 2.32 + (height - 1.85) * 0.12
            box(
                f"{label} vertical plaster reveal {idx}",
                (wall_x, y, z),
                (0.014, 0.026, height),
                MATS["wall_reveal"],
                0.001,
            )
    box("far wall lower reveal", (0, Y_MAX - 0.075, 1.18), (WIDTH - 1.0, 0.018, 0.028), MATS["wall_reveal"], 0.002)
    box("far wall upper reveal", (0, Y_MAX - 0.075, 3.68), (WIDTH - 1.3, 0.016, 0.024), MATS["wall_reveal"], 0.002)


def build_frame(name: str, x: float, y: float, z: float, width_y: float, height_z: float, canvas_mat: bpy.types.Material) -> None:
    side_sign = 1 if x > 0 else -1
    x_panel = x - side_sign * 0.035
    box(f"{name} canvas panel", (x_panel, y, z), (0.035, width_y, height_z), canvas_mat, 0.006)
    box(f"{name} top frame", (x, y, z + height_z / 2 + 0.045), (0.07, width_y + 0.15, 0.09), MATS["wood_frame"], 0.008)
    box(f"{name} bottom frame", (x, y, z - height_z / 2 - 0.045), (0.07, width_y + 0.15, 0.09), MATS["wood_frame"], 0.008)
    box(f"{name} left frame", (x, y - width_y / 2 - 0.045, z), (0.07, 0.09, height_z + 0.18), MATS["wood_frame"], 0.008)
    box(f"{name} right frame", (x, y + width_y / 2 + 0.045, z), (0.07, 0.09, height_z + 0.18), MATS["wood_frame"], 0.008)


def build_wall_frames() -> None:
    positions = [(-1.8, 1.52), (3.2, 1.08), (7.1, 0.82), (11.5, 1.22), (16.3, 0.92), (21.4, 1.38), (26.0, 1.02)]
    mats = [MATS["canvas_a"], MATS["canvas_b"], MATS["canvas_c"]]
    for idx, (y, width) in enumerate(positions):
        height = 0.68 + (idx % 3) * 0.12
        build_frame(f"left wall frame {idx}", -WIDTH / 2 + 0.08, y, 2.38 + (idx % 2) * 0.04, width, height, mats[idx % len(mats)])
    for idx, (y, width) in enumerate(positions[1:]):
        height = 0.68 + ((idx + 1) % 3) * 0.12
        build_frame(f"right wall frame {idx}", WIDTH / 2 - 0.08, y + 0.75, 2.34 + (idx % 2) * 0.04, width, height, mats[(idx + 1) % len(mats)])


def glass_case(name: str, x: float, y: float, base_z: float, width: float, depth: float, height: float) -> None:
    z = base_z + height / 2
    t = 0.025
    box(f"{name} glass left", (x - width / 2, y, z), (t, depth, height), MATS["glass"], 0.01)
    box(f"{name} glass right", (x + width / 2, y, z), (t, depth, height), MATS["glass"], 0.01)
    box(f"{name} glass front", (x, y - depth / 2, z), (width, t, height), MATS["glass"], 0.01)
    box(f"{name} glass back", (x, y + depth / 2, z), (width, t, height), MATS["glass"], 0.01)
    box(f"{name} glass top", (x, y, base_z + height), (width, depth, t), MATS["glass"], 0.01)
    box(f"{name} frosted back panel", (x, y + depth / 2 - 0.045, base_z + height * 0.47), (width * 0.78, 0.018, height * 0.64), MATS["frosted_panel"], 0.006)
    for shelf_idx, shelf_z in enumerate((base_z + height * 0.36, base_z + height * 0.62)):
        box(f"{name} clear internal shelf {shelf_idx}", (x, y, shelf_z), (width * 0.78, depth * 0.68, 0.014), MATS["glass"], 0.005)
        box(f"{name} champagne shelf lip {shelf_idx}", (x, y - depth * 0.33, shelf_z + 0.018), (width * 0.72, 0.022, 0.026), MATS["champagne"], 0.004)
    box(f"{name} lower front metal rail", (x, y - depth / 2 - 0.005, base_z + 0.035), (width + 0.035, 0.035, 0.052), MATS["champagne"], 0.006)
    box(f"{name} upper front metal rail", (x, y - depth / 2 - 0.005, base_z + height - 0.005), (width + 0.035, 0.035, 0.052), MATS["champagne"], 0.006)
    box(f"{name} left lower side rail", (x - width / 2 - 0.005, y, base_z + 0.035), (0.035, depth, 0.045), MATS["champagne"], 0.005)
    box(f"{name} right lower side rail", (x + width / 2 + 0.005, y, base_z + 0.035), (0.035, depth, 0.045), MATS["champagne"], 0.005)
    box(f"{name} front edge", (x, y - depth / 2, base_z + height), (width, 0.035, 0.035), MATS["glass_edge"], 0.006)
    box(f"{name} left front vertical edge", (x - width / 2, y - depth / 2, z), (0.035, 0.035, height), MATS["glass_edge"], 0.005)
    box(f"{name} right front vertical edge", (x + width / 2, y - depth / 2, z), (0.035, 0.035, height), MATS["glass_edge"], 0.005)


def build_pedestal(name: str, x: float, y: float, width: float = 1.35, depth: float = 1.2, height: float = 0.95) -> None:
    box(f"{name} recessed toe shadow", (x, y, 0.035), (width + 0.28, depth + 0.26, 0.07), MATS["floor_shadow"], 0.035)
    box(f"{name} black recessed toe kick", (x, y, 0.065), (width * 0.86, depth * 0.84, 0.12), MATS["label"], 0.025, 3)
    box(f"{name} champagne lower reveal", (x, y - depth * 0.48, 0.17), (width * 0.95, 0.035, 0.045), MATS["champagne"], 0.004)
    box(f"{name} plinth base inset", (x, y, 0.16), (width * 1.02, depth * 1.02, 0.18), MATS["white"], 0.04, 4)
    box(f"{name} white plinth body", (x, y, height / 2 + 0.13), (width, depth, height), MATS["white"], 0.055, 5)
    box(f"{name} left side soft shade", (x - width / 2 - 0.012, y, height * 0.5 + 0.08), (0.018, depth * 0.82, height * 0.72), MATS["plinth_shade"], 0.008)
    box(f"{name} right side soft shade", (x + width / 2 + 0.012, y, height * 0.5 + 0.08), (0.018, depth * 0.82, height * 0.72), MATS["plinth_shade"], 0.008)
    box(f"{name} champagne top reveal", (x, y - depth * 0.49, height + 0.145), (width * 0.94, 0.035, 0.04), MATS["champagne"], 0.004)
    box(f"{name} thin display deck", (x, y, height + 0.62), (width * 0.9, depth * 0.86, 0.07), MATS["white"], 0.035, 4)
    box(f"{name} underside deck shadow", (x, y, height + 0.565), (width * 0.88, depth * 0.84, 0.012), MATS["soft_ao"], 0.018)
    front_y = y - depth / 2 - 0.034
    box(f"{name} front recessed panel", (x, front_y, height * 0.52 + 0.08), (width * 0.74, 0.022, height * 0.42), MATS["plinth_panel"], 0.012)
    box(f"{name} front frosted inset", (x, front_y - 0.006, height * 0.53 + 0.08), (width * 0.52, 0.012, height * 0.22), MATS["frosted_panel"], 0.006)
    box(f"{name} upper front bevel line", (x, front_y - 0.004, height * 0.77 + 0.08), (width * 0.82, 0.012, 0.018), MATS["plinth_line"], 0.002)
    box(f"{name} lower front bevel line", (x, front_y - 0.004, height * 0.31 + 0.08), (width * 0.82, 0.012, 0.018), MATS["plinth_line"], 0.002)
    box(f"{name} left champagne front stile", (x - width * 0.46, front_y - 0.006, height * 0.53 + 0.08), (0.028, 0.018, height * 0.54), MATS["champagne"], 0.003)
    box(f"{name} right champagne front stile", (x + width * 0.46, front_y - 0.006, height * 0.53 + 0.08), (0.028, 0.018, height * 0.54), MATS["champagne"], 0.003)
    box(f"{name} slim brand label", (x, y - depth / 2 - 0.052, height * 0.64 + 0.08), (width * 0.23, 0.022, 0.045), MATS["label"], 0.006)
    box(f"{name} glass base contact shadow", (x, y, height + 0.12), (width * 0.82, depth * 0.78, 0.012), MATS["soft_ao"], 0.03)
    glass_case(f"{name} empty vitrine", x, y, height + 0.08, width * 0.82, depth * 0.78, 0.92)


def build_pedestals() -> list[dict]:
    slots: list[dict] = []
    side_x = WIDTH / 2 - 2.15
    for i, y in enumerate((1.4, 8.2, 15.4, 23.0)):
        slots.append(
            build_cosmetic_showcase(
                ShowcaseModuleSpec(f"L{i + 1:02d}", -side_x, y, 1.28, 1.12, 0.88, 0.92, kind="left_wall_vitrine"),
                box,
                MATS,
            )
        )
    for i, y in enumerate((4.8, 12.0, 19.2, 26.2)):
        slots.append(
            build_cosmetic_showcase(
                ShowcaseModuleSpec(f"R{i + 1:02d}", side_x, y, 1.28, 1.12, 0.88, 0.92, kind="right_wall_vitrine"),
                box,
                MATS,
            )
        )
    for i, y in enumerate((8.8, 17.4, 25.2)):
        slots.append(
            build_cosmetic_showcase(
                ShowcaseModuleSpec(f"C{i + 1:02d}", 0.0, y, 1.72, 1.42, 1.0, 0.92, kind="central_island_vitrine"),
                box,
                MATS,
            )
        )
    return slots


def potted_plant(name: str, x: float, y: float, scale: float = 1.0, side: int = 1) -> None:
    pot_h = 0.46 * scale
    pot_r = 0.26 * scale
    cylinder(f"{name} ceramic planter", (x, y, pot_h / 2), pot_r, pot_h, MATS["ceramic"], vertices=36, bevel=0.012)
    cylinder(f"{name} dark soil", (x, y, pot_h + 0.018), pot_r * 0.88, 0.036 * scale, MATS["soil"], vertices=36)
    box(f"{name} soft planter shadow", (x, y, 0.012), (pot_r * 2.35, pot_r * 2.1, 0.006), MATS["floor_shadow"], 0.04)

    rng = random.Random(sum((idx + 1) * ord(char) for idx, char in enumerate(name)))
    leaf_count = 5
    for i in range(leaf_count):
        angle = (i / leaf_count) * math.tau + rng.uniform(-0.14, 0.14)
        reach = (0.18 + rng.random() * 0.32) * scale
        height = (0.34 + rng.random() * 0.72) * scale
        lx = x + math.cos(angle) * reach * 0.46
        ly = y + math.sin(angle) * reach
        lz = pot_h + height
        stem_h = max(0.24 * scale, height * 0.72)
        cylinder(
            f"{name} stem {i}",
            ((x + lx) / 2, (y + ly) / 2, pot_h + stem_h / 2),
            0.008 * scale,
            stem_h,
            MATS["stem"],
            rotation=(math.radians(10) * math.sin(angle), math.radians(8) * math.cos(angle), 0),
            vertices=10,
        )
        leaf_mat = MATS["leaf_a"] if i % 3 else MATS["leaf_b"]
        ellipsoid(
            f"{name} broad leaf {i}",
            (lx + side * 0.03 * rng.random(), ly, lz),
            ((0.18 + rng.random() * 0.12) * scale, (0.055 + rng.random() * 0.028) * scale, (0.28 + rng.random() * 0.16) * scale),
            leaf_mat,
            rotation=(math.radians(18 + rng.random() * 18), math.radians(42 * side), angle),
        )


def wall_vine(name: str, x: float, y: float, z: float, side: int) -> None:
    cylinder(f"{name} hanging stem", (x, y, z - 0.45), 0.01, 0.95, MATS["stem"], vertices=8)
    for i in range(9):
        offset = i * 0.1
        ellipsoid(
            f"{name} vine leaf {i}",
            (x + side * 0.025, y + (i % 3 - 1) * 0.055, z - offset),
            (0.09, 0.035, 0.17),
            MATS["leaf_a"] if i % 2 else MATS["leaf_b"],
            rotation=(math.radians(24), math.radians(72 * side), math.radians(i * 27)),
        )


def build_greenery() -> None:
    for i, (x, y, scale, side) in enumerate(
        [
            (-5.14, 5.2, 1.0, 1),
            (5.14, 18.2, 0.9, -1),
        ]
    ):
        potted_plant(f"gallery potted plant {i}", x, y, scale, side)


def build_baked_light() -> None:
    patches = [(-4.7, 2.0, 3.3, 4.8), (-2.6, 14.0, 2.6, 5.6), (3.4, 24.6, 2.8, 4.2)]
    for i, (x, y, w, d) in enumerate(patches):
        box(f"warm skylight floor patch {i}", (x, y, 0.012), (w, d, 0.006), MATS["sun_patch"], 0.04)
    for i, y in enumerate((2.0, 14.8, 25.0)):
        box(f"left wall sun wash {i}", (-WIDTH / 2 + 0.09, y, 1.9), (0.018, 4.6, 1.65), MATS["sun_patch"], 0.03)


def add_lights() -> None:
    bpy.ops.object.light_add(type="AREA", location=(-3.5, -2.0, 5.8))
    key = bpy.context.object
    key.name = "soft skylight key"
    key.data.energy = 480
    key.data.size = 7.0
    bpy.ops.object.light_add(type="AREA", location=(2.5, 18.0, 5.4))
    fill = bpy.context.object
    fill.name = "long gallery fill"
    fill.data.energy = 260
    fill.data.size = 10.0


def merge_meshes_by_material() -> None:
    groups: dict[str, list[bpy.types.Object]] = {}
    for obj in list(bpy.context.scene.objects):
        if obj.type != "MESH":
            continue
        if len(obj.data.materials) != 1:
            continue
        mat = obj.data.materials[0]
        if not mat:
            continue
        groups.setdefault(mat.name, []).append(obj)

    for mat_name, objects in groups.items():
        if len(objects) < 2:
            continue
        bpy.ops.object.select_all(action="DESELECT")
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = objects[0]
        bpy.ops.object.join()
        bpy.context.object.name = f"merged {mat_name}"
        bpy.context.object.data.name = f"merged {mat_name} mesh"
        bpy.context.object.select_set(False)


def build_floor() -> None:
    box("hero floor acoustic subbase", (0, (Y_MIN + Y_MAX) / 2, -0.045), (WIDTH + 0.32, LENGTH + 0.32, 0.09), MATS["floor_base"])
    verts = [
        (-WIDTH / 2, Y_MIN, 0.006),
        (WIDTH / 2, Y_MIN, 0.006),
        (WIDTH / 2, Y_MAX, 0.006),
        (-WIDTH / 2, Y_MAX, 0.006),
    ]
    mesh = bpy.data.meshes.new("hero baked oak floor mesh")
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    uv = mesh.uv_layers.new(name="hero oak floor uv")
    for loop, coord in zip(uv.data, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        loop.uv = coord
    obj = bpy.data.objects.new("hero baked oak gallery floor", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(MATS["oak_floor"])

    for idx, x in enumerate([(-WIDTH / 2) + 0.7 + i * 0.78 for i in range(18)]):
        box(
            f"subtle floor board groove {idx}",
            (x, (Y_MIN + Y_MAX) / 2, 0.012),
            (0.014, LENGTH - 0.65, 0.004),
            MATS["floor_shadow_groove"],
            0.001,
            1,
        )
    for idx, y in enumerate([Y_MIN + 1.8 + i * 3.25 for i in range(10)]):
        box(
            f"subtle floor end joint {idx}",
            (0.0, y, 0.013),
            (WIDTH - 1.1, 0.012, 0.004),
            MATS["floor_shadow_groove"],
            0.001,
            1,
        )


def build_wall_frames() -> None:
    positions = [
        (-2.35, 2.15, 1.38, 1.12),
        (2.25, 1.35, 0.92, 1.36),
        (6.8, 1.05, 0.78, 1.05),
        (11.3, 1.48, 1.05, 1.22),
        (16.2, 1.16, 0.88, 1.05),
        (21.0, 1.72, 1.2, 1.26),
        (25.5, 1.22, 0.95, 1.08),
    ]
    mats = [MATS["canvas_a"], MATS["canvas_b"], MATS["canvas_c"]]
    for idx, (y, width, height, lift) in enumerate(positions):
        build_frame(f"left hero campaign frame {idx}", -WIDTH / 2 + 0.08, y, 2.18 + lift * 0.16, width, height, mats[idx % len(mats)])
        box(
            f"left hero poster glass sheen {idx}",
            (-WIDTH / 2 + 0.045, y - width * 0.16, 2.22 + lift * 0.16),
            (0.012, width * 0.5, height * 0.82),
            MATS["light_wash"],
            0.006,
        )
    for idx, (y, width, height, lift) in enumerate(positions[1:]):
        build_frame(f"right hero campaign frame {idx}", WIDTH / 2 - 0.08, y + 0.9, 2.16 + lift * 0.16, width, height, mats[(idx + 1) % len(mats)])
        box(
            f"right hero poster glass sheen {idx}",
            (WIDTH / 2 - 0.045, y + 0.9 - width * 0.16, 2.2 + lift * 0.16),
            (0.012, width * 0.5, height * 0.82),
            MATS["light_wash"],
            0.006,
        )


def build_calibration_product(slot: dict, style: int = 0) -> None:
    x, y, z = slot["position"]
    z += 0.01
    box(f"{slot['id']} warm product riser", (x, y + 0.035, z - 0.01), (0.42, 0.26, 0.035), MATS["hero_display_marble"], 0.012, 2)
    if style % 3 == 0:
        cylinder(f"{slot['id']} rose fill inner bottle", (x, y, z + 0.22), 0.105, 0.44, MATS["hero_liquid_rose"], vertices=64, bevel=0.004)
        cylinder(f"{slot['id']} clear outer bottle", (x, y, z + 0.22), 0.125, 0.50, MATS["hero_glass_product"], vertices=72, bevel=0.006)
        cylinder(f"{slot['id']} glossy black cap", (x, y, z + 0.56), 0.105, 0.22, MATS["hero_black_cap"], vertices=64, bevel=0.008)
        cylinder(f"{slot['id']} champagne collar", (x, y, z + 0.42), 0.114, 0.034, MATS["champagne"], vertices=64, bevel=0.003)
        box(f"{slot['id']} front cosmetic label", (x, y - 0.11, z + 0.24), (0.14, 0.014, 0.15), MATS["frosted_panel"], 0.003)
    elif style % 3 == 1:
        cylinder(f"{slot['id']} amber tall vial fill", (x - 0.12, y, z + 0.25), 0.072, 0.5, MATS["hero_liquid_amber"], vertices=64, bevel=0.004)
        cylinder(f"{slot['id']} amber tall vial glass", (x - 0.12, y, z + 0.25), 0.088, 0.56, MATS["hero_glass_product"], vertices=72, bevel=0.006)
        cylinder(f"{slot['id']} pearl tall cap", (x - 0.12, y, z + 0.62), 0.078, 0.18, MATS["hero_pearl_cap"], vertices=64, bevel=0.008)
        cylinder(f"{slot['id']} small compact base", (x + 0.13, y + 0.015, z + 0.06), 0.12, 0.12, MATS["hero_pearl_cap"], vertices=72, bevel=0.008)
        cylinder(f"{slot['id']} small compact lid", (x + 0.13, y + 0.015, z + 0.145), 0.11, 0.036, MATS["hero_glass_product"], vertices=72, bevel=0.004)
        box(f"{slot['id']} compact bronze accent", (x + 0.13, y - 0.08, z + 0.16), (0.11, 0.012, 0.028), MATS["champagne"], 0.002)
    else:
        cylinder(f"{slot['id']} frosted tube body", (x + 0.03, y, z + 0.25), 0.09, 0.5, MATS["hero_glass_product"], vertices=72, bevel=0.006)
        cylinder(f"{slot['id']} black tube shoulder", (x + 0.03, y, z + 0.56), 0.08, 0.13, MATS["hero_black_cap"], vertices=64, bevel=0.008)
        cylinder(f"{slot['id']} champagne tube cap", (x + 0.03, y, z + 0.73), 0.078, 0.18, MATS["champagne"], vertices=64, bevel=0.006)
        box(f"{slot['id']} slim name card", (x, y - 0.19, z + 0.07), (0.34, 0.018, 0.12), MATS["label"], 0.003)


def build_pedestals() -> list[dict]:
    slots: list[dict] = []
    side_x = WIDTH / 2 - 2.0
    side_specs = [
        ("L01", -side_x, 0.85, 1.62, 1.36, 0.96, 1.16, "left_wall_vitrine"),
        ("L02", -side_x, 7.1, 1.42, 1.22, 0.9, 1.02, "left_wall_vitrine"),
        ("L03", -side_x, 14.6, 1.34, 1.16, 0.88, 0.98, "left_wall_vitrine"),
        ("L04", -side_x, 22.7, 1.3, 1.12, 0.86, 0.96, "left_wall_vitrine"),
        ("R01", side_x, 3.9, 1.62, 1.36, 0.96, 1.16, "right_wall_vitrine"),
        ("R02", side_x, 10.9, 1.42, 1.22, 0.9, 1.02, "right_wall_vitrine"),
        ("R03", side_x, 18.5, 1.34, 1.16, 0.88, 0.98, "right_wall_vitrine"),
        ("R04", side_x, 25.7, 1.3, 1.12, 0.86, 0.96, "right_wall_vitrine"),
    ]
    for idx, (slot_id, x, y, w, d, h, gh, kind) in enumerate(side_specs):
        slot = build_cosmetic_showcase(ShowcaseModuleSpec(slot_id, x, y, w, d, h, gh, kind=kind), box, MATS)
        slots.append(slot)
        build_calibration_product(slot, idx)
        floor_plane(
            f"{slot_id} feathered showcase floor shadow",
            (x, y - d * 0.03, 0.019),
            (w * 1.45, d * 1.32),
            MATS["case_contact_shadow"],
        )
        box(f"{slot_id} showcase internal light bar", (x, y - d * 0.25, h + gh + 0.08), (w * 0.56, 0.028, 0.032), MATS["hero_soft_glow"], 0.006)

    for idx, y in enumerate((7.8, 16.5, 24.4)):
        slot = build_cosmetic_showcase(
            ShowcaseModuleSpec(f"C{idx + 1:02d}", 0.0, y, 2.25, 1.66, 1.06, 1.12, kind="central_island_vitrine"),
            box,
            MATS,
        )
        slots.append(slot)
        build_calibration_product(slot, idx + 2)
        floor_plane(
            f"C{idx + 1:02d} feathered island floor shadow",
            (0.0, y - 0.04, 0.019),
            (2.8, 2.02),
            MATS["case_contact_shadow"],
        )
        box(f"C{idx + 1:02d} island marble display tray", (0.0, y, 1.74), (1.25, 0.72, 0.052), MATS["hero_display_marble"], 0.025, 3)
    return slots


def build_gallery() -> list[dict]:
    clear_scene()
    make_materials()
    build_floor()
    build_shell()
    build_architectural_reveals()
    build_tracks_and_lights()
    build_wall_frames()
    slots = build_pedestals()
    build_greenery()
    build_baked_light()
    add_lights()
    return slots


def export() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(GLB_PATH),
        export_format="GLB",
        export_materials="EXPORT",
        export_apply=True,
        export_yup=True,
        export_lights=True,
    )


def write_manifest(slots: list[dict]) -> None:
    manifest = {
        "id": "aicad_gallery_showroom_v3",
        "asset": "gallery_shell.glb",
        "units": "meters",
        "module_library": {
            "display_case": "cosmetic_showcase_v1",
            "source": "scripts/showroom_display_modules.py",
            "reusable": True,
        },
        "cad_model_calibration": {
            "cad_units": "millimeters",
            "meters_per_cad_mm": 0.001,
            "default_presentation_boost": 1.35,
            "fit_policy": "scale by real-world mm first, then cap by slot usable volume",
            "upright_axis": "Z",
            "front_axis": "-Y",
        },
        "lighting_calibration": {
            "renderer_exposure": 0.98,
            "glass_receives_dynamic_shadow": False,
            "product_key_light": [0.0, -0.42, 0.72],
            "product_fill_light": [0.32, 0.18, 0.45],
            "product_rim_light": [-0.28, 0.34, 0.58],
        },
        "glass_calibration": {
            "opacity": 0.22,
            "roughness": 0.08,
            "ior": 1.45,
            "reflection_mode": "showroom_environment_hint",
        },
        "slots": slots,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    gallery_slots = build_gallery()
    export()
    write_manifest(gallery_slots)
    print(f"Gallery shell exported: {GLB_PATH}")
    print(f"Gallery manifest exported: {MANIFEST_PATH}")
