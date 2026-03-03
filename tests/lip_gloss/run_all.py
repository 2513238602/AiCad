# -*- coding: utf-8 -*-
"""
唇釉瓶产品 - 全量测试运行器

用法：
    python tests/lip_gloss/run_all.py           # 运行全部测试
    python tests/lip_gloss/run_all.py --quick    # 仅约束穷举（跳过3D几何）
    python tests/lip_gloss/run_all.py --quiet    # 简略输出

每次更新约束系统后必须运行此脚本以确保无回归。
"""
from __future__ import annotations

import sys
import argparse

from test_constraint_exhaustive import run_exhaustive_test
from test_param_storage import run_param_storage_test
from test_geometry import run_geometry_test


def main():
    ap = argparse.ArgumentParser(description="唇釉瓶全量测试")
    ap.add_argument("--quick", action="store_true", help="仅约束穷举，跳过3D几何")
    ap.add_argument("--quiet", action="store_true", help="简略输出")
    args = ap.parse_args()

    results = {}

    # Part 1: 约束穷举测试（核心）
    results["约束穷举"] = run_exhaustive_test(verbose=not args.quiet)

    # Part 2: 参数存储完整性
    results["参数存储"] = run_param_storage_test()

    # Part 3: 3D 几何（可跳过）
    if not args.quick:
        results["3D几何"] = run_geometry_test()
    else:
        results["3D几何"] = None  # 跳过

    # 汇总
    print(f"\n{'='*70}")
    print(f"  唇釉瓶全量测试 - 最终结果")
    print(f"{'='*70}")
    all_ok = True
    for name, ok in results.items():
        if ok is None:
            label = "SKIP"
        elif ok:
            label = "PASS"
        else:
            label = "FAIL"
            all_ok = False
        print(f"  {name:20s} {label}")

    print(f"\n  总结: {'ALL PASS' if all_ok else 'SOME FAILED'}")
    return all_ok


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
