# -*- coding: utf-8 -*-
"""3D 参数句柄定义 — 为前端拖拽编辑提供句柄位置和绑定参数信息。

句柄坐标采用 CadQuery 坐标系（Z-up），前端在渲染时统一旋转 -90° 对齐 Three.js（Y-up）。
"""
from __future__ import annotations


def compute_drag_handles(component_id: str, params: dict) -> list[dict]:
    """根据组件类型和当前参数值，计算可拖拽句柄列表。

    每个句柄绑定一个核心参数，指定位置、方向、值域和预览变形轴。
    """
    fn = _HANDLE_FNS.get(component_id)
    if fn is None:
        return []
    return fn(params)


# ── 各组件句柄定义 ──────────────────────────────────────────


def _cap_handles(p: dict) -> list[dict]:
    od = p.get("outer_od_mm", 25)
    h = p.get("height_mm", 30)
    return [
        {
            "id": "cap_height",
            "paramKey": "height_mm",
            "position": [0, 0, h],
            "axis": [0, 0, 1],
            "color": 0xEF4444,
            "min": 10,
            "max": 80,
            "currentValue": h,
            "scaleAxis": "z",
        },
        {
            "id": "cap_od",
            "paramKey": "outer_od_mm",
            "position": [od / 2, 0, h / 2],
            "axis": [1, 0, 0],
            "color": 0x3B82F6,
            "min": 12,
            "max": 50,
            "currentValue": od,
            "scaleAxis": "xy",
        },
    ]


def _bottle_handles(p: dict) -> list[dict]:
    od = p.get("body_od_mm", 22)
    h = p.get("height_mm", 70)
    return [
        {
            "id": "bottle_height",
            "paramKey": "height_mm",
            "position": [0, 0, h],
            "axis": [0, 0, 1],
            "color": 0xEF4444,
            "min": 30,
            "max": 120,
            "currentValue": h,
            "scaleAxis": "z",
        },
        {
            "id": "bottle_od",
            "paramKey": "body_od_mm",
            "position": [od / 2, 0, h / 2],
            "axis": [1, 0, 0],
            "color": 0x3B82F6,
            "min": 12,
            "max": 60,
            "currentValue": od,
            "scaleAxis": "xy",
        },
    ]


def _wand_handles(p: dict) -> list[dict]:
    od = p.get("outer_od_mm", 18)
    h = p.get("total_height_mm", 110)
    cap_h = p.get("cap_height_mm", 15)
    return [
        {
            "id": "wand_height",
            "paramKey": "total_height_mm",
            "position": [0, 0, 0],
            "axis": [0, 0, -1],
            "color": 0xEF4444,
            "min": 60,
            "max": 200,
            "currentValue": h,
            "scaleAxis": "z",
        },
        {
            "id": "wand_od",
            "paramKey": "outer_od_mm",
            "position": [od / 2, 0, cap_h / 2],
            "axis": [1, 0, 0],
            "color": 0x3B82F6,
            "min": 10,
            "max": 40,
            "currentValue": od,
            "scaleAxis": "xy",
        },
    ]


def _wiper_handles(p: dict) -> list[dict]:
    od = p.get("outer_od_mm", 18)
    h = p.get("height_mm", 8)
    return [
        {
            "id": "wiper_height",
            "paramKey": "height_mm",
            "position": [0, 0, h],
            "axis": [0, 0, 1],
            "color": 0xEF4444,
            "min": 3,
            "max": 20,
            "currentValue": h,
            "scaleAxis": "z",
        },
        {
            "id": "wiper_od",
            "paramKey": "outer_od_mm",
            "position": [od / 2, 0, h / 2],
            "axis": [1, 0, 0],
            "color": 0x3B82F6,
            "min": 8,
            "max": 40,
            "currentValue": od,
            "scaleAxis": "xy",
        },
    ]


_HANDLE_FNS = {
    "cap": _cap_handles,
    "bottle": _bottle_handles,
    "wand": _wand_handles,
    "wiper": _wiper_handles,
}
