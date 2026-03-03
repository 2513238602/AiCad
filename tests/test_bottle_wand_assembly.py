#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
瓶身 + 刷杆 真实装配测试

测试目标：
1. 生成瓶身，记录其螺纹参数
2. 基于瓶身参数生成配套的刷杆
3. 验证两者可以成功生成并且参数匹配
4. 测试多种不同尺寸的组合
"""

import sys
import os
import json

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from products.lip_gloss.components.bottle import BottleComponent
from products.lip_gloss.components.wand import WandComponent


def test_single_assembly(bottle_params: dict, test_name: str) -> dict:
    """测试单个瓶身+刷杆装配"""
    print(f"\n{'='*60}")
    print(f"测试: {test_name}")
    print('='*60)

    result = {
        "name": test_name,
        "bottle_ok": False,
        "wand_ok": False,
        "params_match": False,
        "errors": []
    }

    # 1. 生成瓶身
    print(f"\n[1] 生成瓶身...")
    print(f"    瓶身参数: neck_od={bottle_params.get('neck_od_mm', 18.0)}mm, "
          f"pitch={bottle_params.get('thread', {}).get('pitch_mm', 2.7)}mm, "
          f"turns={bottle_params.get('thread', {}).get('turns', 2)}")

    bottle_comp = BottleComponent()
    bottle_result = bottle_comp.generate(
        user_params=bottle_params,
        outroot="artifacts/test_assembly"
    )

    if bottle_result["ok"]:
        print(f"    [OK] 瓶身生成成功")
        result["bottle_ok"] = True
        result["bottle_step"] = bottle_result.get("step")
    else:
        error = bottle_result.get("error", "未知错误")
        qc = bottle_result.get("qc", {})
        print(f"    [FAIL] 瓶身生成失败: {error}")
        if qc.get("failed"):
            for f in qc["failed"]:
                print(f"           - {f.get('msg', f)}")
        result["errors"].append(f"瓶身: {error}")
        return result

    # 2. 提取瓶身的螺纹参数，用于生成配套刷杆
    bottle_neck_od = bottle_params.get("neck_od_mm", 18.0)
    bottle_thread = bottle_params.get("thread", {})
    bottle_pitch = bottle_thread.get("pitch_mm", 2.7)
    bottle_turns = bottle_thread.get("turns", 2)

    # 3. 生成配套刷杆
    # 关键配合：刷杆的内螺纹峰径 ≈ 瓶身的颈外径
    print(f"\n[2] 生成配套刷杆...")

    # 计算配套参数
    thread_depth = bottle_thread.get("depth_mm", 0.5)
    thread_root = bottle_neck_od - 2 * thread_depth  # 螺纹底径

    # 提取 finish 规格
    bottle_finish = bottle_params.get("finish", "18-415")

    wand_params = {
        "thread": {
            "enabled": True,
            "crest_dia_mm": bottle_neck_od,  # 关键：峰径=瓶颈外径
            "pitch_mm": bottle_pitch,        # 螺距必须一致
            "turns": bottle_turns,           # 圈数一致
            "depth_mm": thread_depth,
            "lead_angle_deg": 3.0,
            "segmented": False,
            "gap_angle_deg": 20.0
        },
        "seal_ring": {
            "od_mm": thread_root - 0.5,      # 气密环外径 < 螺纹底径
            "height_mm": 3.0,
            "style": "flat"
        },
        "stem_diameter_mm": 4.0,
        "orifice_mm": 7.0,
        "finish": bottle_finish,  # 规格标注
    }

    print(f"    刷杆参数: crest_dia={wand_params['thread']['crest_dia_mm']}mm, "
          f"pitch={wand_params['thread']['pitch_mm']}mm, "
          f"turns={wand_params['thread']['turns']}, "
          f"seal_ring_od={wand_params['seal_ring']['od_mm']:.1f}mm")

    wand_comp = WandComponent()
    wand_result = wand_comp.generate(
        user_params=wand_params,
        outroot="artifacts/test_assembly"
    )

    if wand_result["ok"]:
        print(f"    [OK] 刷杆生成成功")
        result["wand_ok"] = True
        result["wand_step"] = wand_result.get("step")
    else:
        error = wand_result.get("error", "未知错误")
        qc = wand_result.get("qc", {})
        print(f"    [FAIL] 刷杆生成失败: {error}")
        # 打印失败的规则检查
        for check in qc.get("checks", []):
            if not check.get("ok"):
                print(f"           - 规则 '{check.get('id')}' 失败")
        result["errors"].append(f"刷杆: {error}")
        return result

    # 4. 验证参数匹配
    print(f"\n[3] 验证装配参数...")
    matches = []
    mismatches = []

    # 检查峰径 vs 颈外径
    if abs(wand_params["thread"]["crest_dia_mm"] - bottle_neck_od) < 0.5:
        matches.append(f"螺纹峰径匹配: {wand_params['thread']['crest_dia_mm']} ≈ {bottle_neck_od}")
    else:
        mismatches.append(f"螺纹峰径不匹配: {wand_params['thread']['crest_dia_mm']} vs {bottle_neck_od}")

    # 检查螺距
    if wand_params["thread"]["pitch_mm"] == bottle_pitch:
        matches.append(f"螺距匹配: {wand_params['thread']['pitch_mm']} = {bottle_pitch}")
    else:
        mismatches.append(f"螺距不匹配: {wand_params['thread']['pitch_mm']} vs {bottle_pitch}")

    # 检查圈数
    if wand_params["thread"]["turns"] == bottle_turns:
        matches.append(f"圈数匹配: {wand_params['thread']['turns']} = {bottle_turns}")
    else:
        mismatches.append(f"圈数不匹配: {wand_params['thread']['turns']} vs {bottle_turns}")

    for m in matches:
        print(f"    [OK] {m}")
    for m in mismatches:
        print(f"    [FAIL] {m}")

    result["params_match"] = len(mismatches) == 0
    result["matches"] = matches
    result["mismatches"] = mismatches

    # 总结
    if result["bottle_ok"] and result["wand_ok"] and result["params_match"]:
        print(f"\n    === 装配测试通过 ===")
    else:
        print(f"\n    === 装配测试失败 ===")

    return result


def main():
    print("="*60)
    print("瓶身 + 刷杆 真实装配测试")
    print("="*60)

    # 测试用例：不同尺寸的瓶身
    test_cases = [
        # 标准 18-415 规格
        {
            "name": "标准 18-415 (18mm颈外径)",
            "params": {
                "neck_od_mm": 18.0,
                "height_mm": 70.0,
                "body_od_mm": 20.0,
                "neck_height_mm": 10.0,
                "lip_thickness_mm": 1.0,
                "shoulder_height_mm": 8.0,
                "inner_depth_mm": 55.0,
                "wall_thickness_mm": 1.2,
                "bottom_thickness_mm": 2.0,
                "capacity_ml": 5.0,
                "full_capacity_ml": 6.0,
                "thread": {
                    "enabled": True,
                    "pitch_mm": 2.7,
                    "turns": 2,
                    "depth_mm": 0.5,
                    "lead_angle_deg": 3.0,
                    "segmented": False,
                    "gap_angle_deg": 20.0
                },
                "finish": "18-415"
            }
        },
        # 20-410 规格
        {
            "name": "20-410 (20mm颈外径)",
            "params": {
                "neck_od_mm": 20.0,
                "height_mm": 75.0,
                "body_od_mm": 24.0,
                "neck_height_mm": 10.0,
                "lip_thickness_mm": 1.2,
                "shoulder_height_mm": 10.0,
                "inner_depth_mm": 58.0,
                "wall_thickness_mm": 1.5,
                "bottom_thickness_mm": 2.5,
                "capacity_ml": 7.0,
                "full_capacity_ml": 8.5,
                "thread": {
                    "enabled": True,
                    "pitch_mm": 2.7,
                    "turns": 2,
                    "depth_mm": 0.5,
                    "lead_angle_deg": 3.0,
                    "segmented": False,
                    "gap_angle_deg": 20.0
                },
                "finish": "20-410"
            }
        },
        # 小号 15mm 规格
        {
            "name": "小号 15mm 颈外径",
            "params": {
                "neck_od_mm": 15.0,
                "height_mm": 60.0,
                "body_od_mm": 18.0,
                "neck_height_mm": 8.0,
                "lip_thickness_mm": 1.0,
                "shoulder_height_mm": 6.0,
                "inner_depth_mm": 45.0,
                "wall_thickness_mm": 1.2,
                "bottom_thickness_mm": 2.0,
                "capacity_ml": 3.5,
                "full_capacity_ml": 4.5,
                "thread": {
                    "enabled": True,
                    "pitch_mm": 2.5,
                    "turns": 2,
                    "depth_mm": 0.4,
                    "lead_angle_deg": 3.0,
                    "segmented": False,
                    "gap_angle_deg": 20.0
                },
                "finish": "15-415"
            }
        },
        # 24-410 大号规格
        {
            "name": "24-410 (24mm颈外径)",
            "params": {
                "neck_od_mm": 24.0,
                "height_mm": 85.0,
                "body_od_mm": 28.0,
                "neck_height_mm": 12.0,
                "lip_thickness_mm": 1.5,
                "shoulder_height_mm": 12.0,
                "inner_depth_mm": 65.0,
                "wall_thickness_mm": 1.8,
                "bottom_thickness_mm": 3.0,
                "capacity_ml": 10.0,
                "full_capacity_ml": 12.0,
                "thread": {
                    "enabled": True,
                    "pitch_mm": 2.7,
                    "turns": 2,
                    "depth_mm": 0.6,
                    "lead_angle_deg": 3.0,
                    "segmented": False,
                    "gap_angle_deg": 20.0
                },
                "finish": "24-410"
            }
        },
        # 不同螺距 (3.0mm)
        {
            "name": "18mm 大螺距 (3.0mm pitch)",
            "params": {
                "neck_od_mm": 18.0,
                "height_mm": 70.0,
                "body_od_mm": 20.0,
                "neck_height_mm": 12.0,  # 加高以容纳更大螺距
                "lip_thickness_mm": 1.0,
                "shoulder_height_mm": 8.0,
                "inner_depth_mm": 50.0,
                "wall_thickness_mm": 1.2,
                "bottom_thickness_mm": 2.0,
                "capacity_ml": 4.5,
                "full_capacity_ml": 5.5,
                "thread": {
                    "enabled": True,
                    "pitch_mm": 3.0,
                    "turns": 2,
                    "depth_mm": 0.5,
                    "lead_angle_deg": 3.0,
                    "segmented": False,
                    "gap_angle_deg": 20.0
                },
                "finish": "18-415"
            }
        },
    ]

    results = []
    passed = 0
    failed = 0

    for tc in test_cases:
        result = test_single_assembly(tc["params"], tc["name"])
        results.append(result)

        if result["bottle_ok"] and result["wand_ok"] and result["params_match"]:
            passed += 1
        else:
            failed += 1

    # 打印汇总表格
    print("\n")
    print("="*70)
    print("测试结果汇总")
    print("="*70)
    print(f"{'测试名称':<30} {'瓶身':<8} {'刷杆':<8} {'参数匹配':<10} {'结果':<8}")
    print("-"*70)

    for r in results:
        bottle_status = "OK" if r["bottle_ok"] else "FAIL"
        wand_status = "OK" if r["wand_ok"] else "FAIL"
        match_status = "OK" if r["params_match"] else "FAIL"
        overall = "通过" if (r["bottle_ok"] and r["wand_ok"] and r["params_match"]) else "失败"
        print(f"{r['name']:<30} {bottle_status:<8} {wand_status:<8} {match_status:<10} {overall:<8}")

    print("-"*70)
    print(f"总计: {passed} 通过, {failed} 失败")
    print("="*70)

    if failed > 0:
        print("\n失败详情:")
        for r in results:
            if r["errors"]:
                print(f"  {r['name']}:")
                for e in r["errors"]:
                    print(f"    - {e}")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
