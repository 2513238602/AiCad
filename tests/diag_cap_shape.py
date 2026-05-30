#!/usr/bin/env python3
"""
诊断脚本：分析 spline cap 的 BREP 拓扑和外壁几何。
目的：找到"看起来像两个东西"的根因。
"""
import sys, os, math, json, tempfile, struct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import cadquery as cq
import numpy as np
from core.modeler import Modeler
from products.lip_gloss.components.cap import CapComponent
from products.lip_gloss.derived_params import generate_default_cap_profile


def get_defaults(comp_cls):
    s = comp_cls().schema()
    return {p['k']: p['default'] for p in s['params']}


def analyze_brep(solid, label):
    """分析 BREP 拓扑。"""
    print(f"\n{'='*60}")
    print(f"  {label} - BREP 拓扑分析")
    print(f"{'='*60}")

    faces = solid.faces().vals()
    edges = solid.edges().vals()
    print(f"  面数: {len(faces)}")
    print(f"  边数: {len(edges)}")

    face_info = []
    for i, face in enumerate(faces):
        bb = face.BoundingBox()
        # 面类型：通过 geomType() 方法
        try:
            gtype = face.geomType()
        except Exception:
            gtype = "Unknown"

        # 面积
        try:
            area = face.Area()
        except Exception:
            area = 0

        face_info.append({
            'idx': i, 'type': gtype, 'area': area,
            'xmin': bb.xmin, 'xmax': bb.xmax,
            'ymin': bb.ymin, 'ymax': bb.ymax,
            'zmin': bb.zmin, 'zmax': bb.zmax,
        })

    # 按面积排序
    face_info.sort(key=lambda f: -f['area'])
    print(f"\n  各面详情 (按面积降序):")
    print(f"  {'#':>3} {'类型':>15} {'面积':>10} {'Z范围':>20} {'XY范围(R)':>20}")
    for f in face_info:
        r_max = math.sqrt(f['xmax']**2 + f['ymax']**2)
        print(f"  {f['idx']:3d} {f['type']:>15} {f['area']:10.2f} "
              f"  Z=[{f['zmin']:6.2f}, {f['zmax']:6.2f}] "
              f"  R_max={r_max:6.2f}")

    # 关键检查：外壁面
    outer_faces = [f for f in face_info
                   if f['zmax'] - f['zmin'] > 5.0
                   and f['xmax'] > 5.0]
    print(f"\n  [关键] 外壁候选面 (Z跨度>5mm, X>5mm): {len(outer_faces)}")
    for f in outer_faces:
        print(f"    面 {f['idx']}: {f['type']}, "
              f"Z=[{f['zmin']:.2f}, {f['zmax']:.2f}], 面积={f['area']:.2f}")

    # 检查边的 Z 坐标分布——找水平边（可能导致分段外观）
    print(f"\n  边的 Z 分布 (找水平环):")
    edge_z = []
    for i, edge in enumerate(edges):
        bb = edge.BoundingBox()
        z_span = bb.zmax - bb.zmin
        if z_span < 0.5:  # 接近水平的边
            z_mid = (bb.zmin + bb.zmax) / 2
            r_mid = math.sqrt(bb.xmax**2 + bb.ymax**2)
            edge_z.append((z_mid, r_mid, i))
    edge_z.sort()
    for z, r, idx in edge_z:
        print(f"    边 {idx}: z={z:.2f}, R={r:.2f}")

    return face_info


def analyze_stl_outer_wall(stl_path, H, r0):
    """分析 STL 外壁的半径 vs Z。"""
    print(f"\n{'='*60}")
    print(f"  STL 外壁半径 vs Z 分析")
    print(f"{'='*60}")

    with open(stl_path, 'rb') as f:
        f.read(80)
        n_tri = struct.unpack('<I', f.read(4))[0]
        vertices = []
        for _ in range(n_tri):
            data = struct.unpack('<12fH', f.read(50))
            for vi in range(3):
                x, y, z = data[3+vi*3], data[4+vi*3], data[5+vi*3]
                r = math.sqrt(x*x + y*y)
                vertices.append((r, z))

    # 只看外壁顶点 (R > r0 * 0.8)
    outer_verts = [(r, z) for r, z in vertices if r > r0 * 0.8 and 0 <= z <= H]

    # 按 Z 分 bin
    n_bins = 50
    z_bins = np.linspace(0, H, n_bins + 1)
    max_r_per_bin = np.full(n_bins, -1.0)

    for r, z in outer_verts:
        bi = min(int(z / H * n_bins), n_bins - 1)
        if r > max_r_per_bin[bi]:
            max_r_per_bin[bi] = r

    # 找突变
    jumps = []
    prev_r = None
    for i in range(n_bins):
        z_mid = (z_bins[i] + z_bins[i+1]) / 2
        r = max_r_per_bin[i]
        if r < 0:
            prev_r = None
            continue
        if prev_r is not None:
            d = r - prev_r
            if abs(d) > 0.03:
                jumps.append((z_mid, d, r))
        prev_r = r

    # 输出外壁 R 的 ASCII 图
    valid = [(i, max_r_per_bin[i]) for i in range(n_bins) if max_r_per_bin[i] > 0]
    if valid:
        r_min_v = min(r for _, r in valid)
        r_max_v = max(r for _, r in valid)
        r_range = max(r_max_v - r_min_v, 0.01)
        print(f"\n  外壁 R vs Z (范围: {r_min_v:.3f} ~ {r_max_v:.3f}):")
        width = 40
        for i, r in valid:
            z_mid = (z_bins[i] + z_bins[i+1]) / 2
            pos = int((r - r_min_v) / r_range * (width - 1))
            pos = max(0, min(pos, width - 1))
            bar = '.' * pos + '#' + '.' * (width - pos - 1)
            marker = " <--JUMP" if any(abs(z_mid - jz) < H/n_bins for jz, _, _ in jumps) else ""
            print(f"    z={z_mid:5.1f} |{bar}| r={r:.4f}{marker}")

    if jumps:
        print(f"\n  [WARNING] 检测到 {len(jumps)} 个外壁半径突变 (>0.03mm):")
        for z, d, r in jumps:
            print(f"    z={z:.1f}: delta_r={d:+.4f}, r={r:.4f}")
    else:
        print(f"\n  [OK] 外壁半径平滑变化")

    return jumps


def main():
    m = Modeler()
    tmpdir = tempfile.mkdtemp(prefix="diag_cap_")

    cap_p = get_defaults(CapComponent)
    cap_p["profile_mode"] = "spline"
    cap_p["profile_points_json"] = "[]"

    OD = float(cap_p['outer_od_mm'])
    H = float(cap_p['height_mm'])
    taper_deg = max(float(cap_p.get('taper_deg', 0)), 0.5)
    delta_r = math.tan(math.radians(taper_deg)) * H
    OD_top = max(OD - delta_r, OD * 0.7)
    r0 = OD / 2.0
    r1 = OD_top / 2.0

    print("="*60)
    print("  Cap 形状诊断")
    print("="*60)
    print(f"  OD={OD}, H={H}, ID={cap_p['inner_id_mm']}, "
          f"taper={cap_p.get('taper_deg', 0)}")
    print(f"  r0={r0:.3f}, r1={r1:.3f}")

    # Profile 分析
    pts = generate_default_cap_profile(r0, r1, H)
    print(f"\n  Profile 控制点:")
    for i, (r, z) in enumerate(pts):
        tag = " <-- WIDER than r0!" if i > 0 and r > r0 else ""
        print(f"    [{i}] r={r:.4f}, z={z:.2f}{tag}")
    mono = all(pts[i][0] >= pts[i+1][0] for i in range(len(pts)-1))
    print(f"  R 单调递减: {'YES' if mono else 'NO (barrel/pumpkin shape!)'}")

    # 生成 cap
    print(f"\n  生成 Cap (spline)...")
    meta = {}
    cap_solid = m.build("cap", cap_p, meta)

    print(f"  meta.profile_mode = {meta.get('profile_mode')}")
    print(f"  meta.profile_points = {meta.get('profile_points')}")
    print(f"  meta.effective_cavity_depth = {meta.get('effective_cavity_depth')}")
    if 'degraded' in meta:
        for d in meta['degraded']:
            print(f"  [DEGRADED] {d['feature']}: {d['error']}")

    # BREP 分析
    analyze_brep(cap_solid, "Cap (spline)")

    # STL 分析
    stl_path = os.path.join(tmpdir, "cap_spline.stl")
    cq.exporters.export(cap_solid, stl_path, tolerance=0.01, angularTolerance=0.05)
    jumps = analyze_stl_outer_wall(stl_path, H, r0)

    # ============ 对比: classic ============
    print(f"\n\n{'#'*60}")
    print(f"  对比: Cap (classic)")
    print(f"{'#'*60}")
    cap_p2 = get_defaults(CapComponent)
    cap_p2["profile_mode"] = "classic"
    meta2 = {}
    cap_solid2 = m.build("cap", cap_p2, meta2)
    if 'degraded' in meta2:
        for d in meta2['degraded']:
            print(f"  [DEGRADED] {d['feature']}: {d['error']}")
    analyze_brep(cap_solid2, "Cap (classic)")

    stl_path2 = os.path.join(tmpdir, "cap_classic.stl")
    cq.exporters.export(cap_solid2, stl_path2, tolerance=0.01, angularTolerance=0.05)
    jumps2 = analyze_stl_outer_wall(stl_path2, H, r0)

    # 清理
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    # 总结
    print(f"\n\n{'='*60}")
    print(f"  诊断总结")
    print(f"{'='*60}")
    print(f"  Spline: {len(jumps)} 个外壁突变")
    print(f"  Classic: {len(jumps2)} 个外壁突变")

    # 关键对比
    spline_faces = len(cap_solid.faces().vals())
    classic_faces = len(cap_solid2.faces().vals())
    print(f"  Spline 面数: {spline_faces}")
    print(f"  Classic 面数: {classic_faces}")


if __name__ == "__main__":
    main()
