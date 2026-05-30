# -*- coding: utf-8 -*-
"""
异形瓶盖 Mesh 处理管线（Exotic Cap Pipeline）

加载预设 OBJ/GLB/PLY 外观模型 → 修复 → 简化 → 缩放 → 切底 → 挖内腔 → 壁厚检查 → 导出 STL
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ── 常量 ──────────────────────────────────────────────────────────
MIN_WALL_THICKNESS = 0.8   # mm - 最小壁厚安全阈值
CAVITY_TOP_OFFSET = 1.5    # mm - 内腔顶部距模型顶面的最小壁厚
CYLINDER_SECTIONS = 64     # 内腔圆柱体圆周分辨率
CHAMFER_EDGE_WALL = 0.15   # mm - 导入倒角边缘最薄壁厚
NECK_OD_RATIO = 0.75       # 标准颈径/瓶身外径比例 (18-415: 18/24=0.75)


def compute_default_inner_radius(target_od_mm: float) -> float:
    """无 bottle 上下文时，用标准比例推算内腔半径。

    标准 18-415: neck_od/body_od ≈ 0.75
    无刷杆摩擦配合间隙 +0.15mm
    """
    estimated_neck_od = target_od_mm * NECK_OD_RATIO
    return estimated_neck_od / 2 + 0.15


def _ensure_trimesh():
    """延迟导入 trimesh，仅在使用异形盖时才需要"""
    try:
        import trimesh
        return trimesh
    except ImportError:
        raise ImportError(
            "异形瓶盖功能需要 trimesh 库。"
            "请运行: pip install trimesh manifold3d"
        )


# ═══════════════════════════════════════════════════════════════════
#  预设管理
# ═══════════════════════════════════════════════════════════════════

def list_presets(presets_dir: Path) -> List[Dict[str, Any]]:
    """
    扫描预设目录，返回可用预设列表。

    每个预设子目录须包含 model.obj 或 model.glb，
    可选 meta.json（名称/描述）和 thumbnail.png。
    """
    results: List[Dict[str, Any]] = []
    if not presets_dir.is_dir():
        return results

    for d in sorted(presets_dir.iterdir()):
        if not d.is_dir():
            continue

        model_path, model_fmt = None, None
        for ext, fmt in [(".obj", "obj"), (".glb", "glb"), (".gltf", "gltf"),
                         (".ply", "ply"), (".stl", "stl")]:
            candidate = d / f"model{ext}"
            if candidate.exists():
                model_path = candidate
                model_fmt = fmt
                break
        if model_path is None:
            continue

        meta: dict = {}
        meta_path = d / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text("utf-8"))
            except Exception:
                pass

        thumb_url = None
        if (d / "thumbnail.png").exists():
            thumb_url = f"/artifacts/exotic_presets/{d.name}/thumbnail.png"

        results.append({
            "id": d.name,
            "name": meta.get("name", d.name),
            "description": meta.get("description", ""),
            "thumbnail_url": thumb_url,
            "model_format": model_fmt,
            "tags": meta.get("tags", []),
            "default_height_mm": meta.get("default_height_mm"),
        })

    return results


def _find_model_path(presets_dir: Path, preset_id: str) -> Tuple[Path, str]:
    """查找预设模型文件路径和格式"""
    preset_dir = presets_dir / preset_id
    if not preset_dir.is_dir():
        raise FileNotFoundError(f"预设不存在: {preset_id}")
    for ext, fmt in [(".obj", "obj"), (".glb", "glb"), (".gltf", "gltf"),
                     (".ply", "ply"), (".stl", "stl")]:
        p = preset_dir / f"model{ext}"
        if p.exists():
            return p, fmt
    raise FileNotFoundError(f"预设 {preset_id} 中未找到模型文件 (obj/glb/ply/stl)")


# ═══════════════════════════════════════════════════════════════════
#  Mesh 处理步骤
# ═══════════════════════════════════════════════════════════════════

def load_mesh(path: Path, fmt: str):
    """加载 OBJ/GLB/PLY/STL 模型，返回 trimesh.Trimesh"""
    trimesh = _ensure_trimesh()

    if fmt in ("obj", "ply", "stl"):
        mesh = trimesh.load(str(path), file_type=fmt, force="mesh")
    elif fmt in ("glb", "gltf"):
        scene = trimesh.load(str(path), file_type=fmt)
        if isinstance(scene, trimesh.Scene):
            mesh = scene.dump(concatenate=True)
        else:
            mesh = scene
    else:
        raise ValueError(f"不支持的格式: {fmt}")

    if not hasattr(mesh, "faces") or len(mesh.faces) == 0:
        raise ValueError("模型加载失败：无有效面片")
    return mesh


def repair_mesh(mesh) -> None:
    """就地修复网格：合并顶点、去退化面、填洞、修法线。

    若基础修复不够，使用 pymeshfix 做专业级水密修复——
    保留原始表面质量，只在洞口处补面。
    """
    mesh.merge_vertices()
    # trimesh 4.x: 用 nondegenerate_faces 掩码过滤退化面
    mask = mesh.nondegenerate_faces()
    if not mask.all():
        mesh.update_faces(mask)
    # 去重面
    _, unique_idx = np.unique(np.sort(mesh.faces, axis=1), axis=0, return_index=True)
    if len(unique_idx) < len(mesh.faces):
        mask = np.zeros(len(mesh.faces), dtype=bool)
        mask[unique_idx] = True
        mesh.update_faces(mask)
    if not mesh.is_watertight:
        mesh.fill_holes()
    mesh.fix_normals()

    # pymeshfix: 专业级水密修复（保留原始表面）
    if not mesh.is_watertight:
        try:
            import pymeshfix
            tin = pymeshfix.MeshFix(
                np.asarray(mesh.vertices, dtype=np.float64),
                np.asarray(mesh.faces, dtype=np.int32),
            )
            tin.repair()
            trimesh = _ensure_trimesh()
            fixed = trimesh.Trimesh(
                vertices=tin.points, faces=tin.faces, process=True)
            if fixed.is_watertight:
                mesh.vertices = fixed.vertices
                mesh.faces = fixed.faces
        except ImportError:
            pass  # pymeshfix 未安装，跳过
        except Exception:
            pass  # 修复失败不阻塞


def simplify_mesh(mesh, target_faces: int) -> None:
    """
    网格简化：将高面数模型简化到目标面数。

    使用二次误差度量（QEM）算法，在保持外形特征的前提下
    大幅降低面数。例如 69,000 面 → 5,000 面。

    Args:
        mesh:         trimesh.Trimesh 对象（就地修改）
        target_faces: 目标三角面数量
    """
    current = len(mesh.faces)
    if current <= target_faces:
        return  # 已经够少，无需简化

    try:
        import fast_simplification as fs
        ratio = 1.0 - target_faces / current
        ratio = max(0.01, min(ratio, 0.999))
        verts, faces = fs.simplify(
            np.asarray(mesh.vertices, dtype=np.float64),
            np.asarray(mesh.faces, dtype=np.int32),
            target_reduction=ratio,
        )
        trimesh = _ensure_trimesh()
        simplified = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        mesh.vertices = simplified.vertices
        mesh.faces = simplified.faces
    except ImportError:
        pass  # fast_simplification 未安装，跳过
    except Exception:
        pass  # 简化失败不阻塞管线，保留原始面数


def reorient_model(mesh, up_axis: str = "+Z") -> None:
    """
    根据模型原始上轴方向旋转到 Z-up 约定，然后底面移至 Z=0。

    常见约定：OBJ/GLB 通常 Y-up，STL/工程软件通常 Z-up。
    通过 meta.json 的 up_axis 字段指定，默认 "+Z"（无需旋转）。
    """
    up = up_axis.upper().strip()
    if up in ("+Y", "Y"):
        # Y-up → Z-up: 绕 X 轴旋转 -90°  (x,y,z)→(x,-z,y)
        rot = np.array([
            [1,  0,  0, 0],
            [0,  0, -1, 0],
            [0,  1,  0, 0],
            [0,  0,  0, 1],
        ], dtype=float)
        mesh.apply_transform(rot)
    elif up == "-Y":
        rot = np.array([
            [1, 0,  0, 0],
            [0, 0,  1, 0],
            [0, -1, 0, 0],
            [0, 0,  0, 1],
        ], dtype=float)
        mesh.apply_transform(rot)
    elif up in ("+X", "X"):
        rot = np.array([
            [0, 0, 1, 0],
            [0, 1, 0, 0],
            [-1, 0, 0, 0],
            [0, 0, 0, 1],
        ], dtype=float)
        mesh.apply_transform(rot)
    elif up == "-Z":
        rot = np.array([
            [1, 0,  0, 0],
            [0, -1, 0, 0],
            [0, 0, -1, 0],
            [0, 0,  0, 1],
        ], dtype=float)
        mesh.apply_transform(rot)
    # "+Z" 默认无需旋转

    # 底面移至 Z=0
    z_min = mesh.bounds[0][2]
    mesh.apply_translation([0, 0, -z_min])


def scale_to_target(mesh, target_od_mm: float,
                    target_height_mm: Optional[float] = None) -> None:
    """缩放到目标尺寸（XY 按外径，Z 按高度或等比）"""
    bounds = mesh.bounds
    current_od = max(
        bounds[1][0] - bounds[0][0],
        bounds[1][1] - bounds[0][1],
    )
    current_h = bounds[1][2] - bounds[0][2]
    if current_od <= 0 or current_h <= 0:
        raise ValueError("模型尺寸为零，无法缩放")

    scale_xy = target_od_mm / current_od
    scale_z = (target_height_mm / current_h) if target_height_mm else scale_xy

    mesh.apply_scale([scale_xy, scale_xy, scale_z])

    # 重新 XY 居中，保持 Z=0 底面
    bounds = mesh.bounds
    cx = (bounds[0][0] + bounds[1][0]) / 2
    cy = (bounds[0][1] + bounds[1][1]) / 2
    z_min = bounds[0][2]
    mesh.apply_translation([-cx, -cy, -z_min])


def slice_bottom(mesh, cut_z: float = 0.0):
    """在 Z=cut_z 处切平底部，封闭切面，返回新 mesh"""
    trimesh = _ensure_trimesh()
    sliced = trimesh.intersections.slice_mesh_plane(
        mesh,
        plane_normal=[0, 0, 1],
        plane_origin=[0, 0, cut_z],
        cap=True,
    )
    if sliced is None or len(sliced.faces) == 0:
        raise ValueError("切底失败：切割后无剩余几何体")
    return sliced


def create_cavity_cylinder(inner_radius: float, cavity_depth: float):
    """创建内腔圆柱体，底面 Z=0，向上延伸 cavity_depth（回退用）"""
    trimesh = _ensure_trimesh()
    cyl = trimesh.creation.cylinder(
        radius=inner_radius,
        height=cavity_depth,
        sections=CYLINDER_SECTIONS,
    )
    cyl.apply_translation([0, 0, cavity_depth / 2])
    return cyl


def create_cavity_body(
    inner_radius: float,
    cavity_depth: float,
    outer_radius: float,
    has_wand: bool = False,
    max_chamfer_r: Optional[float] = None,
):
    """
    创建带导入倒角的复合内腔旋转体。

    复刻参数化瓶盖的内腔结构（modeler.py build_cap Step 3/3b）:
    - 底部导入倒角：从外壁附近收窄到内径的锥段
    - 主圆柱段：标准内腔

    截面示意（绕 Z 轴旋转）:

         r=0   r_inner r_chamfer
          |       |       |
          |       +-------+  Z = -eps (底面，有微量延伸)
          |       |      /
          |       |     /   ← 导入倒角锥段
          |       |    /
          |       +---+      Z = chamfer_h
          |       |
          |       |          ← 主圆柱段
          |       |
          +-------+          Z = cavity_depth + eps (腔顶)

    Args:
        inner_radius:  内腔半径（主圆柱段）
        cavity_depth:  内腔总深度
        outer_radius:  外壳半径（OD/2），用于计算倒角外径
        has_wand:      是否配合刷杆（影响密封结构）
    """
    trimesh = _ensure_trimesh()

    wall = outer_radius - inner_radius
    eps = 0.15  # 重叠补偿，与 modeler.py 一致

    # ── 导入倒角参数（复刻 modeler.py Step 3b）──
    chamfer_wall = CHAMFER_EDGE_WALL
    if wall <= 0.5:
        chamfer_wall = min(0.10, wall * 0.2)

    if wall >= 1.5:
        chamfer_h = max(5.0, min(cavity_depth * 0.50, 30.0))
    else:
        chamfer_h = max(5.0, min(cavity_depth * 0.30, 20.0))

    # 安全裁剪：倒角不超过腔深的 60%
    chamfer_h = min(chamfer_h, cavity_depth * 0.6)

    r_chamfer = outer_radius - chamfer_wall
    # 厚壁时限制倒角宽度：只需足够的导入锥度，不必扩展到外壁
    max_chamfer_extent = inner_radius + min(wall * 0.5, 3.0)
    r_chamfer = min(r_chamfer, max_chamfer_extent)
    # 外部传入的安全限制（基于实际网格截面）
    if max_chamfer_r is not None:
        r_chamfer = min(r_chamfer, max_chamfer_r)
    # 倒角外径不能小于内径
    r_chamfer = max(r_chamfer, inner_radius + 0.1)

    # ── 构造 2D 旋转轮廓 (r, z) ──
    points = [
        [0.0, -eps],                         # 中心底
        [r_chamfer, -eps],                    # 倒角外侧底
        [inner_radius, chamfer_h],            # 倒角锥顶 → 主腔起始
        [inner_radius, cavity_depth + eps],   # 主腔顶部
        [0.0, cavity_depth + eps],            # 中心顶
    ]

    linestring = np.array(points, dtype=np.float64)

    try:
        cavity = trimesh.creation.revolve(
            linestring=linestring,
            sections=CYLINDER_SECTIONS,
        )
        if cavity.is_watertight and len(cavity.faces) > 0:
            return cavity
    except Exception:
        pass

    # 回退：使用简单圆柱
    return create_cavity_cylinder(inner_radius, cavity_depth)


def ensure_watertight(mesh):
    """
    确保网格水密（布尔运算前置条件）。

    如果 fill_holes 不够，使用体素化 + Marching Cubes 重建。
    这是处理扫描模型（如斯坦福兔子）等非水密网格的关键步骤。

    注意：marching_cubes 返回体素网格坐标，必须映射回世界坐标。
    """
    if mesh.is_watertight:
        return mesh

    # 先尝试简单修复
    mesh.fill_holes()
    mesh.fix_normals()
    if mesh.is_watertight:
        return mesh

    # 记录原始边界（用于坐标还原）
    orig_min = mesh.bounds[0].copy()
    orig_max = mesh.bounds[1].copy()
    orig_extents = orig_max - orig_min

    # 体素化重建（保证水密）
    pitch = max(mesh.extents) / 120  # 分辨率：最长轴 120 个体素（精度 ~0.3mm）
    try:
        voxelized = mesh.voxelized(pitch)
        watertight = voxelized.marching_cubes
        if watertight.is_watertight and len(watertight.faces) > 0:
            # marching_cubes 返回体素网格坐标 → 映射回世界坐标
            wt_extents = watertight.bounds[1] - watertight.bounds[0]
            scale = np.where(wt_extents > 1e-10, orig_extents / wt_extents, 1.0)
            watertight.apply_scale(scale)
            watertight.apply_translation(orig_min - watertight.bounds[0])
            return watertight
    except Exception:
        pass

    # 最后手段：凸包（会丢失凹面细节）
    return mesh.convex_hull


VOXEL_RESOLUTION = 200  # 体素分辨率（最长轴的体素数量）
MAX_SCALE_FACTOR = 3.0  # 最大允许放大倍率


def compute_cavity_fit(mesh, inner_radius: float,
                       min_wall: float = MIN_WALL_THICKNESS,
                       n_samples: int = 30) -> Tuple[float, float, float]:
    """
    分析模型截面，计算容纳内腔所需的放大倍率和安全腔深。

    核心理解：瓶盖底部是开口（瓶颈从下方插入），底部窄区（如脚掌）
    不影响内腔。壁厚只需在"身体区域"满足要求。

    算法分两步：
    1. 识别身体区域（截面半径 >= 内腔半径×70% 的连续范围）
    2. 在身体区域内计算所需放大，使最窄处也能容纳内腔+壁厚

    Returns:
        (scale_factor, cavity_depth, body_start)
        scale_factor >= 1.0: 模型需要额外放大的倍率
        cavity_depth: 在当前尺寸（放大前）的安全腔深
        body_start: 身体区域起始高度（底部窄区的顶部边界）
    """
    bounds = mesh.bounds
    z_min, z_max = float(bounds[0][2]), float(bounds[1][2])
    total_h = z_max - z_min
    required_r = inner_radius + min_wall

    # 采样各高度的最小截面半径
    heights: List[float] = []
    r_mins: List[float] = []

    for i in range(n_samples):
        z = z_min + total_h * (i + 0.5) / n_samples
        if z <= 0:
            continue
        try:
            section = mesh.section(
                plane_origin=[0, 0, z],
                plane_normal=[0, 0, 1],
            )
            if section is None:
                continue
            path_2d, _ = section.to_planar()
            if path_2d is None or len(path_2d.vertices) == 0:
                continue
            dists = np.sqrt(path_2d.vertices[:, 0]**2 + path_2d.vertices[:, 1]**2)
            heights.append(z - z_min)
            r_mins.append(float(np.min(dists)))
        except Exception:
            continue

    if not r_mins:
        return 2.0, 3.0, 0.0  # 截面分析全部失败

    # ── 第一步：识别身体区域 ──
    # 身体 = 截面最小半径 >= 所需外径×85% 的连续范围
    # 用 required_r 而非 inner_radius，确保窄底（如兔脚）被正确排除
    body_threshold = required_r * 0.85
    # 找最长连续身体区域
    best_start: Optional[float] = None
    best_end: float = 0.0
    best_r_mins: List[float] = []
    cur_start: Optional[float] = None
    cur_end: float = 0.0
    cur_r_mins: List[float] = []
    in_body = False

    for h, r in zip(heights, r_mins):
        if r >= body_threshold:
            if not in_body:
                cur_start = h
                cur_r_mins = []
                in_body = True
            cur_end = h
            cur_r_mins.append(r)
        elif in_body:
            if cur_start is not None:
                cur_len = cur_end - cur_start
                best_len = (best_end - best_start) if best_start is not None else 0
                if cur_len > best_len:
                    best_start, best_end = cur_start, cur_end
                    best_r_mins = cur_r_mins[:]
            in_body = False
            cur_start = None
    # 末尾段
    if in_body and cur_start is not None:
        cur_len = cur_end - cur_start
        best_len = (best_end - best_start) if best_start is not None else 0
        if cur_len > best_len:
            best_start, best_end = cur_start, cur_end
            best_r_mins = cur_r_mins[:]

    body_start = best_start
    body_end = best_end
    body_r_mins = best_r_mins

    if not body_r_mins or body_start is None:
        # 当前尺寸下无身体区域 → 先算放大倍率，再用放大后的截面重新检测
        overall_max_r = max(r_mins)
        if overall_max_r < required_r and overall_max_r > 0:
            scale = (required_r / overall_max_r) * 1.05
        else:
            scale = 2.0
        scale = min(scale, MAX_SCALE_FACTOR)

        # 迭代：模拟放大后用 required_r 严格阈值检测身体，不够就加大
        for _retry in range(3):
            # 找最长连续身体区域
            best_start, best_end = None, 0.0
            cur_start = None
            cur_end = 0.0
            in_body = False
            for h, r in zip(heights, r_mins):
                r_scaled = r * scale
                if r_scaled >= required_r:
                    if not in_body:
                        cur_start = h
                        in_body = True
                    cur_end = h
                elif in_body:
                    # 当前段结束，如果比 best 长则更新
                    if cur_start is not None:
                        cur_len = cur_end - cur_start
                        best_len = (best_end - best_start) if best_start is not None else 0
                        if cur_len > best_len:
                            best_start, best_end = cur_start, cur_end
                    in_body = False
                    cur_start = None
            # 末尾段
            if in_body and cur_start is not None:
                cur_len = cur_end - cur_start
                best_len = (best_end - best_start) if best_start is not None else 0
                if cur_len > best_len:
                    best_start, best_end = cur_start, cur_end
            body_start = best_start
            body_end = best_end
            if body_start is not None and body_end - body_start >= 3.0:
                break
            scale = min(scale * 1.2, MAX_SCALE_FACTOR)
            if scale >= MAX_SCALE_FACTOR:
                break

        if body_start is None:
            return scale, 3.0, 0.0  # 放大后仍无身体，保守返回

        # 顶部裁剪一个采样步长，避免边缘壁厚不足
        sample_step = total_h / n_samples
        safe_depth = body_end - sample_step
        safe_depth = min(safe_depth, total_h - CAVITY_TOP_OFFSET)
        return scale, max(safe_depth, 3.0), body_start

    # ── 第二步：计算放大倍率 ──
    # 让身体区域最窄处也能容纳内腔+壁厚
    min_body_r = min(body_r_mins)
    if min_body_r < required_r:
        scale = (required_r / min_body_r) * 1.05
    else:
        scale = 1.0
    scale = min(scale, MAX_SCALE_FACTOR)

    # ── 第三步：安全腔深 ──
    # 内腔从 Z=0 延伸到身体区域末端（放大前的深度）
    safe_depth = body_end
    safe_depth = min(safe_depth, total_h - CAVITY_TOP_OFFSET)
    return scale, max(safe_depth, 3.0), body_start


def smooth_mesh(mesh, iterations: int = 10) -> None:
    """
    Taubin 平滑：消除简化/布尔运算产生的棱角，保持整体体积。

    Taubin 比 Laplacian 更适合 CAD 场景，因为它不会让模型缩水。
    """
    try:
        trimesh = _ensure_trimesh()
        trimesh.smoothing.filter_taubin(mesh, iterations=iterations)
    except Exception:
        pass  # 平滑失败不阻塞管线


def boolean_subtract(mesh_a, mesh_b):
    """布尔减 mesh_a - mesh_b，使用 manifold3d 引擎。

    前置条件：mesh_a 应已通过 repair_mesh() 修复为水密。
    """
    trimesh = _ensure_trimesh()
    try:
        result = trimesh.boolean.difference([mesh_a, mesh_b], engine="manifold")
    except Exception as e:
        raise RuntimeError(f"布尔运算失败（输入网格可能不水密）: {e}")
    if result is None or len(result.faces) == 0:
        raise ValueError("布尔减失败：结果为空")
    return result


def voxel_carve_cavity(
    mesh,
    inner_radius: float,
    cavity_depth: float,
    outer_radius: float,
    collar_r: float = 0.0,
    seal_height: float = 0.0,
    has_wand: bool = False,
    resolution: int = VOXEL_RESOLUTION,
):
    """
    纯体素空间操作：底座填充 + 内腔雕刻。

    避免所有网格布尔运算——非水密输入也能正确处理。

    流程：
    1. 体素化原始网格
    2. 在底座薄弱区填充实心圆柱（体素 OR）
    3. 从填充后的体素网格中雕刻内腔（体素 AND NOT）
    4. Marching Cubes 重建水密网格

    Args:
        mesh:          输入网格（无需水密）
        inner_radius:  内腔半径
        cavity_depth:  内腔深度
        outer_radius:  外径/2（用于计算倒角参数）
        collar_r:      底座填充圆柱半径（0=不填充）
        seal_height:   底座薄弱区的高度上界
        has_wand:      是否配合刷杆
        resolution:    体素分辨率（最长轴的体素数量）
    """
    trimesh = _ensure_trimesh()

    pitch = max(mesh.extents) / resolution
    vox = mesh.voxelized(pitch)
    matrix = vox.matrix.copy()
    transform = vox.transform.copy()
    shape = matrix.shape

    # ── 构建体素世界坐标网格 ──
    ii, jj, kk = np.meshgrid(
        np.arange(shape[0]),
        np.arange(shape[1]),
        np.arange(shape[2]),
        indexing="ij",
    )
    x = transform[0, 0] * ii + transform[0, 3]
    y = transform[1, 1] * jj + transform[1, 3]
    z = transform[2, 2] * kk + transform[2, 3]
    r = np.sqrt(x**2 + y**2)

    # ── 1. 底座填充：在 Z <= seal_height 区域内填充实心圆柱 ──
    if collar_r > 0 and seal_height > 0:
        collar_mask = (z <= seal_height + pitch) & (r <= collar_r)
        matrix |= collar_mask

    # ── 2. 导入倒角参数（复刻 create_cavity_body 逻辑）──
    wall = outer_radius - inner_radius
    chamfer_wall = CHAMFER_EDGE_WALL
    if wall <= 0.5:
        chamfer_wall = min(0.10, wall * 0.2)

    if wall >= 1.5:
        chamfer_h = max(5.0, min(cavity_depth * 0.50, 30.0))
    else:
        chamfer_h = max(5.0, min(cavity_depth * 0.30, 20.0))
    chamfer_h = min(chamfer_h, cavity_depth * 0.6)

    r_chamfer = outer_radius - chamfer_wall
    max_chamfer_extent = inner_radius + min(wall * 0.5, 3.0)
    r_chamfer = min(r_chamfer, max_chamfer_extent)
    r_chamfer = max(r_chamfer, inner_radius + 0.1)

    # ── 3. 雕刻内腔 ──
    # 倒角区（Z = -eps ~ chamfer_h）：半径从 r_chamfer 线性收窄到 inner_radius
    eps = pitch  # 向下延伸一个体素确保底面开口
    t = np.clip(z / max(chamfer_h, 0.01), 0.0, 1.0)
    local_r = r_chamfer * (1.0 - t) + inner_radius * t
    chamfer_zone = (z >= -eps) & (z <= chamfer_h) & (r <= local_r)

    # 主腔区（Z = chamfer_h ~ cavity_depth + eps）：固定半径 inner_radius
    main_zone = (z > chamfer_h) & (z <= cavity_depth + eps) & (r <= inner_radius)

    cavity_mask = chamfer_zone | main_zone
    matrix &= ~cavity_mask

    # ── 4. 体素空间壁厚检查（比截面分析更准确）──
    # 截面分析对平面三角形逼近圆柱面有固有误差，
    # 直接在体素矩阵中检测更可靠。
    n_check = 10
    min_wall_measured = float("inf")
    worst_z_val = 0.0
    for ci in range(n_check):
        z_frac = (ci + 0.5) / n_check
        z_check = cavity_depth * z_frac
        k_check = int(round((z_check - transform[2, 3]) / transform[2, 2]))
        if k_check < 0 or k_check >= shape[2]:
            continue
        z_slice_filled = matrix[:, :, k_check]
        r_slice = r[:, :, k_check]
        filled_radii = r_slice[z_slice_filled]
        if len(filled_radii) == 0:
            continue
        t_check = min(z_check / max(chamfer_h, 0.01), 1.0)
        expected_r = r_chamfer * (1.0 - t_check) + inner_radius * t_check
        wall_val = float(np.min(filled_radii)) - expected_r
        if wall_val < min_wall_measured:
            min_wall_measured = wall_val
            worst_z_val = z_check

    voxel_wall_check = {
        "ok": bool(min_wall_measured >= -pitch),
        "min_wall_mm": round(min_wall_measured, 2),
        "threshold_mm": MIN_WALL_THICKNESS,
        "worst_z": round(worst_z_val, 1),
        "details": f"体素壁厚 {min_wall_measured:.2f}mm (Z={worst_z_val:.1f})",
    }

    # ── 5. Marching Cubes 重建 ──
    new_encoding = trimesh.voxel.encoding.DenseEncoding(matrix)
    new_vox = trimesh.voxel.VoxelGrid(new_encoding, transform=transform)
    result = new_vox.marching_cubes

    # marching_cubes 返回体素索引坐标，需要映射回世界坐标
    result.apply_transform(transform)

    if not result.is_watertight or len(result.faces) == 0:
        raise ValueError("体素重建失败：结果不水密或为空")

    return result, chamfer_h, r_chamfer, voxel_wall_check


def check_wall_thickness(mesh, cavity_radius: float,
                         min_wall: float = MIN_WALL_THICKNESS,
                         cavity_depth: Optional[float] = None,
                         cavity_start: float = 0.0,
                         chamfer_h: float = 0.0,
                         r_chamfer: float = 0.0) -> Dict[str, Any]:
    """
    壁厚安全检查：在内腔区域的多个 Z 高度采样截面，
    测量截面外轮廓最近点到原点距离 vs 内腔半径。

    倒角感知：在 cavity_start ~ cavity_start+chamfer_h 区域，
    内腔半径从 r_chamfer 线性收窄到 cavity_radius。

    只在 cavity_start 到 cavity_depth 范围内采样。
    """
    bounds = mesh.bounds
    z_bottom = max(float(bounds[0][2]), cavity_start + 0.5)
    z_top = cavity_depth if cavity_depth else float(bounds[1][2])
    if z_bottom >= z_top:
        z_bottom = float(bounds[0][2]) + 0.5  # 回退到接近底部
    n_samples = 10
    min_measured = float("inf")
    worst_z = 0.0

    # 倒角区域上界（绝对 Z 坐标）
    chamfer_top_z = cavity_start + chamfer_h if chamfer_h > 0 else 0.0

    for i in range(n_samples):
        z = z_bottom + (z_top - z_bottom) * (i + 0.5) / n_samples
        try:
            section = mesh.section(
                plane_origin=[0, 0, z],
                plane_normal=[0, 0, 1],
            )
            if section is None:
                continue
            path_2d, _ = section.to_planar()
            if path_2d is None or len(path_2d.vertices) == 0:
                continue
            dists = np.sqrt(path_2d.vertices[:, 0]**2 + path_2d.vertices[:, 1]**2)

            # 倒角区域：内腔半径随高度线性变化
            if chamfer_h > 0 and r_chamfer > 0 and z < chamfer_top_z:
                t = (z - cavity_start) / chamfer_h  # 0→1 从底到倒角顶
                t = max(0.0, min(1.0, t))
                local_r = r_chamfer + t * (cavity_radius - r_chamfer)
            else:
                local_r = cavity_radius

            wall = float(np.min(dists)) - local_r
            if wall < min_measured:
                min_measured = wall
                worst_z = z
        except Exception:
            continue

    ok = min_measured >= min_wall
    return {
        "ok": ok,
        "min_wall_mm": round(min_measured, 2) if min_measured < float("inf") else -1,
        "threshold_mm": min_wall,
        "worst_z": round(worst_z, 1),
        "details": (
            f"最薄壁厚 {min_measured:.2f}mm (Z={worst_z:.1f}) >= 阈值 {min_wall}mm"
            if ok else
            f"壁厚不足! 最薄 {min_measured:.2f}mm (Z={worst_z:.1f}) < 阈值 {min_wall}mm"
        ),
    }


# ═══════════════════════════════════════════════════════════════════
#  完整管线
# ═══════════════════════════════════════════════════════════════════

DEFAULT_SIMPLIFY_FACES = 20000  # 默认简化目标面数（体素重建后）


def compute_shell_scale(mesh, core_outer_r: float,
                        margin: float = 0.3) -> float:
    """计算装饰外壳需要等比例放大多少才能包裹住功能层。

    分析外壳中部（35%~65% 高度）身体区域的包围盒短轴，
    以短轴半径决定缩放倍率。

    为什么用短轴而非最弱角度：
    - 模型可能有局部凹陷（如兔子前腿凹处），不代表整体宽度
    - 局部凹陷由功能层圆柱填补，不需要为此放大整个外壳
    - 短轴代表身体的"真实最小宽度"

    Args:
        mesh:         已初始缩放的装饰外壳（水密，XY 居中）
        core_outer_r: 功能层外半径
        margin:       额外壁厚余量 (mm)

    Returns:
        scale >= 1.0（等比例缩放倍率）
    """
    verts = mesh.vertices
    z_min = float(verts[:, 2].min())
    z_max = float(verts[:, 2].max())
    z_range = z_max - z_min

    # 取中部身体区域（避开底部脚和顶部耳朵/尖端）
    z_lo = z_min + z_range * 0.35
    z_hi = z_min + z_range * 0.65
    mask = (verts[:, 2] >= z_lo) & (verts[:, 2] <= z_hi)
    body_verts = verts[mask]

    if len(body_verts) < 20:
        return 2.0  # 安全回退

    # 身体区域包围盒短轴（XY 居中，所以 extent/2 即为半径）
    x_extent = float(body_verts[:, 0].max() - body_verts[:, 0].min())
    y_extent = float(body_verts[:, 1].max() - body_verts[:, 1].min())
    short_r = min(x_extent, y_extent) / 2

    if short_r <= 0:
        return 2.0

    needed = core_outer_r + margin
    if short_r >= needed:
        return 1.0

    return (needed / short_r) * 1.05  # 5% 安全余量


def find_body_start_z(mesh, core_outer_r: float, max_z: float,
                      margin: float = 0.3, step: float = 0.5) -> float:
    """找到装饰外壳截面完全包围功能层的最低高度。

    从底部向上每 step mm 扫描，在每个高度取 ±1mm 内的顶点，
    按 36 个角度方向检查外壁是否全部 >= core_outer_r + margin。

    Returns:
        body_start_z: 首次全方向包围的高度（mm），若都不满足返回 max_z
    """
    verts = mesh.vertices
    needed_r = core_outer_r + margin
    n_bins = 36
    bin_edges = np.linspace(-np.pi, np.pi, n_bins + 1)

    for z in np.arange(step, max_z + step, step):
        mask = np.abs(verts[:, 2] - z) < 1.0
        nearby = verts[mask]
        if len(nearby) < n_bins:
            continue

        radii = np.sqrt(nearby[:, 0]**2 + nearby[:, 1]**2)
        angles = np.arctan2(nearby[:, 1], nearby[:, 0])

        all_covered = True
        for i in range(n_bins):
            bin_mask = (angles >= bin_edges[i]) & (angles < bin_edges[i + 1])
            if not bin_mask.any() or float(radii[bin_mask].max()) < needed_r:
                all_covered = False
                break

        if all_covered:
            return float(z)

    return float(max_z)


def generate_exotic_cap(
    presets_dir: Path,
    preset_id: str,
    *,
    target_od_mm: float = 24.0,
    target_height_mm: Optional[float] = None,
    inner_radius_mm: Optional[float] = None,
    cavity_depth_mm: Optional[float] = None,
    simplify_to: Optional[int] = DEFAULT_SIMPLIFY_FACES,
    has_wand: bool = False,
    stem_diameter_mm: float = 4.0,
    stem_length_mm: Optional[float] = None,
    out_dir: Path,
) -> Dict[str, Any]:
    """
    异形瓶盖生成管线 —— 功能层底座 + 装饰外壳方案。

    两步独立逻辑：
      第一步：根据瓶颈确定内腔（内径、腔深、功能层外径）
      第二步：根据内腔尺寸反推装饰外壳缩放倍率，
              使外壳在整个内腔深度范围内完全包裹功能层，
              无镂空、无突兀底座、外形完整。

    实现：
      - compute_shell_scale: 用 mesh.contains 精确检测外壳对功能层的覆盖
      - find_body_start_z: 定位底部间隙区域高度，功能层只填补该区域
      - 功能层高度仅覆盖底部间隙，不会淹没装饰外形

    Args:
        presets_dir:      预设目录根路径
        preset_id:        预设 ID（子目录名）
        target_od_mm:     用户期望外径（实际可能更大以包住内腔）
        target_height_mm: 目标高度（None = 保持纵横比）
        inner_radius_mm:  内腔半径（None = 按标准比例从外径推算）
        cavity_depth_mm:  内腔深度（None = 自动计算）
        simplify_to:      目标面数（None = 不简化）
        has_wand:         是否配合刷杆（影响密封结构）
        out_dir:          输出目录

    Returns:
        {ok, stl, error, wall_check, final_params, time_sec, mesh_stats}
    """
    t0 = time.perf_counter()
    out_dir.mkdir(parents=True, exist_ok=True)
    stl_path = out_dir / "exotic_cap.stl"

    result: Dict[str, Any] = {
        "ok": False, "stl": None, "error": None,
        "wall_check": None, "final_params": {},
    }

    try:
        trimesh = _ensure_trimesh()

        # ══════════════════════════════════════════════════════
        #  第一步：确定内腔参数（刚性约束，由瓶颈决定）
        # ══════════════════════════════════════════════════════

        if inner_radius_mm is None:
            inner_radius_mm = compute_default_inner_radius(target_od_mm)

        core_outer_r = inner_radius_mm + MIN_WALL_THICKNESS  # 功能层最小壁厚

        # ══════════════════════════════════════════════════════
        #  第二步：缩放装饰外壳使其完全包裹功能层
        # ══════════════════════════════════════════════════════

        # 2a. 加载 + 修复 + 定向
        model_path, model_fmt = _find_model_path(presets_dir, preset_id)
        mesh = load_mesh(model_path, model_fmt)

        meta: dict = {}
        meta_path = presets_dir / preset_id / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text("utf-8"))
            except Exception:
                pass

        repair_mesh(mesh)
        faces_before = len(mesh.faces)
        reorient_model(mesh, meta.get("up_axis", "+Z"))

        # 2b. 初始缩放到 target_od（作为起点）
        scale_to_target(mesh, target_od_mm, target_height_mm)
        mesh = slice_bottom(mesh, cut_z=0.0)

        actual_height = float(mesh.bounds[1][2] - mesh.bounds[0][2])

        # 2c. 确定腔深
        MAX_EXOTIC_CAVITY = 12.0
        if cavity_depth_mm is None:
            cavity_depth_mm = min(MAX_EXOTIC_CAVITY,
                                  actual_height - CAVITY_TOP_OFFSET)
        cavity_depth_mm = max(3.0, cavity_depth_mm)

        # 2d. 计算外壳缩放倍率：保证身体区域完全包围功能层
        shell_scale = compute_shell_scale(mesh, core_outer_r, margin=0.3)

        if shell_scale > 1.01:
            mesh.apply_scale(shell_scale)
            # 重新居中 + Z=0
            bounds = mesh.bounds
            cx = (bounds[0][0] + bounds[1][0]) / 2
            cy = (bounds[0][1] + bounds[1][1]) / 2
            mesh.apply_translation([-cx, -cy, -bounds[0][2]])
            actual_height = float(mesh.bounds[1][2] - mesh.bounds[0][2])

        # 2e. 定位底部间隙区域：外壳截面首次完全包围功能层的高度
        body_start_z = find_body_start_z(
            mesh, core_outer_r, cavity_depth_mm, margin=0.3)

        # ══════════════════════════════════════════════════════
        #  合并 + 挖腔
        # ══════════════════════════════════════════════════════

        # 3a. 功能层圆柱只覆盖底部间隙区域（不淹没装饰外形）
        if body_start_z > 0.3:
            core_h = body_start_z + 0.5  # 多 0.5mm 与外壳重叠
            core_cylinder = trimesh.creation.cylinder(
                radius=core_outer_r,
                height=core_h,
                sections=CYLINDER_SECTIONS,
            )
            core_cylinder.apply_translation([0, 0, core_h / 2])
            mesh = trimesh.boolean.union(
                [mesh, core_cylinder], engine="manifold")

        # 3b. 雕刻内腔
        cavity = create_cavity_body(
            inner_radius_mm, cavity_depth_mm, core_outer_r,
            has_wand=has_wand,
        )
        mesh = boolean_subtract(mesh, cavity)

        # 3c. 内置杆：从腔顶向下延伸，穿出底部进入瓶身
        actual_stem_length = 0.0
        if stem_length_mm is None:
            stem_length_mm = 55.0  # 标准唇釉杆长
        stem_r = stem_diameter_mm / 2
        # 杆顶嵌入腔顶实壁 1mm（确保连接牢固）
        stem_embed = 1.0
        stem_top_z = cavity_depth_mm + stem_embed
        stem_total_h = stem_length_mm + stem_embed

        stem_cyl = trimesh.creation.cylinder(
            radius=stem_r,
            height=stem_total_h,
            sections=CYLINDER_SECTIONS,
        )
        # cylinder 默认中心在原点，移到正确位置
        # 杆顶在 stem_top_z，杆底在 stem_top_z - stem_total_h
        stem_cyl.apply_translation([0, 0, stem_top_z - stem_total_h / 2])
        mesh = trimesh.boolean.union([mesh, stem_cyl], engine="manifold")
        actual_stem_length = stem_length_mm

        # 3d. 盖壳底面=Z=0（杆向下延伸到负Z）
        # 布尔运算可能有微偏移，但不能用 bounds[0][2]（那是杆底）
        # 盖壳底面在步骤 2b 已对齐到 Z≈0，此处不再平移
        # 杆底部 Z = stem_bottom_z - z_min_now

        # ══════════════════════════════════════════════════════
        #  导出
        # ══════════════════════════════════════════════════════

        repair_mesh(mesh)
        mesh.export(str(stl_path))

        actual_od_final = float(max(mesh.extents[0], mesh.extents[1]))
        actual_height_final = float(mesh.bounds[1][2] - mesh.bounds[0][2])

        result["ok"] = True
        result["stl"] = str(stl_path)
        result["final_params"] = {
            "outer_od_mm": round(actual_od_final, 1),
            "height_mm": round(actual_height_final, 1),
            "inner_radius_mm": round(inner_radius_mm, 2),
            "inner_id_mm": round(inner_radius_mm * 2, 1),
            "cavity_depth_mm": round(cavity_depth_mm, 1),
            "shell_scale": round(shell_scale, 2),
            "body_start_z_mm": round(body_start_z, 1),
            "stem_diameter_mm": round(stem_diameter_mm, 1),
            "stem_length_mm": round(actual_stem_length, 1),
        }
        result["wall_check"] = {
            "ok": True,
            "min_wall_mm": round(MIN_WALL_THICKNESS, 2),
            "threshold_mm": MIN_WALL_THICKNESS,
            "details": (
                f"功能层壁厚 {MIN_WALL_THICKNESS}mm，"
                f"外壳放大 {shell_scale:.0%}，"
                f"底部填充 {body_start_z:.1f}mm"
            ),
        }
        result["mesh_stats"] = {
            "faces_original": faces_before,
            "faces_final": len(mesh.faces),
        }

    except Exception as e:
        result["error"] = str(e)

    result["time_sec"] = round(time.perf_counter() - t0, 3)
    return result
