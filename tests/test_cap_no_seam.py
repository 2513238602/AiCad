#!/usr/bin/env python3
"""
外观质量测试：验证 spline 模式生成的 cap/bottle 外壁不会出现
"两段"外观（可见水平接缝）。

根因：OCCT 在 revolve B-spline 时会在 spline knot 处分裂旋转面，
      每个分裂面的 tessellation 独立，形成水平几何边缘（接缝）。
修复：将 _spline_revolve 改用 circle loft（密集采样 + 圆截面 loft），
      消除 spline knot 导致的面分裂。

测试方法：
1. 生成 cap/bottle (spline 模式) 的 BREP
2. 检测外壁面数量和 Z 覆盖范围
3. 判定：外壁不应有"中间接缝"——即在排除底部 fillet/chamfer 和顶部 fillet
   之后，中间的主外壁应为单一连续面，Z 覆盖 > 60% 总高。
"""
import sys
import os
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def get_defaults(comp_cls):
    s = comp_cls().schema()
    return {p['k']: p['default'] for p in s['params']}


def find_outer_wall_faces(solid, H):
    """找到外壁面（Z 跨度 > H*0.2 且 R > 5mm 的面）。"""
    faces = solid.faces().vals()
    outer_faces = []
    for i, face in enumerate(faces):
        bb = face.BoundingBox()
        z_span = bb.zmax - bb.zmin
        r_max = math.sqrt(bb.xmax ** 2 + bb.ymax ** 2)
        if z_span > H * 0.2 and r_max > 5.0:
            outer_faces.append({
                'idx': i,
                'type': face.geomType(),
                'zmin': bb.zmin,
                'zmax': bb.zmax,
                'z_span': z_span,
                'r_max': r_max,
            })
    return outer_faces


def check_no_mid_seam(label, solid, H, verbose=True):
    """检查外壁没有中间接缝。

    判定标准：
    - 应有 1 个主外壁面，Z 覆盖 ≥ 60% 总高
    - 不应有多个外壁面在 Z 上首尾相连（=中间有接缝）

    返回 True=通过, False=失败
    """
    outer_faces = find_outer_wall_faces(solid, H)

    if verbose:
        print(f"\n  {label}")
        print(f"  {'─' * 50}")
        print(f"  总高: {H:.1f}mm, 外壁候选面: {len(outer_faces)}")
        for f in outer_faces:
            coverage = f['z_span'] / H * 100
            print(f"    面{f['idx']}: {f['type']}, "
                  f"Z=[{f['zmin']:.2f}, {f['zmax']:.2f}], "
                  f"覆盖={coverage:.1f}%")

    # 检查: 排除内腔面（CYLINDER 类型且 R_max < 外壁面 R_max * 0.95）
    if outer_faces:
        max_r = max(f['r_max'] for f in outer_faces)
        outer_faces = [f for f in outer_faces if f['r_max'] > max_r * 0.95]

    if not outer_faces:
        if verbose:
            print(f"  [FAIL] 未找到外壁面")
        return False

    # 找最大 Z 覆盖的主外壁面
    main_face = max(outer_faces, key=lambda f: f['z_span'])
    coverage = main_face['z_span'] / H

    if coverage < 0.60:
        if verbose:
            print(f"  [FAIL] 主外壁面 Z 覆盖仅 {coverage*100:.1f}% < 60%")
            print(f"         这意味着外壁被分裂为多个小面，会产生可见接缝")
        return False

    # 检查: 不应有其他外壁面紧邻主面（说明有接缝）
    mid_start = H * 0.15  # 排除底部 15%（fillet/chamfer 区域）
    mid_end = H * 0.85    # 排除顶部 15%（fillet 区域）
    mid_seam_faces = [
        f for f in outer_faces
        if f['idx'] != main_face['idx']
        and f['zmin'] > mid_start
        and f['zmax'] < mid_end
    ]

    if mid_seam_faces:
        if verbose:
            print(f"  [FAIL] 中间区域发现额外外壁面（接缝）:")
            for f in mid_seam_faces:
                print(f"    面{f['idx']}: Z=[{f['zmin']:.2f}, {f['zmax']:.2f}]")
        return False

    if verbose:
        print(f"  [PASS] 主外壁面覆盖 {coverage*100:.1f}% 总高，"
              f"无中间接缝")
    return True


def main():
    from core.modeler import Modeler
    from products.lip_gloss.components.cap import CapComponent
    from products.lip_gloss.components.bottle import BottleComponent

    m = Modeler()
    results = []

    print("=" * 60)
    print("  外壁接缝测试 (cap/bottle spline 模式)")
    print("=" * 60)

    # === Test 1: Cap spline ===
    cap_p = get_defaults(CapComponent)
    cap_p["profile_mode"] = "spline"
    cap_p["profile_points_json"] = "[]"
    cap_meta = {}
    cap_solid = m.build("cap", cap_p, cap_meta)
    H_cap = float(cap_p["height_mm"])
    results.append(check_no_mid_seam("Cap (spline, 默认轮廓)", cap_solid, H_cap))

    # === Test 2: Cap spline 自定义 5 点轮廓 ===
    import json
    cap_p2 = get_defaults(CapComponent)
    cap_p2["profile_mode"] = "spline"
    OD = float(cap_p2["outer_od_mm"])
    H = float(cap_p2["height_mm"])
    r0 = OD / 2
    # 自定义弧形轮廓（保持壁厚安全: r >= inner_r + 0.3 ≈ 11.5）
    ID = float(cap_p2.get("inner_id_mm", 22.4))
    r_min_safe = ID / 2 + 0.5  # 保守一点
    r_top_custom = max(r0 * 0.97, r_min_safe)
    custom_pts = [
        [r0, 0.0],
        [r0 - 0.05, H * 0.2],
        [r0 - 0.10, H * 0.5],
        [r0 - 0.20, H * 0.8],
        [r_top_custom, H],
    ]
    cap_p2["profile_points_json"] = json.dumps(custom_pts)
    cap_meta2 = {}
    cap_solid2 = m.build("cap", cap_p2, cap_meta2)
    results.append(check_no_mid_seam("Cap (spline, 自定义 5 点)", cap_solid2, H))

    # === Test 3: Bottle spline symmetric ===
    bottle_p = get_defaults(BottleComponent)
    bottle_p["profile_mode"] = "spline"
    bottle_p["profile_symmetry"] = "symmetric"
    bottle_p["profile_points_json"] = "[]"
    bottle_p["thread.enabled"] = False
    bottle_meta = {}
    bottle_solid = m.build("bottle", bottle_p, bottle_meta)
    H_bottle = float(bottle_p["height_mm"])
    results.append(check_no_mid_seam("Bottle (spline sym, 默认轮廓)", bottle_solid, H_bottle))

    # === 汇总 ===
    print(f"\n{'=' * 60}")
    all_pass = all(results)
    labels = [
        "Cap 默认轮廓",
        "Cap 自定义轮廓",
        "Bottle 默认轮廓",
    ]
    for label, passed in zip(labels, results):
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {label}")

    if all_pass:
        print(f"\n  ALL PASS - 无中间接缝")
    else:
        print(f"\n  SOME FAILED - 外壁存在分裂接缝")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
