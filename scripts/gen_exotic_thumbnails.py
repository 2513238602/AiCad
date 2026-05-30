# -*- coding: utf-8 -*-
"""
异形瓶盖预设缩略图生成器

扫描 artifacts/exotic_presets/ 下的模型文件，
用软件渲染（PIL 画家算法）生成 thumbnail.png。

零额外依赖 — 仅需 trimesh + PIL + numpy（项目已有）。

用法:
    python scripts/gen_exotic_thumbnails.py               # 全部生成（跳过已有）
    python scripts/gen_exotic_thumbnails.py --force        # 强制重新生成
    python scripts/gen_exotic_thumbnails.py --preset bunny # 只处理指定预设
    python scripts/gen_exotic_thumbnails.py --size 512     # 自定义尺寸
"""
from __future__ import annotations

import io
import sys

# Windows GBK 终端兼容
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import argparse
import json
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRESETS_DIR = PROJECT_ROOT / "artifacts" / "exotic_presets"

# ── 渲染参数 ──────────────────────────────────────────────────────
BASE_COLOR = np.array([176, 196, 222], dtype=np.float64)  # LightSteelBlue
AMBIENT = 0.15           # 环境光最低亮度
KEY_LIGHT_DIR = np.array([0.5, 0.7, 0.5])    # 主光：右上前方
KEY_LIGHT_STR = 0.7
FILL_LIGHT_DIR = np.array([-0.4, -0.3, -0.6])  # 补光：左下后方
FILL_LIGHT_STR = 0.3
ELEV_DEG = 25.0   # 仰角
AZIM_DEG = -35.0   # 方位角
MARGIN = 0.15      # 画面边距比例
TARGET_FACES = 10000  # 简化目标面数（PIL polygon 绑定 C 实现，万面级也很快）


# ── 模型加载 ──────────────────────────────────────────────────────

def _load_mesh(preset_dir: Path):
    """加载预设目录下的模型文件，返回 trimesh.Trimesh"""
    import trimesh

    for ext, fmt in [(".obj", "obj"), (".glb", "glb"), (".gltf", "gltf"),
                     (".ply", "ply"), (".stl", "stl")]:
        p = preset_dir / f"model{ext}"
        if p.exists():
            if fmt in ("glb", "gltf"):
                scene = trimesh.load(str(p), file_type=fmt)
                if isinstance(scene, trimesh.Scene):
                    return scene.dump(concatenate=True)
                return scene
            return trimesh.load(str(p), file_type=fmt, force="mesh")

    # 也尝试修复版本
    for name in ("model_watertight.obj", "model_fixed.obj"):
        p = preset_dir / name
        if p.exists():
            return trimesh.load(str(p), file_type="obj", force="mesh")

    return None


def _read_up_axis(preset_dir: Path) -> str:
    """从 meta.json 读取 up_axis，默认 +Y"""
    meta_path = preset_dir / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text("utf-8"))
            return meta.get("up_axis", "+Y")
        except Exception:
            pass
    return "+Y"


# ── 几何变换 ──────────────────────────────────────────────────────

def _rot_x(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _rot_y(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rot_z(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def _fix_up_axis(verts: np.ndarray, up_axis: str) -> np.ndarray:
    """将模型坐标系转为 Y-up（渲染约定）"""
    up = up_axis.strip().upper()
    if up in ("+Z", "Z"):
        # Z-up → Y-up: 绕 X 轴旋转 -90°
        R = _rot_x(-np.pi / 2)
        return (R @ verts.T).T
    elif up in ("-Y", "-y"):
        # 翻转 Y
        verts = verts.copy()
        verts[:, 1] *= -1
        return verts
    # +Y 或其他：不变
    return verts


# ── 软件渲染 ──────────────────────────────────────────────────────

def render_thumbnail(mesh, size: int = 400, up_axis: str = "+Y") -> Image.Image:
    """
    将 trimesh.Trimesh 渲染为 RGBA PNG 图像。

    画家算法：面按深度排序，PIL polygon 逐面绘制。
    """
    import trimesh as _trimesh

    # 1. 简化（高面数模型加速渲染，但不能太激进）
    if len(mesh.faces) > TARGET_FACES:
        try:
            mesh = mesh.simplify_quadric_decimation(TARGET_FACES)
        except Exception:
            pass  # 简化失败就用原始网格，不做随机采样（会破碎）

    verts = mesh.vertices.copy()

    # 2. 修正坐标轴
    verts = _fix_up_axis(verts, up_axis)

    # 3. 居中 + 归一化到单位包围盒
    centroid = (verts.max(axis=0) + verts.min(axis=0)) / 2
    verts -= centroid
    extent = (verts.max(axis=0) - verts.min(axis=0)).max()
    if extent > 1e-8:
        verts /= extent

    # 4. 等轴测旋转（先方位角绕 Y，再仰角绕 X）
    R_azim = _rot_y(np.radians(AZIM_DEG))
    R_elev = _rot_x(np.radians(-ELEV_DEG))
    R = R_elev @ R_azim

    verts_rot = (R @ verts.T).T

    # 5. 计算面法线（旋转后）并着色
    face_normals = mesh.face_normals.copy()
    face_normals = _fix_up_axis(face_normals, up_axis)
    normals_rot = (R @ face_normals.T).T
    # 归一化
    norms = np.linalg.norm(normals_rot, axis=1, keepdims=True)
    norms[norms < 1e-8] = 1.0
    normals_rot /= norms

    # 主光
    kl = KEY_LIGHT_DIR / np.linalg.norm(KEY_LIGHT_DIR)
    key = np.clip(normals_rot @ kl, 0, 1) * KEY_LIGHT_STR

    # 补光
    fl = FILL_LIGHT_DIR / np.linalg.norm(FILL_LIGHT_DIR)
    fill = np.clip(normals_rot @ fl, 0, 1) * FILL_LIGHT_STR

    brightness = np.clip(AMBIENT + key + fill, 0, 1)

    # 6. 正交投影到像素空间
    x = verts_rot[:, 0]
    y = verts_rot[:, 1]
    z = verts_rot[:, 2]

    xmin, xmax = x.min(), x.max()
    ymin, ymax = y.min(), y.max()
    span = max(xmax - xmin, ymax - ymin)
    if span < 1e-8:
        span = 1.0

    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    scale = (1 - 2 * MARGIN) * size / span

    px = (x - cx) * scale + size / 2
    py = -(y - cy) * scale + size / 2  # Y 翻转（屏幕坐标 Y 向下）

    # 7. 面排序（画家算法：按平均 Z，先画远的）
    faces = mesh.faces
    face_z = z[faces].mean(axis=1)
    order = np.argsort(face_z)  # Z 从小到大（远→近）

    # 8. 绘制
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for i in order:
        f = faces[i]
        polygon = [(px[f[0]], py[f[0]]),
                    (px[f[1]], py[f[1]]),
                    (px[f[2]], py[f[2]])]

        b = brightness[i]
        r = int(np.clip(BASE_COLOR[0] * b, 0, 255))
        g = int(np.clip(BASE_COLOR[1] * b, 0, 255))
        bv = int(np.clip(BASE_COLOR[2] * b, 0, 255))

        draw.polygon(polygon, fill=(r, g, bv, 255))

    return img


# ── 主流程 ────────────────────────────────────────────────────────

def process_preset(preset_dir: Path, size: int, force: bool) -> bool:
    """处理单个预设目录。返回 True 表示成功生成。"""
    thumb_path = preset_dir / "thumbnail.png"
    name = preset_dir.name

    if thumb_path.exists() and not force:
        print(f"  [跳过] {name} — 已有缩略图")
        return True

    mesh = _load_mesh(preset_dir)
    if mesh is None:
        print(f"  [失败] {name} — 未找到模型文件")
        return False

    up_axis = _read_up_axis(preset_dir)
    print(f"  [渲染] {name} — {len(mesh.faces)} 面, up={up_axis} ...", end=" ", flush=True)

    try:
        img = render_thumbnail(mesh, size=size, up_axis=up_axis)
        img.save(str(thumb_path), "PNG")
        fsize = thumb_path.stat().st_size
        print(f"OK ({fsize // 1024}KB)")
        return True
    except Exception as e:
        print(f"失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="为异形瓶盖预设生成缩略图")
    parser.add_argument("--preset", type=str, default=None,
                        help="只处理指定预设（目录名）")
    parser.add_argument("--size", type=int, default=400,
                        help="缩略图尺寸（像素，默认 400）")
    parser.add_argument("--force", action="store_true",
                        help="强制重新生成已有缩略图")
    args = parser.parse_args()

    if not PRESETS_DIR.is_dir():
        print(f"预设目录不存在: {PRESETS_DIR}")
        sys.exit(1)

    dirs = sorted(d for d in PRESETS_DIR.iterdir() if d.is_dir())
    if args.preset:
        dirs = [d for d in dirs if d.name == args.preset]
        if not dirs:
            print(f"未找到预设: {args.preset}")
            sys.exit(1)

    print(f"异形瓶盖缩略图生成器 — 共 {len(dirs)} 个预设, 尺寸 {args.size}×{args.size}")
    print()

    ok, fail = 0, 0
    for d in dirs:
        if process_preset(d, args.size, args.force):
            ok += 1
        else:
            fail += 1

    print()
    print(f"完成: {ok} 成功, {fail} 失败")


if __name__ == "__main__":
    main()
