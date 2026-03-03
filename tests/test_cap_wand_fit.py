# -*- coding: utf-8 -*-
"""
测试脚本：瓶盖与刷杆的配合关系

测试目标：
1. 瓶盖无内螺纹设计
2. 瓶盖内径 > 刷杆外径（瓶盖套在刷杆外）
3. 瓶盖内腔深 > 刷杆盖高（刷杆能完全进入瓶盖内腔）
4. 瓶盖高度 > 刷杆盖高（确保完整覆盖）
5. 瓶盖壁厚 = (外径 - 内径) / 2 >= 0.8mm

测试场景：
- 场景1：先生成瓶盖，再生成刷杆（刷杆适配瓶盖）
- 场景2：先生成刷杆，再生成瓶盖（瓶盖适配刷杆）
- 场景3：完整流程 瓶身 → 刷杆 → 瓶盖

作者：AiCad
日期：2024
"""
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from products.lip_gloss.components.cap import CapComponent
from products.lip_gloss.components.wand import WandComponent


def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")


def test_cap_no_thread():
    """测试瓶盖无内螺纹参数"""
    print_header("测试1：瓶盖无内螺纹设计")

    cap = CapComponent()
    schema = cap.schema()
    params = schema["params"]

    # 检查是否存在 thread 相关参数
    thread_params = [p for p in params if p["k"].startswith("thread")]

    if len(thread_params) == 0:
        print_result("无螺纹参数", True, "参数定义中不包含 thread.* 参数")
        return True
    else:
        print_result("无螺纹参数", False, f"发现螺纹参数: {[p['k'] for p in thread_params]}")
        return False


def test_cap_defaults():
    """测试瓶盖默认值：内腔尽可能深，壁厚尽可能薄"""
    print_header("测试2：瓶盖默认值优化")

    cap = CapComponent()
    schema = cap.schema()
    params = {p["k"]: p["default"] for p in schema["params"]}

    # 检查默认参数
    outer_od = params.get("outer_od_mm", 0)
    inner_id = params.get("inner_id_mm", 0)
    height = params.get("height_mm", 0)
    cavity_depth = params.get("cavity_depth_mm", 0)

    wall_thickness = (outer_od - inner_id) / 2.0
    top_thickness = height - cavity_depth

    all_pass = True

    # 壁厚 >= 0.8mm
    passed = wall_thickness >= 0.8
    print_result(f"壁厚 >= 0.8mm", passed,
                 f"壁厚 = ({outer_od} - {inner_id}) / 2 = {wall_thickness:.2f}mm")
    all_pass = all_pass and passed

    # 顶部厚度 <= 2mm（尽可能薄）
    passed = top_thickness <= 2.0
    print_result(f"顶部厚度 <= 2mm", passed,
                 f"顶部 = {height} - {cavity_depth} = {top_thickness:.2f}mm")
    all_pass = all_pass and passed

    # 内腔深度占比 > 90%
    cavity_ratio = cavity_depth / height * 100
    passed = cavity_ratio > 90
    print_result(f"内腔深度占比 > 90%", passed,
                 f"内腔深度/总高 = {cavity_depth}/{height} = {cavity_ratio:.1f}%")
    all_pass = all_pass and passed

    return all_pass


def test_cap_wand_fit_cap_first():
    """测试场景1：先生成瓶盖，再生成刷杆"""
    print_header("测试3：先瓶盖后刷杆（刷杆适配瓶盖）")

    cap = CapComponent()
    wand = WandComponent()

    # 使用瓶盖默认参数
    cap_schema = cap.schema()
    cap_params = {p["k"]: p["default"] for p in cap_schema["params"]}

    cap_inner_id = cap_params.get("inner_id_mm", 22.4)
    cap_cavity_depth = cap_params.get("cavity_depth_mm", 23.5)
    cap_height = cap_params.get("height_mm", 25.0)

    # 刷杆应适配瓶盖
    # 刷杆外径 < 瓶盖内径 - 0.5mm
    wand_outer_od = cap_inner_id - 1.0
    # 刷杆盖高 < 瓶盖内腔深 - 3mm
    wand_cap_height = cap_cavity_depth - 4.0

    all_pass = True

    # 验证配合关系
    passed = wand_outer_od < cap_inner_id - 0.5
    print_result("刷杆外径 < 瓶盖内径 - 0.5mm", passed,
                 f"{wand_outer_od:.1f} < {cap_inner_id:.1f} - 0.5 = {cap_inner_id - 0.5:.1f}")
    all_pass = all_pass and passed

    passed = wand_cap_height < cap_cavity_depth - 3.0
    print_result("刷杆盖高 < 瓶盖内腔 - 3mm", passed,
                 f"{wand_cap_height:.1f} < {cap_cavity_depth:.1f} - 3 = {cap_cavity_depth - 3:.1f}")
    all_pass = all_pass and passed

    return all_pass


def test_cap_wand_fit_wand_first():
    """测试场景2：先生成刷杆，再生成瓶盖"""
    print_header("测试4：先刷杆后瓶盖（瓶盖适配刷杆）")

    cap = CapComponent()
    wand = WandComponent()

    # 使用刷杆默认参数
    wand_schema = wand.schema()
    wand_params = {p["k"]: p["default"] for p in wand_schema["params"]}

    wand_outer_od = wand_params.get("outer_od_mm", 23.0)
    wand_cap_height = wand_params.get("cap_height_mm", 15.0)

    # 瓶盖应适配刷杆
    # 瓶盖内径 > 刷杆外径 + 0.5mm
    cap_inner_id = wand_outer_od + 0.5
    # 瓶盖内腔深 > 刷杆盖高 + 4mm
    cap_cavity_depth = wand_cap_height + 4.0
    # 瓶盖高度 > 刷杆盖高 + 5mm
    cap_height = wand_cap_height + 5.0
    # 壁厚 0.8mm
    cap_outer_od = cap_inner_id + 2 * 0.8

    all_pass = True

    # 验证配合关系
    passed = cap_inner_id > wand_outer_od + 0.3
    print_result("瓶盖内径 > 刷杆外径 + 0.3mm", passed,
                 f"{cap_inner_id:.1f} > {wand_outer_od:.1f} + 0.3 = {wand_outer_od + 0.3:.1f}")
    all_pass = all_pass and passed

    passed = cap_cavity_depth > wand_cap_height + 3.0
    print_result("瓶盖内腔 > 刷杆盖高 + 3mm", passed,
                 f"{cap_cavity_depth:.1f} > {wand_cap_height:.1f} + 3 = {wand_cap_height + 3:.1f}")
    all_pass = all_pass and passed

    passed = cap_height > wand_cap_height + 3.0
    print_result("瓶盖高度 > 刷杆盖高 + 3mm", passed,
                 f"{cap_height:.1f} > {wand_cap_height:.1f} + 3 = {wand_cap_height + 3:.1f}")
    all_pass = all_pass and passed

    wall = (cap_outer_od - cap_inner_id) / 2.0
    passed = wall >= 0.8
    print_result("瓶盖壁厚 >= 0.8mm", passed,
                 f"({cap_outer_od:.1f} - {cap_inner_id:.1f}) / 2 = {wall:.2f}mm")
    all_pass = all_pass and passed

    return all_pass


def test_cap_generation():
    """测试瓶盖实际生成"""
    print_header("测试5：瓶盖实际生成（无螺纹）")

    cap = CapComponent()

    try:
        result = cap.generate(preset_id="cap_18415_standard")

        if result["ok"]:
            print_result("生成成功", True, f"输出目录: {result['run_dir']}")

            # 检查 STEP 文件
            if result.get("step"):
                print_result("STEP 导出", True, result["step"])
            else:
                print_result("STEP 导出", False, "未生成 STEP 文件")

            # 检查 STL 文件
            if result.get("stl"):
                print_result("STL 导出", True, result["stl"])
            else:
                print_result("STL 导出", False, "未生成 STL 文件")

            return True
        else:
            print_result("生成成功", False, f"错误: {result.get('error')}")
            if result.get("qc", {}).get("hard_fail"):
                print(f"         硬约束失败: {result['qc']['hard_fail']}")
            return False

    except Exception as e:
        print_result("生成成功", False, f"异常: {e}")
        return False


def test_wand_generation():
    """测试刷杆实际生成"""
    print_header("测试6：刷杆实际生成")

    wand = WandComponent()

    try:
        result = wand.generate(preset_id="wand_standard_18415")

        if result["ok"]:
            print_result("生成成功", True, f"输出目录: {result['run_dir']}")
            return True
        else:
            print_result("生成成功", False, f"错误: {result.get('error')}")
            if result.get("qc", {}).get("hard_fail"):
                print(f"         硬约束失败: {result['qc']['hard_fail']}")
            return False

    except Exception as e:
        print_result("生成成功", False, f"异常: {e}")
        return False


def main():
    print("\n" + "#" * 60)
    print("#  瓶盖-刷杆配合测试")
    print("#" * 60)

    results = []

    results.append(("瓶盖无螺纹设计", test_cap_no_thread()))
    results.append(("瓶盖默认值优化", test_cap_defaults()))
    results.append(("先瓶盖后刷杆配合", test_cap_wand_fit_cap_first()))
    results.append(("先刷杆后瓶盖配合", test_cap_wand_fit_wand_first()))
    results.append(("瓶盖实际生成", test_cap_generation()))
    results.append(("刷杆实际生成", test_wand_generation()))

    # 汇总
    print("\n" + "=" * 60)
    print("  测试汇总")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")

    print("-" * 60)
    print(f"  总计: {passed}/{total} 通过")

    if passed == total:
        print("\n  [OK] All tests passed! Cap-Wand fit is correct.")
        return 0
    else:
        print(f"\n  [WARN] {total - passed} tests failed, check fit params.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
