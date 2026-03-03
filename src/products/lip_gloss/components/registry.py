# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .cap import CapComponent
from .bottle import BottleComponent
from .wiper import WiperComponent
from .wand import WandComponent

_CAP = CapComponent()
_BOTTLE = BottleComponent()
_WIPER = WiperComponent()
_WAND = WandComponent()

_PRODUCTS: List[Dict[str, Any]] = [
    {
        "id": "lip_gloss",
        "name": "唇釉瓶",
        "components": [
            {
                **_CAP.schema(),
                "enabled": True,
            },
            {
                **_BOTTLE.schema(),
                "enabled": True,
            },
            {
                **_WIPER.schema(),
                "enabled": True,
            },
            {
                **_WAND.schema(),
                "enabled": True,
            },
        ],
    }
]


def schema() -> Dict[str, Any]:
    """给前端：产品 -> 组件 -> 预设+参数定义"""
    return {"products": _PRODUCTS}


def get_component(product_id: str, component_id: str):
    """给 server/CLI：拿到组件对象"""
    if product_id != "lip_gloss":
        raise KeyError(f"unknown product: {product_id}")
    if component_id == "cap":
        return _CAP
    if component_id == "bottle":
        return _BOTTLE
    if component_id == "wiper":
        return _WIPER
    if component_id == "wand":
        return _WAND
    raise KeyError(f"component not ready: {component_id}")
