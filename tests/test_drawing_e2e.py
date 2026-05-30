#!/usr/bin/env python3
"""端到端测试：验证四个组件工程图 SVG 生成。"""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def get_defaults(comp_cls):
    s = comp_cls().schema()
    d = {}
    for p in s['params']:
        val = p['default']
        # 跳过 dict/list 类型的默认值（如 preset），只保留标量参数
        if not isinstance(val, (dict, list)):
            d[p['k']] = val
    return d


def check_svg(label, content):
    checks = {
        "hatch_pattern": '<pattern id="hatch"' in content,
        "hatch_fill": 'url(#hatch)' in content,
        "solid_arrow": '<polygon points=' in content and 'fill="black"' in content,
        "centerline_dash": '10,2,2,2' in content,
        "hidden_dash": '4,2' in content,
        "section_label_A": '>A<' in content,
        "title_grid": '图号' in content and '材料' in content,
        "no_param_table": '关键参数' not in content,
    }
    all_ok = True
    for name, ok in checks.items():
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  [{status}] {label} — {name}")
    return all_ok


def main():
    from products.lip_gloss.components.cap import CapComponent
    from products.lip_gloss.components.bottle import BottleComponent
    from products.lip_gloss.components.wand import WandComponent
    from products.lip_gloss.components.wiper import WiperComponent

    components = [
        ("Cap", CapComponent),
        ("Bottle", BottleComponent),
        ("Wand", WandComponent),
        ("Wiper", WiperComponent),
    ]

    tmpdir = tempfile.mkdtemp(prefix="drawing_e2e_")
    results = []

    for label, cls in components:
        print(f"\n=== {label} ===")
        params = get_defaults(cls)
        run_dir = os.path.join(tmpdir, label.lower())
        os.makedirs(run_dir, exist_ok=True)

        try:
            result = cls().generate(user_params=params, outroot=run_dir)
            ok = result.get("ok", False)
            print(f"  generate ok={ok}")
            if not ok and "error" in result:
                print(f"  error: {result['error']}")

            svg_path = result.get("svg")
            if svg_path and Path(svg_path).exists():
                content = Path(svg_path).read_text(encoding="utf-8")
                sz = len(content)
                print(f"  SVG size={sz} bytes")
                passed = check_svg(label, content)
                results.append(passed)
            else:
                print(f"  [FAIL] SVG not found: {svg_path}")
                results.append(False)
        except Exception as e:
            import traceback
            print(f"  [ERROR] {e}")
            traceback.print_exc()
            results.append(False)

    print(f"\n{'='*50}")
    all_pass = all(results)
    for (label, _), passed in zip(components, results):
        print(f"  [{('PASS' if passed else 'FAIL')}] {label}")
    print(f"\n  {'ALL PASS' if all_pass else 'SOME FAILED'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
