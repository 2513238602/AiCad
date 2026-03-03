# -*- coding: utf-8 -*-
"""
配合约束系统 - 核心框架（Fit Constraints Framework）

本模块提供配合约束系统的核心类和工具函数。
具体的约束定义应放在各产品目录下，如：
  products/lip_gloss/constraints.py

核心功能：
1. FitConstraint - 跨组件配合约束基类
2. LinkedParam - 联动参数定义
3. InternalConstraint - 组件内部约束
4. ConstraintRegistry - 约束注册表（管理优先级）
5. 工具函数 - 嵌套字典操作等

设计原则：
- 第一个生成的组件是"锚点"，后续组件必须适配它
- 支持约束优先级，解决多源约束冲突
- 联动约束确保相关参数同步更新

作者：AiCad
日期：2024
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set


# ═══════════════════════════════════════════════════════════════════════════
# 核心数据结构
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LinkedParam:
    """
    联动参数 - 当主参数变化时联动调整

    Attributes:
        param: 目标组件的参数键
        compute: 计算函数 (source_value, target_params) -> new_value
        description: 联动描述
    """
    param: str
    compute: Callable[[float, Dict[str, Any]], float]
    description: str = ""


@dataclass
class FitConstraint:
    """
    跨组件配合约束

    Attributes:
        source_component: 源组件 ID（如 "cap"）
        target_component: 目标组件 ID（如 "wand"）
        source_param: 源参数键（如 "inner_id_mm"）
        target_param: 目标参数键（如 "outer_od_mm"）
        offset: 偏移量（目标值 = 源值 + offset）
        priority: 优先级（数字越大优先级越高，默认 10）
        linked_params: 联动参数列表
        description: 约束描述
    """
    source_component: str
    target_component: str
    source_param: str
    target_param: str
    offset: float = 0.0
    priority: int = 10
    linked_params: Optional[List[LinkedParam]] = None
    description: str = ""


@dataclass
class InternalConstraint:
    """
    组件内部约束 - 参数间的自动调整

    Attributes:
        component: 组件 ID
        trigger_param: 触发参数
        adjust_param: 被调整参数
        compute: 计算函数 (trigger_value, all_params) -> adjusted_value
        description: 约束描述
    """
    component: str
    trigger_param: str
    adjust_param: str
    compute: Callable[[float, Dict[str, Any]], float]
    description: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# 约束注册表
# ═══════════════════════════════════════════════════════════════════════════

class ConstraintRegistry:
    """
    约束注册表 - 管理所有配合约束

    支持：
    - 按产品注册约束
    - 优先级排序
    - 冲突检测和解决
    """

    def __init__(self):
        self._fit_constraints: List[FitConstraint] = []
        self._internal_constraints: List[InternalConstraint] = []
        self._registered_products: Set[str] = set()

    def register_fit_constraint(self, constraint: FitConstraint) -> None:
        """注册一个配合约束"""
        self._fit_constraints.append(constraint)

    def register_fit_constraints(self, constraints: List[FitConstraint]) -> None:
        """批量注册配合约束"""
        self._fit_constraints.extend(constraints)

    def register_internal_constraint(self, constraint: InternalConstraint) -> None:
        """注册一个内部约束"""
        self._internal_constraints.append(constraint)

    def register_internal_constraints(self, constraints: List[InternalConstraint]) -> None:
        """批量注册内部约束"""
        self._internal_constraints.extend(constraints)

    def register_product(self, product_id: str) -> None:
        """标记产品已注册"""
        self._registered_products.add(product_id)

    def is_product_registered(self, product_id: str) -> bool:
        """检查产品是否已注册"""
        return product_id in self._registered_products

    def get_constraints_for_pair(
        self,
        source_component: str,
        target_component: str,
        *,
        sort_by_priority: bool = True
    ) -> List[FitConstraint]:
        """
        获取指定组件对的所有配合约束

        Args:
            source_component: 源组件 ID
            target_component: 目标组件 ID
            sort_by_priority: 是否按优先级排序（高优先级在前）

        Returns:
            适用的约束列表
        """
        constraints = [
            c for c in self._fit_constraints
            if c.source_component == source_component
            and c.target_component == target_component
        ]
        if sort_by_priority:
            constraints.sort(key=lambda c: c.priority, reverse=True)
        return constraints

    def get_best_constraint_for_param(
        self,
        target_component: str,
        target_param: str,
        available_sources: List[str]
    ) -> Optional[FitConstraint]:
        """
        获取目标参数的最佳约束（优先级最高）

        用于解决多源约束冲突：当多个已生成组件都对同一目标参数有约束时，
        选择优先级最高的那个。

        Args:
            target_component: 目标组件 ID
            target_param: 目标参数键
            available_sources: 可用的源组件列表（已生成的组件）

        Returns:
            优先级最高的约束，如果没有则返回 None
        """
        candidates = []
        for c in self._fit_constraints:
            if (c.target_component == target_component
                and c.target_param == target_param
                and c.source_component in available_sources):
                candidates.append(c)

        if not candidates:
            return None

        # 按优先级排序，返回最高的
        candidates.sort(key=lambda c: c.priority, reverse=True)
        return candidates[0]

    def get_internal_constraints(self, component: str) -> List[InternalConstraint]:
        """获取组件的所有内部约束"""
        return [c for c in self._internal_constraints if c.component == component]

    def get_fit_param_keys(self, component: str) -> List[str]:
        """获取组件的配合相关参数键列表"""
        keys = set()
        for c in self._fit_constraints:
            if c.source_component == component:
                keys.add(c.source_param)
            if c.target_component == component:
                keys.add(c.target_param)
                if c.linked_params:
                    for lp in c.linked_params:
                        keys.add(lp.param)
        return sorted(keys)

    def clear(self) -> None:
        """清空所有约束"""
        self._fit_constraints.clear()
        self._internal_constraints.clear()
        self._registered_products.clear()


# 全局注册表实例
_registry = ConstraintRegistry()


def get_registry() -> ConstraintRegistry:
    """获取全局约束注册表"""
    return _registry


# ═══════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════

def get_nested_value(d: Dict[str, Any], key: str) -> Any:
    """
    获取嵌套字典中的值

    支持点号分隔的键，如 "thread.pitch_mm"
    """
    parts = key.split(".")
    current = d

    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None

    return current


def set_nested_value(d: Dict[str, Any], key: str, value: Any) -> None:
    """
    设置嵌套字典中的值

    支持点号分隔的键，如 "thread.pitch_mm"
    自动创建中间字典
    """
    parts = key.split(".")
    current = d

    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]

    current[parts[-1]] = value


# ═══════════════════════════════════════════════════════════════════════════
# 核心函数：应用配合约束
# ═══════════════════════════════════════════════════════════════════════════

def apply_fit_constraints(
    source_component: str,
    source_params: Dict[str, Any],
    target_component: str,
    target_params: Optional[Dict[str, Any]] = None,
    *,
    registry: Optional[ConstraintRegistry] = None
) -> Dict[str, Any]:
    """
    应用配合约束，计算目标组件的参数

    Args:
        source_component: 源组件 ID（锚点组件）
        source_params: 源组件参数（已生成）
        target_component: 目标组件 ID
        target_params: 目标组件当前参数（可选）
        registry: 约束注册表（可选，默认使用全局）

    Returns:
        调整后的目标参数字典
    """
    if registry is None:
        registry = _registry

    result = dict(target_params or {})
    constraints = registry.get_constraints_for_pair(source_component, target_component)

    for constraint in constraints:
        source_value = get_nested_value(source_params, constraint.source_param)
        if source_value is None:
            continue

        target_value = float(source_value) + constraint.offset
        set_nested_value(result, constraint.target_param, target_value)

        if constraint.linked_params:
            for linked in constraint.linked_params:
                linked_value = linked.compute(float(source_value), result)
                set_nested_value(result, linked.param, linked_value)

    return result


def apply_internal_constraints(
    component: str,
    params: Dict[str, Any],
    trigger_param: str,
    *,
    registry: Optional[ConstraintRegistry] = None
) -> Dict[str, Any]:
    """
    应用组件内部约束

    Args:
        component: 组件 ID
        params: 当前参数
        trigger_param: 触发变化的参数
        registry: 约束注册表（可选）

    Returns:
        调整后的参数字典
    """
    if registry is None:
        registry = _registry

    result = dict(params)
    constraints = registry.get_internal_constraints(component)

    for constraint in constraints:
        if constraint.trigger_param != trigger_param:
            continue

        trigger_value = get_nested_value(params, trigger_param)
        if trigger_value is None:
            continue

        adjusted_value = constraint.compute(float(trigger_value), params)
        set_nested_value(result, constraint.adjust_param, adjusted_value)

    return result


def resolve_multi_source_constraints(
    target_component: str,
    target_param: str,
    source_params_map: Dict[str, Dict[str, Any]],
    *,
    registry: Optional[ConstraintRegistry] = None
) -> Optional[float]:
    """
    解决多源约束冲突

    当多个已生成组件都对同一目标参数有约束时，选择优先级最高的。

    Args:
        target_component: 目标组件 ID
        target_param: 目标参数键
        source_params_map: 源组件参数映射 {component_id: params}
        registry: 约束注册表（可选）

    Returns:
        计算出的目标参数值，如果没有约束则返回 None
    """
    if registry is None:
        registry = _registry

    available_sources = list(source_params_map.keys())
    best = registry.get_best_constraint_for_param(
        target_component, target_param, available_sources
    )

    if best is None:
        return None

    source_params = source_params_map.get(best.source_component)
    if source_params is None:
        return None

    source_value = get_nested_value(source_params, best.source_param)
    if source_value is None:
        return None

    return float(source_value) + best.offset


# ═══════════════════════════════════════════════════════════════════════════
# 导出 API
# ═══════════════════════════════════════════════════════════════════════════

def export_constraints_for_frontend(
    registry: Optional[ConstraintRegistry] = None
) -> Dict[str, Any]:
    """
    导出约束配置供前端使用

    Returns:
        前端可用的约束配置 JSON
    """
    if registry is None:
        registry = _registry

    fit_constraints = {}
    internal_constraints = {}
    fit_param_keys = {}

    for c in registry._fit_constraints:
        pair_key = f"{c.source_component}->{c.target_component}"
        if pair_key not in fit_constraints:
            fit_constraints[pair_key] = []

        constraint_dict = {
            "source": c.source_param,
            "target": c.target_param,
            "offset": c.offset,
            "priority": c.priority,
        }
        if c.linked_params:
            constraint_dict["linked"] = [
                {"param": lp.param, "desc": lp.description}
                for lp in c.linked_params
            ]
        fit_constraints[pair_key].append(constraint_dict)

    for c in registry._internal_constraints:
        if c.component not in internal_constraints:
            internal_constraints[c.component] = []
        internal_constraints[c.component].append({
            "trigger": c.trigger_param,
            "adjust": c.adjust_param,
            "desc": c.description,
        })

    for comp in ["cap", "bottle", "wand", "wiper"]:
        fit_param_keys[comp] = registry.get_fit_param_keys(comp)

    return {
        "fit_constraints": fit_constraints,
        "internal_constraints": internal_constraints,
        "fit_param_keys": fit_param_keys,
    }
