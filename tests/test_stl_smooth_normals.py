#!/usr/bin/env python3
"""
外观质量自动化测试：模拟前端 mergeVertices + computeVertexNormals 的效果。
验证：合并顶点 + 平滑法线后，弯曲表面的法线变化应 ≤ 阈值（无可见条带）。

测试逻辑：
1. 生成 cap/bottle STL（spline 模式）
2. 解析 STL 三角面片
3. 按顶点位置合并（模拟 Three.js mergeVertices）
4. 计算平滑顶点法线（模拟 Three.js computeVertexNormals）
5. 度量相邻面的法线角度差
6. 判定：
   - 合并前：相邻面法线角度差 > 阈值 → 可见条带（已知问题）
   - 合并后：相邻面法线角度差 < 阈值 → 平滑渲染（修复有效）
"""
import struct
import sys
import os
import math
import tempfile
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import numpy as np


def parse_binary_stl(filepath: str):
    """解析二进制 STL 文件，返回 (normals, vertices) 数组。"""
    with open(filepath, 'rb') as f:
        header = f.read(80)
        num_triangles = struct.unpack('<I', f.read(4))[0]
        normals = []
        vertices = []
        for _ in range(num_triangles):
            data = struct.unpack('<12fH', f.read(50))
            n = np.array(data[0:3])
            v0 = np.array(data[3:6])
            v1 = np.array(data[6:9])
            v2 = np.array(data[9:12])
            normals.append(n)
            vertices.append((v0, v1, v2))
    return np.array(normals), vertices


def merge_vertices_and_smooth(normals, vertices, tolerance=1e-4, crease_angle_deg=30.0):
    """模拟 Three.js toCreasedNormals。
    crease_angle_deg: 面间角度 < 此值 → 平滑; >= 此值 → 保留锐边。

    返回：
    - smoothed_face_normals: 每个三角面的平滑法线
    - vertex_map: unused (kept for API compat)
    """
    crease_cos = math.cos(math.radians(crease_angle_deg))

    # Step 1: 计算每个三角面的几何法线
    geo_normals = []
    for i, (v0, v1, v2) in enumerate(vertices):
        edge1 = v1 - v0
        edge2 = v2 - v0
        n = np.cross(edge1, edge2)
        length = np.linalg.norm(n)
        if length > 1e-10:
            n = n / length
        else:
            n = normals[i]
        geo_normals.append(n)
    geo_normals = np.array(geo_normals)

    # Step 2: 按位置合并顶点，构建 vertex → face 映射
    vert_to_faces = defaultdict(list)  # key=rounded pos, value=[(face_idx, vert_idx_in_face)]
    for i, (v0, v1, v2) in enumerate(vertices):
        for vi, v in enumerate((v0, v1, v2)):
            key = tuple(np.round(v / tolerance).astype(int))
            vert_to_faces[key].append((i, vi))

    # Step 3: 对每个顶点，按 crease angle 分组并计算平滑法线
    # face_vertex_normals[face_idx][vert_idx] = smoothed normal
    face_vertex_normals = [[None, None, None] for _ in range(len(vertices))]

    for key, face_verts in vert_to_faces.items():
        # 对此顶点的所有面，按法线相似度分组
        assigned = [False] * len(face_verts)
        groups = []
        for i in range(len(face_verts)):
            if assigned[i]:
                continue
            group = [i]
            assigned[i] = True
            n_i = geo_normals[face_verts[i][0]]
            for j in range(i + 1, len(face_verts)):
                if assigned[j]:
                    continue
                n_j = geo_normals[face_verts[j][0]]
                if np.dot(n_i, n_j) >= crease_cos:
                    group.append(j)
                    assigned[j] = True
            groups.append(group)

        for group in groups:
            # 组内法线平均
            avg = np.mean([geo_normals[face_verts[gi][0]] for gi in group], axis=0)
            length = np.linalg.norm(avg)
            if length > 1e-10:
                avg = avg / length
            for gi in group:
                fi, vi = face_verts[gi]
                face_vertex_normals[fi][vi] = avg

    # Step 4: 计算每个面的平滑后"代表法线"（3个顶点法线平均）
    smoothed_face_normals = []
    for i in range(len(vertices)):
        vn = face_vertex_normals[i]
        vals = [v for v in vn if v is not None]
        if vals:
            avg = np.mean(vals, axis=0)
            length = np.linalg.norm(avg)
            if length > 1e-10:
                avg = avg / length
            smoothed_face_normals.append(avg)
        else:
            smoothed_face_normals.append(geo_normals[i])

    return np.array(smoothed_face_normals), {}


def angle_between(n1, n2):
    """两个法线之间的角度（度）。"""
    dot = np.clip(np.dot(n1, n2), -1.0, 1.0)
    return math.degrees(math.acos(dot))


def find_adjacent_faces(vertices, tolerance=1e-4):
    """找到共享边的相邻面对。"""
    edge_to_faces = defaultdict(list)

    for i, (v0, v1, v2) in enumerate(vertices):
        verts = [
            tuple(np.round(v0 / tolerance).astype(int)),
            tuple(np.round(v1 / tolerance).astype(int)),
            tuple(np.round(v2 / tolerance).astype(int)),
        ]
        for a in range(3):
            for b in range(a + 1, 3):
                edge = tuple(sorted([verts[a], verts[b]]))
                edge_to_faces[edge].append(i)

    pairs = set()
    for edge, faces in edge_to_faces.items():
        for a in range(len(faces)):
            for b in range(a + 1, len(faces)):
                pairs.add((min(faces[a], faces[b]), max(faces[a], faces[b])))

    return pairs


def analyze_stl_quality(filepath: str, label: str):
    """分析 STL 的法线质量，输出报告。"""
    normals, vertices = parse_binary_stl(filepath)
    n_faces = len(normals)

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  三角面数: {n_faces}")

    # 找相邻面
    adj_pairs = find_adjacent_faces(vertices)
    print(f"  相邻面对数: {len(adj_pairs)}")

    # 修复前：原始面法线之间的角度差
    raw_angles = []
    for i, j in adj_pairs:
        a = angle_between(normals[i], normals[j])
        if a < 90:  # 忽略内外面交界（锐角折叠）
            raw_angles.append(a)

    raw_angles = np.array(raw_angles)
    print(f"\n  [修复前] 相邻面法线角度差 (仅弯曲区域 <90°):")
    print(f"    面对数: {len(raw_angles)}")
    if len(raw_angles) > 0:
        print(f"    最大: {raw_angles.max():.2f}°")
        print(f"    平均: {raw_angles.mean():.2f}°")
        print(f"    P95:  {np.percentile(raw_angles, 95):.2f}°")
        print(f"    P99:  {np.percentile(raw_angles, 99):.2f}°")
        # 角度差 > 5° 的面对 → 可能可见的条带
        visible_bands = np.sum(raw_angles > 5.0)
        print(f"    >5°的面对: {visible_bands} ({visible_bands/len(raw_angles)*100:.1f}%)")

    # 修复后：mergeVertices + computeVertexNormals 效果
    smoothed_normals, _ = merge_vertices_and_smooth(normals, vertices)

    smooth_angles = []
    for i, j in adj_pairs:
        a = angle_between(smoothed_normals[i], smoothed_normals[j])
        if a < 90:
            smooth_angles.append(a)

    smooth_angles = np.array(smooth_angles)
    print(f"\n  [修复后] mergeVertices + computeVertexNormals:")
    print(f"    面对数: {len(smooth_angles)}")
    if len(smooth_angles) > 0:
        print(f"    最大: {smooth_angles.max():.2f}°")
        print(f"    平均: {smooth_angles.mean():.2f}°")
        print(f"    P95:  {np.percentile(smooth_angles, 95):.2f}°")
        print(f"    P99:  {np.percentile(smooth_angles, 99):.2f}°")
        visible_bands = np.sum(smooth_angles > 5.0)
        print(f"    >5°的面对: {visible_bands} ({visible_bands/len(smooth_angles)*100:.1f}%)")

    # 改善率
    if len(raw_angles) > 0 and len(smooth_angles) > 0:
        improvement = (1 - smooth_angles.mean() / raw_angles.mean()) * 100
        print(f"\n  平均角度差改善: {improvement:.1f}%")

    # 判定：>5度 的面对比例 < 5% 视为通过
    band_threshold = 5.0  # 度
    ratio_threshold = 0.05  # 5%
    if len(smooth_angles) > 0:
        visible_ratio = np.sum(smooth_angles > band_threshold) / len(smooth_angles)
        if visible_ratio < ratio_threshold:
            print(f"\n  [PASS] >5deg 面对比例: {visible_ratio*100:.1f}% < {ratio_threshold*100:.0f}%")
            return True
        else:
            print(f"\n  [FAIL] >5deg 面对比例: {visible_ratio*100:.1f}% >= {ratio_threshold*100:.0f}%")
            return False
    return True


def main():
    import cadquery as cq
    from core.modeler import Modeler
    from products.lip_gloss.components.cap import CapComponent
    from products.lip_gloss.components.bottle import BottleComponent

    m = Modeler()
    tmpdir = tempfile.mkdtemp(prefix="stl_test_")
    results = []

    def get_defaults(comp_cls):
        s = comp_cls().schema()
        return {p['k']: p['default'] for p in s['params']}

    # === 测试 1: Cap (spline 模式) ===
    print("\n生成 Cap (spline 模式)...")
    cap_p = get_defaults(CapComponent)
    cap_p["profile_mode"] = "spline"
    cap_p["profile_points_json"] = "[]"
    cap_meta = {}
    cap_solid = m.build("cap", cap_p, cap_meta)

    cap_stl = os.path.join(tmpdir, "cap_spline.stl")
    cq.exporters.export(cap_solid, cap_stl, tolerance=0.01, angularTolerance=0.05)
    results.append(analyze_stl_quality(cap_stl, "Cap (spline 模式)"))

    # === 测试 2: Cap (classic 模式) ===
    print("\n生成 Cap (classic 模式)...")
    cap_p2 = get_defaults(CapComponent)
    cap_p2["profile_mode"] = "classic"
    cap_meta2 = {}
    cap_solid2 = m.build("cap", cap_p2, cap_meta2)

    cap_stl2 = os.path.join(tmpdir, "cap_classic.stl")
    cq.exporters.export(cap_solid2, cap_stl2, tolerance=0.01, angularTolerance=0.05)
    results.append(analyze_stl_quality(cap_stl2, "Cap (classic 模式)"))

    # === 测试 3: Bottle (spline 对称模式) ===
    print("\n生成 Bottle (spline 对称模式)...")
    bottle_p = get_defaults(BottleComponent)
    bottle_p["profile_mode"] = "spline"
    bottle_p["profile_symmetry"] = "symmetric"
    bottle_p["profile_points_json"] = "[]"
    bottle_p["thread.enabled"] = False  # 简化测试
    bottle_meta = {}
    bottle_solid = m.build("bottle", bottle_p, bottle_meta)

    bottle_stl = os.path.join(tmpdir, "bottle_spline_sym.stl")
    cq.exporters.export(bottle_solid, bottle_stl, tolerance=0.01, angularTolerance=0.05)
    results.append(analyze_stl_quality(bottle_stl, "Bottle (spline sym)"))

    # === 测试 4: Bottle (classic 模式) ===
    print("\n生成 Bottle (classic 模式)...")
    bottle_p2 = get_defaults(BottleComponent)
    bottle_p2["profile_mode"] = "classic"
    bottle_p2["thread.enabled"] = False
    bottle_meta2 = {}
    bottle_solid2 = m.build("bottle", bottle_p2, bottle_meta2)

    bottle_stl2 = os.path.join(tmpdir, "bottle_classic.stl")
    cq.exporters.export(bottle_solid2, bottle_stl2, tolerance=0.01, angularTolerance=0.05)
    results.append(analyze_stl_quality(bottle_stl2, "Bottle (classic)"))

    # === 汇总 ===
    print(f"\n{'='*60}")
    print("  汇总")
    print(f"{'='*60}")
    all_pass = all(results)
    if all_pass:
        print("  ALL PASS - mergeVertices + computeVertexNormals fix works")
    else:
        print("  SOME FAILED")
        for i, r in enumerate(results):
            status = "PASS" if r else "FAIL"
            print(f"    Test {i+1}: {status}")

    # 清理
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
