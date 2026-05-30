# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import sys


def _json_load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    # CadQuery solids/workplanes are useful internally but not printable JSON.
    return f"<{value.__class__.__name__}>"


def main():
    ap = argparse.ArgumentParser("CADMVP generic generator")
    ap.add_argument("--product", default="lip_gloss")
    ap.add_argument("--component", default="cap")
    ap.add_argument("--preset", default=None)
    ap.add_argument("--params", default=None, help='JSON string, e.g. {"outer_od_mm":28}')
    ap.add_argument("--params-json", default=None, help="path to json file")
    ap.add_argument("--outroot", default="artifacts/webui")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))

    from products.lip_gloss.components.registry import get_component

    params: Dict[str, Any] = {}
    if args.params_json:
        params.update(_json_load(Path(args.params_json)))
    if args.params:
        params.update(json.loads(args.params))

    comp = get_component(args.product, args.component)
    res = comp.generate(preset_id=args.preset, user_params=params, outroot=args.outroot, title=args.title)

    print(json.dumps(_json_safe(res), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
