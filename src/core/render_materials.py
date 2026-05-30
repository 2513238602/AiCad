# -*- coding: utf-8 -*-
"""Reference-image driven render metadata for gallery/viewer workflows.

This module deliberately stays outside the CAD/VLM geometry pipeline.  It
derives viewer-only PBR hints from a reference image and attaches them to the
params object with the `_render_{component}_{field}` namespace expected by the
web viewer.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path
from statistics import median
from typing import Any


IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
COMPONENTS = ("bottle", "cap", "wand", "wiper")
VALID_MATERIALS = {
    "transparent_glass",
    "frosted_glass",
    "glossy_plastic",
    "matte_plastic",
    "metal",
    "pearl",
}


def _clamp(value: Any, lo: float, hi: float, fallback: float = 0.0) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        n = fallback
    if not math.isfinite(n):
        n = fallback
    return max(lo, min(hi, n))


def _rgb(value: Any, fallback: list[int] | None = None) -> list[int]:
    fallback = fallback or [128, 128, 128]
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return [int(round(_clamp(v, 0, 255, fallback[i]))) for i, v in enumerate(value[:3])]
    return list(fallback)


def _mix_rgb(a: list[int], b: list[int], t: float) -> list[int]:
    t = _clamp(t, 0.0, 1.0)
    aa = _rgb(a)
    bb = _rgb(b)
    return [int(round(aa[i] * (1.0 - t) + bb[i] * t)) for i in range(3)]


def _luma(rgb: tuple[int, int, int] | list[int]) -> float:
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    idx = _clamp((len(vals) - 1) * pct, 0, len(vals) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return float(vals[lo])
    frac = idx - lo
    return float(vals[lo] * (1.0 - frac) + vals[hi] * frac)


def _median_rgb(pixels: list[tuple[int, int, int]]) -> list[int]:
    if not pixels:
        return [128, 128, 128]
    return [int(round(median([p[i] for p in pixels]))) for i in range(3)]


def _pixel_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _sample_chroma(rgb: tuple[int, int, int]) -> float:
    return (max(rgb) - min(rgb)) / 255.0


def _is_warm_metal_rgb(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return (
        r > 95
        and r >= g * 0.92
        and g >= r * 0.45
        and g >= b * 0.70
        and (r - b) > 22
        and (max(rgb) - min(rgb)) > 28
    )


def _is_foreground_rgb(rgb: tuple[int, int, int], bg: tuple[int, int, int]) -> bool:
    dist = _pixel_distance(rgb, bg)
    luma = _luma(rgb)
    chroma = _sample_chroma(rgb)
    if dist > 24:
        return True
    if bg[0] > 230 and bg[1] > 230 and bg[2] > 230:
        return luma < 242 and (dist > 10 or chroma > 0.08)
    return dist > 16 or chroma > 0.10


def _foreground_samples(img, y0: float = 0.0, y1: float = 1.0) -> tuple[list[dict[str, Any]], int]:
    w, h = img.size
    yy0 = max(0, min(h - 1, int(round(h * y0))))
    yy1 = max(yy0 + 1, min(h, int(round(h * y1))))
    bg = _background_rgb(img)
    step_x = max(1, w // 180)
    step_y = max(1, (yy1 - yy0) // 140)
    samples: list[dict[str, Any]] = []
    candidates = 0
    for y in range(yy0, yy1, step_y):
        for x in range(0, w, step_x):
            rgb = img.getpixel((x, y))[:3]
            candidates += 1
            if not _is_foreground_rgb(rgb, bg):
                continue
            samples.append({
                "x": x / max(w - 1, 1),
                "y": y / max(h - 1, 1),
                "rgb": rgb,
                "luma": _luma(rgb),
                "chroma": _sample_chroma(rgb),
            })
    return samples, candidates


def _stats_from_samples(samples: list[dict[str, Any]], candidates: int | None = None) -> dict[str, Any]:
    pixels = [s["rgb"] for s in samples]
    if len(pixels) < 5:
        return _default_stats([128, 128, 128])

    lumas = [s["luma"] for s in samples]
    base_rgb = _median_rgb(pixels)
    p10 = _percentile(lumas, 0.10)
    p50 = _percentile(lumas, 0.50)
    p90 = _percentile(lumas, 0.90)
    p97 = _percentile(lumas, 0.97)
    shadow = [p for p, l in zip(pixels, lumas) if l <= p10 + 1e-6] or pixels
    highlight = [p for p, l in zip(pixels, lumas) if l >= p97 - 1e-6] or pixels
    chroma = [s["chroma"] for s in samples]
    warm_pixels = [p for p in pixels if _is_warm_metal_rgb(p)]
    denom = max(candidates if candidates is not None else len(samples), 1)

    return {
        "base_color_rgb": base_rgb,
        "color_rgb": base_rgb,
        "shadow_color_rgb": _median_rgb(shadow),
        "highlight_color_rgb": _median_rgb(highlight),
        "highlight_strength": round(_clamp((p97 - p50) / 120.0, 0, 1), 3),
        "contrast": round(_clamp((p90 - p10) / 160.0, 0, 1), 3),
        "saturation": round(_clamp(float(median(chroma)) if chroma else 0.0, 0, 1), 3),
        "brightness": round(_clamp(p50 / 255.0, 0, 1), 3),
        "coverage": round(_clamp(len(samples) / denom, 0, 1), 3),
        "warm_color_rgb": _median_rgb(warm_pixels) if warm_pixels else None,
        "warm_coverage": round(_clamp(len(warm_pixels) / max(len(samples), 1), 0, 1), 3),
    }


def _metal_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        s for s in samples
        if _is_warm_metal_rgb(s["rgb"])
        or (
            s["chroma"] < 0.18
            and 70 <= s["luma"] <= 235
            and _pixel_distance(s["rgb"], (255, 255, 255)) > 42
        )
    ]


def _glass_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        s for s in samples
        if not _is_warm_metal_rgb(s["rgb"])
        and s["chroma"] < 0.18
        and 120 <= s["luma"] <= 252
    ]


def _dominant_color_samples(samples: list[dict[str, Any]], bucket_size: int = 40) -> list[dict[str, Any]]:
    if not samples:
        return []
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for sample in samples:
        rgb = sample["rgb"]
        key = tuple(min(255, int(v // bucket_size) * bucket_size) for v in rgb)
        buckets.setdefault(key, []).append(sample)
    return max(buckets.values(), key=len)


def _trim_zones_from_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    if not samples:
        return zones

    def _zone(anchor: str, zone_samples: list[dict[str, Any]]) -> None:
        if len(zone_samples) < max(10, len(samples) * 0.08):
            return
        ys = sorted(s["y"] for s in zone_samples)
        y0 = _percentile(ys, 0.08)
        y1 = _percentile(ys, 0.92)
        max_height = 0.14 if anchor == "collar" else 0.08
        fallback_height = 0.10 if anchor == "collar" else 0.06
        zones.append({
            "anchor": anchor,
            "height_ratio": round(_clamp(y1 - y0, 0.035, max_height, fallback_height), 3),
            "source_y0": round(y0, 3),
            "source_y1": round(y1, 3),
        })

    _zone("collar", [s for s in samples if 0.30 <= s["y"] <= 0.64])
    _zone("bottom", [s for s in samples if s["y"] >= 0.70])
    if not zones and len(samples) >= 16:
        ys = sorted(s["y"] for s in samples)
        mid = _percentile(ys, 0.50)
        zones.append({
            "anchor": "body",
            "center_ratio": round(_clamp(1.0 - mid, 0.12, 0.88), 3),
            "height_ratio": 0.08,
            "source_y0": round(_percentile(ys, 0.15), 3),
            "source_y1": round(_percentile(ys, 0.85), 3),
        })
    return zones


def _bottle_trim_metadata(samples: list[dict[str, Any]]) -> dict[str, Any]:
    trim_samples = [s for s in _metal_samples(samples) if s["y"] >= 0.30]
    if len(trim_samples) < 20:
        return {}
    warm_trim_samples = [s for s in trim_samples if _is_warm_metal_rgb(s["rgb"])]
    color_samples = warm_trim_samples if len(warm_trim_samples) >= 20 else trim_samples
    stats = _stats_from_samples(color_samples)
    zones = _trim_zones_from_samples(trim_samples)
    if not zones:
        return {}
    saturation = _clamp(stats.get("saturation"), 0, 1)
    contrast = _clamp(stats.get("contrast"), 0, 1)
    material = "metal" if saturation < 0.38 and contrast > 0.25 else "glossy_plastic"
    return {
        "_render_bottle_trim_material": material,
        "_render_bottle_trim_color_rgb": _rgb(stats.get("base_color_rgb")),
        "_render_bottle_trim_shadow_color_rgb": _rgb(stats.get("shadow_color_rgb")),
        "_render_bottle_trim_highlight_color_rgb": _rgb(stats.get("highlight_color_rgb")),
        "_render_bottle_trim_metalness": 0.42 if material == "metal" else 0.0,
        "_render_bottle_trim_roughness": round(
            _clamp(0.26 - contrast * 0.08, 0.14, 0.32)
            if material == "metal" else _clamp(0.28 - contrast * 0.06, 0.16, 0.42),
            3,
        ),
        "_render_bottle_trim_clearcoat": 0.72 if material == "metal" else 0.50,
        "_render_bottle_trim_clearcoat_roughness": 0.08 if material == "metal" else 0.12,
        "_render_bottle_trim_env_intensity": 1.25 if material == "metal" else 0.85,
        "_render_bottle_trim_zones": zones,
    }


def _background_rgb(img) -> tuple[int, int, int]:
    w, h = img.size
    samples: list[tuple[int, int, int]] = []
    span = max(4, min(w, h) // 16)
    corners = (
        (0, 0, span, span),
        (w - span, 0, w, span),
        (0, h - span, span, h),
        (w - span, h - span, w, h),
    )
    for x0, y0, x1, y1 in corners:
        for y in range(max(0, y0), min(h, y1), 2):
            for x in range(max(0, x0), min(w, x1), 2):
                samples.append(img.getpixel((x, y))[:3])
    return tuple(_median_rgb(samples))  # type: ignore[return-value]


def _open_reference_image(image_path: str | Path | None):
    if not image_path:
        return None
    path = Path(image_path)
    if not path.exists():
        return None
    try:
        from PIL import Image

        img = Image.open(path).convert("RGBA")
        if max(img.size) > 360:
            ratio = 360 / max(img.size)
            size = (max(1, int(img.size[0] * ratio)), max(1, int(img.size[1] * ratio)))
            img = img.resize(size, Image.Resampling.LANCZOS)

        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        return bg.convert("RGB")
    except Exception:
        return None


def _sample_band(img, y0: float, y1: float) -> dict[str, Any]:
    samples, candidates = _foreground_samples(img, y0, y1)
    if len(samples) >= 20:
        return _stats_from_samples(samples, candidates)

    w, h = img.size
    yy0 = max(0, min(h - 1, int(round(h * y0))))
    yy1 = max(yy0 + 1, min(h, int(round(h * y1))))
    step_y = max(1, (yy1 - yy0) // 120)
    fallback_samples = []
    for y in range(yy0, yy1, step_y):
        rgb = img.getpixel((w // 2, y))[:3]
        fallback_samples.append({
            "x": 0.5,
            "y": y / max(h - 1, 1),
            "rgb": rgb,
            "luma": _luma(rgb),
            "chroma": _sample_chroma(rgb),
        })
    return _stats_from_samples(fallback_samples, max(candidates, 1))


def _material_from_hint(component: str, hints: dict[str, Any] | None) -> str | None:
    if not hints:
        return None
    material = hints.get(f"{component}_render_material") or hints.get(f"{component}_material")
    if isinstance(material, str) and material in VALID_MATERIALS:
        return material
    return None


def _infer_material(component: str, stats: dict[str, Any], hints: dict[str, Any] | None = None) -> str:
    hinted = _material_from_hint(component, hints)
    if hinted:
        return hinted

    saturation = _clamp(stats.get("saturation"), 0, 1)
    highlight = _clamp(stats.get("highlight_strength"), 0, 1)
    contrast = _clamp(stats.get("contrast"), 0, 1)
    brightness = _clamp(stats.get("brightness"), 0, 1)

    if component == "bottle":
        if brightness > 0.68 and saturation < 0.18:
            if contrast > 0.08 or highlight > 0.08:
                return "transparent_glass"
            return "frosted_glass"
        if highlight > 0.18 and contrast > 0.14 and saturation < 0.42:
            return "transparent_glass"
        if highlight < 0.10 and contrast < 0.18:
            return "matte_plastic"
        return "glossy_plastic"

    if component == "cap":
        warm_coverage = _clamp(stats.get("warm_coverage"), 0, 1)
        if warm_coverage > 0.12 and contrast > 0.45:
            return "metal"
        if brightness > 0.50 and highlight > 0.24 and contrast > 0.20 and saturation < 0.30:
            return "transparent_glass"
        if highlight < 0.10:
            return "matte_plastic"
        if saturation > 0.22 and brightness > 0.62 and highlight > 0.20:
            return "pearl"
        return "glossy_plastic"

    return "matte_plastic" if component == "wiper" else "glossy_plastic"


def _default_stats(rgb: list[int]) -> dict[str, Any]:
    return {
        "base_color_rgb": rgb,
        "color_rgb": rgb,
        "shadow_color_rgb": _mix_rgb(rgb, [0, 0, 0], 0.35),
        "highlight_color_rgb": _mix_rgb(rgb, [255, 255, 255], 0.55),
        "highlight_strength": 0.28,
        "contrast": 0.32,
        "saturation": (max(rgb) - min(rgb)) / 255.0,
        "brightness": _luma(rgb) / 255.0,
        "coverage": 0.4,
    }


def _render_fields(component: str, material: str, stats: dict[str, Any]) -> dict[str, Any]:
    base_rgb = _rgb(stats.get("base_color_rgb") or stats.get("color_rgb"))
    if material == "metal" and stats.get("warm_color_rgb"):
        base_rgb = _rgb(stats.get("warm_color_rgb"), base_rgb)
    shadow_rgb = _rgb(stats.get("shadow_color_rgb"), _mix_rgb(base_rgb, [0, 0, 0], 0.35))
    highlight_rgb = _rgb(stats.get("highlight_color_rgb"), _mix_rgb(base_rgb, [255, 255, 255], 0.5))
    highlight_strength = _clamp(stats.get("highlight_strength"), 0.0, 1.0, 0.35)
    contrast = _clamp(stats.get("contrast"), 0.0, 1.0, 0.35)
    saturation = _clamp(stats.get("saturation"), 0.0, 1.0, 0.25)
    gloss = _clamp(highlight_strength * 0.7 + contrast * 0.3, 0.0, 1.0)
    roughness_hint = _clamp(0.72 - gloss * 0.52, 0.06, 0.82)
    prefix = f"_render_{component}_"

    fields: dict[str, Any] = {
        f"{prefix}material": material,
        f"{prefix}color_rgb": base_rgb,
        f"{prefix}base_color_rgb": base_rgb,
        f"{prefix}shadow_color_rgb": shadow_rgb,
        f"{prefix}highlight_color_rgb": highlight_rgb,
        f"{prefix}highlight_strength": round(highlight_strength, 3),
        f"{prefix}contrast": round(contrast, 3),
        f"{prefix}saturation": round(saturation, 3),
        f"{prefix}roughness": round(roughness_hint, 3),
        f"{prefix}clearcoat": round(0.25 + gloss * 0.45, 3),
        f"{prefix}clearcoat_roughness": round(_clamp(0.22 - gloss * 0.12, 0.04, 0.28), 3),
        f"{prefix}metalness": 0.0,
        f"{prefix}transmission": 0.0,
        f"{prefix}opacity": 1.0,
        f"{prefix}ior": 1.46,
        f"{prefix}thickness": 1.2,
        f"{prefix}attenuation_color_rgb": base_rgb,
        f"{prefix}attenuation_distance": 24.0,
        f"{prefix}env_intensity": round(0.55 + gloss * 0.35, 3),
        f"{prefix}iridescence": 0.0,
        f"{prefix}sheen": 0.0,
        f"{prefix}sheen_roughness": 0.5,
    }

    if material == "transparent_glass":
        glass_tint_mix = 0.78 if component in ("bottle", "cap") else 0.55
        glass_opacity = 0.34 if component in ("bottle", "cap") else 0.55
        fields.update({
            f"{prefix}base_color_rgb": _mix_rgb(base_rgb, [255, 255, 255], glass_tint_mix),
            f"{prefix}roughness": round(_clamp(0.16 - gloss * 0.09, 0.035, 0.18), 3),
            f"{prefix}clearcoat": 1.0,
            f"{prefix}clearcoat_roughness": 0.045,
            f"{prefix}transmission": round(_clamp(0.72 + gloss * 0.22, 0.68, 0.92), 3),
            f"{prefix}opacity": glass_opacity,
            f"{prefix}thickness": 2.4,
            f"{prefix}attenuation_distance": round(14.0 + (1.0 - saturation) * 16.0, 2),
            f"{prefix}env_intensity": 1.05,
        })
    elif material == "frosted_glass":
        fields.update({
            f"{prefix}base_color_rgb": _mix_rgb(base_rgb, [255, 255, 255], 0.18),
            f"{prefix}roughness": round(_clamp(0.56 + (1.0 - gloss) * 0.16, 0.44, 0.82), 3),
            f"{prefix}clearcoat": 0.38,
            f"{prefix}clearcoat_roughness": 0.24,
            f"{prefix}transmission": 0.36,
            f"{prefix}opacity": 0.78,
            f"{prefix}thickness": 1.8,
            f"{prefix}attenuation_distance": 18.0,
            f"{prefix}env_intensity": 0.82,
        })
    elif material == "matte_plastic":
        fields.update({
            f"{prefix}roughness": round(_clamp(0.62 + (1.0 - gloss) * 0.18, 0.56, 0.88), 3),
            f"{prefix}clearcoat": 0.08,
            f"{prefix}clearcoat_roughness": 0.42,
            f"{prefix}env_intensity": 0.45,
        })
    elif material == "metal":
        fields.update({
            f"{prefix}metalness": 0.42,
            f"{prefix}roughness": round(_clamp(0.26 - gloss * 0.08, 0.16, 0.32), 3),
            f"{prefix}clearcoat": 0.72,
            f"{prefix}clearcoat_roughness": 0.08,
            f"{prefix}env_intensity": 1.35,
        })
    elif material == "pearl":
        fields.update({
            f"{prefix}base_color_rgb": _mix_rgb(base_rgb, [255, 248, 238], 0.14),
            f"{prefix}roughness": round(_clamp(0.34 - gloss * 0.08, 0.22, 0.42), 3),
            f"{prefix}clearcoat": 0.58,
            f"{prefix}clearcoat_roughness": 0.16,
            f"{prefix}iridescence": 0.42,
            f"{prefix}sheen": 0.38,
            f"{prefix}sheen_roughness": 0.35,
            f"{prefix}env_intensity": 0.92,
        })

    if component == "bottle" and material in ("transparent_glass", "frosted_glass"):
        fields.update({
            "_render_bottle_liquid_color_rgb": _mix_rgb(base_rgb, shadow_rgb, 0.18),
            "_render_bottle_liquid_opacity": 0.5 if material == "transparent_glass" else 0.35,
            "_render_bottle_liquid_roughness": 0.28 if material == "transparent_glass" else 0.48,
            "_render_bottle_liquid_level": 0.68,
        })

    return fields


def default_render_metadata(hints: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = {
        "bottle": _default_stats([206, 220, 226]),
        "cap": _default_stats([212, 212, 216]),
        "wand": _default_stats([205, 205, 205]),
        "wiper": _default_stats([220, 220, 220]),
    }
    metadata: dict[str, Any] = {}
    for component, stats in defaults.items():
        material = _infer_material(component, stats, hints)
        metadata.update(_render_fields(component, material, stats))
    return metadata


def extract_reference_render_metadata(
    image_path: str | Path | None,
    hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    img = _open_reference_image(image_path)
    if img is None:
        return default_render_metadata(hints)

    all_samples, _ = _foreground_samples(img)
    cap_samples, cap_candidates = _foreground_samples(img, 0.04, 0.44)
    bottle_samples, bottle_candidates = _foreground_samples(img, 0.34, 0.95)
    cap_warm_samples = [s for s in cap_samples if _is_warm_metal_rgb(s["rgb"])]
    cap_dominant_samples = _dominant_color_samples(cap_samples)
    bottle_body_samples = [
        s for s in bottle_samples
        if not _is_warm_metal_rgb(s["rgb"])
        and not (s["luma"] > 244 and s["chroma"] < 0.05)
    ]
    bottle_dominant_samples = _dominant_color_samples(bottle_body_samples)
    bottle_glass_samples = _glass_samples(bottle_samples)

    cap_stats = (
        _stats_from_samples(cap_warm_samples, cap_candidates)
        if len(cap_warm_samples) >= 20 and len(cap_warm_samples) / max(len(cap_samples), 1) > 0.08
        else _stats_from_samples(cap_dominant_samples, cap_candidates)
        if len(cap_dominant_samples) >= 20
        else _stats_from_samples(cap_samples, cap_candidates)
        if len(cap_samples) >= 20
        else _sample_band(img, 0.05, 0.38)
    )
    bottle_stats = (
        _stats_from_samples(bottle_dominant_samples, bottle_candidates)
        if len(bottle_dominant_samples) >= 20
        else _stats_from_samples(bottle_glass_samples, bottle_candidates)
        if len(bottle_glass_samples) >= 20
        else _stats_from_samples(bottle_body_samples, bottle_candidates)
        if len(bottle_body_samples) >= 20
        else _stats_from_samples(bottle_samples, bottle_candidates)
        if len(bottle_samples) >= 20
        else _sample_band(img, 0.42, 0.92)
    )

    component_stats = {
        "cap": cap_stats,
        "bottle": bottle_stats,
        "wand": _default_stats([205, 205, 205]),
        "wiper": _default_stats([220, 220, 220]),
    }
    metadata: dict[str, Any] = {}
    for component, stats in component_stats.items():
        material = _infer_material(component, stats, hints)
        metadata.update(_render_fields(component, material, stats))
    metadata.update(_bottle_trim_metadata(all_samples))
    return metadata


def find_gallery_reference_image(project_root: str | Path, cat_id: str) -> Path | None:
    picture_dir = Path(project_root) / "tests" / "picture" / cat_id
    if not picture_dir.is_dir():
        return None
    for path in sorted(picture_dir.iterdir(), key=lambda p: p.name.lower()):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            return path
    return None


def build_gallery_render_metadata(
    project_root: str | Path,
    cat_id: str,
    ref_image: str | Path | None = None,
    hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    image_path: Path | None = None
    if ref_image:
        image_path = Path(ref_image)
        if not image_path.is_absolute():
            image_path = root / image_path
    if image_path is None or not image_path.exists():
        image_path = find_gallery_reference_image(root, cat_id)
    metadata = extract_reference_render_metadata(image_path, hints)
    return metadata


def attach_render_metadata(
    params: dict[str, Any] | None,
    component_id: str,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    out = copy.deepcopy(params or {})
    if not metadata:
        return out
    prefix = f"_render_{component_id}_"
    for key, value in metadata.items():
        if key.startswith(prefix):
            out[key] = copy.deepcopy(value)
    return out


def strip_render_metadata(params: dict[str, Any] | None) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in (params or {}).items()
        if not key.startswith("_render_")
    }
