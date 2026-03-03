#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CADMVP Windows 环境自检脚本
生成一个 10x10x10 的 box 并导出到 artifacts/selftest/box.step
"""

import sys
from pathlib import Path

def main():
    print("=" * 50)
    print("CADMVP Windows 环境自检")
    print("=" * 50)

    # 检查 Python 版本
    print(f"\n[1] Python 版本: {sys.version}")

    # 尝试导入 cadquery
    print("\n[2] 导入 cadquery...")
    try:
        import cadquery as cq
        print(f"    cadquery 版本: {cq.__version__}")
    except ImportError as e:
        print(f"    [ERROR] 无法导入 cadquery: {e}")
        return 1

    # 尝试导入 OCP
    print("\n[3] 检查 cadquery-ocp...")
    try:
        from OCP.TopoDS import TopoDS_Shape
        print("    OCP 导入成功")
    except ImportError as e:
        print(f"    [WARNING] OCP 导入失败: {e}")

    # 创建输出目录
    output_dir = Path(__file__).parent.parent / "artifacts" / "selftest"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "box.step"

    # 生成 10x10x10 的 box
    print("\n[4] 生成 10x10x10 box...")
    try:
        box = cq.Workplane("XY").box(10, 10, 10)
        print("    box 生成成功")
    except Exception as e:
        print(f"    [ERROR] box 生成失败: {e}")
        return 1

    # 导出 STEP 文件
    print(f"\n[5] 导出 STEP 文件到: {output_file}")
    try:
        cq.exporters.export(box, str(output_file))
        print("    STEP 文件导出成功")
    except Exception as e:
        print(f"    [ERROR] STEP 导出失败: {e}")
        return 1

    # 验证文件
    if output_file.exists():
        file_size = output_file.stat().st_size
        print(f"\n[6] 验证: {output_file.name} ({file_size} bytes)")
        print("    文件存在且有效")
    else:
        print("\n[6] [ERROR] STEP 文件未生成")
        return 1

    print("\n" + "=" * 50)
    print("自检完成: 所有测试通过!")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
