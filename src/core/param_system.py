# -*- coding: utf-8 -*-
"""
参数系统核心框架（Parameter System Core Framework）

本模块定义参数分类系统的核心类和工具函数。
具体的派生规则应放在各产品目录下，如：
  products/lip_gloss/derived_params.py

核心功能：
1. ParamDef - 参数定义（支持核心/派生分类）
2. DerivedRule - 派生规则定义
3. DerivedParamRegistry - 派生参数注册表
4. 工具函数 - 计算派生参数值和动态范围

设计原则：
- 核心参数（is_core=True）：用户指定，系统不自动修改
- 派生参数（is_core=False）：由核心参数自动计算
- 动态范围：派生参数的 min/max 随核心参数变化

作者：AiCad
日期：2024
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ═══════════════════════════════════════════════════════════════════════════
# 核心数据结构
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class DerivedRule:
    """
    派生规则 - 定义派生参数如何从核心参数计算

    Attributes:
        master_param: 主控参数的 key（如 "outer_od_mm"）
        compute_default: 计算默认值的函数 (master_value, all_params) -> default_value
        compute_range: 计算 (min, max) 范围的函数（可选）
        description: 派生规则描述（中文）
    """
    master_param: str
    compute_default: Callable[[float, Dict[str, Any]], float]
    compute_range: Optional[Callable[[float, Dict[str, Any]], Tuple[float, float]]] = None
    description: str = ""


@dataclass
class CrossComponentDerived:
    """
    跨组件派生规则 - 已生成组件约束未生成组件的参数

    当源组件已生成后，目标组件的某些参数将被约束：
    - 范围被限制（compute_range）
    - 默认值被覆盖（compute_default）
    - 可选：变为只读（lock_when_set）

    Attributes:
        source_component: 源组件 ID（已生成的组件）
        source_param: 源参数键
        target_component: 目标组件 ID（待生成的组件）
        target_param: 目标参数键
        compute_range: 计算约束范围 (src_value, src_params) -> (min, max)
        compute_default: 计算约束默认值 (src_value, src_params) -> default
        lock_when_set: 源确定后目标是否变为只读
        description: 约束描述
    """
    source_component: str
    source_param: str
    target_component: str
    target_param: str
    compute_range: Callable[[float, Dict[str, Any]], Tuple[float, float]]
    compute_default: Callable[[float, Dict[str, Any]], float]
    lock_when_set: bool = False
    description: str = ""


@dataclass
class ParamDef:
    """
    参数定义（增强版）

    核心参数 vs 派生参数：
    - is_core=True: 核心参数，用户自由指定，系统不修改
    - is_core=False: 派生参数，由 derived_rule 自动计算

    Attributes:
        k: 参数键（如 "outer_od_mm"）
        name: 显示名称（如 "外径 ⌀OD"）
        unit: 单位（如 "mm"）
        type: 类型（float/int/bool/enum/str）
        default: 默认值
        min: 最小值（静态，用于核心参数）
        max: 最大值（静态，用于核心参数）
        step: 步进值
        choices: 枚举选项列表
        required: 是否必填
        is_core: 是否为核心参数
        derived_rule: 派生规则（仅当 is_core=False 时有效）
        group: 参数分组（用于 UI 显示）
        readonly: 是否只读（派生参数可设为只读）
    """
    k: str
    name: str
    unit: str = ""
    type: str = "float"
    default: Any = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    choices: Optional[List[str]] = None
    required: bool = False
    is_core: bool = True
    derived_rule: Optional[DerivedRule] = None
    group: str = ""
    readonly: bool = False


# ═══════════════════════════════════════════════════════════════════════════
# 派生参数注册表
# ═══════════════════════════════════════════════════════════════════════════

class DerivedParamRegistry:
    """
    派生参数注册表 - 管理所有派生规则

    支持：
    - 按产品/组件注册派生规则
    - 计算派生参数值
    - 计算动态范围
    - 导出规则供前端使用
    """

    def __init__(self) -> None:
        # 结构: {product_id: {component_id: {param_key: DerivedRule}}}
        self._rules: Dict[str, Dict[str, Dict[str, DerivedRule]]] = {}
        self._registered_products: Set[str] = set()

    def register_rules(
        self,
        product_id: str,
        component_id: str,
        rules: Dict[str, DerivedRule]
    ) -> None:
        """
        注册派生规则

        Args:
            product_id: 产品 ID（如 "lip_gloss"）
            component_id: 组件 ID（如 "cap"）
            rules: 派生规则字典 {param_key: DerivedRule}
        """
        if product_id not in self._rules:
            self._rules[product_id] = {}
        self._rules[product_id][component_id] = rules
        self._registered_products.add(product_id)

    def is_product_registered(self, product_id: str) -> bool:
        """检查产品是否已注册"""
        return product_id in self._registered_products

    def get_rule(
        self,
        product_id: str,
        component_id: str,
        param_key: str
    ) -> Optional[DerivedRule]:
        """获取指定参数的派生规则"""
        product_rules = self._rules.get(product_id)
        if not product_rules:
            return None
        component_rules = product_rules.get(component_id)
        if not component_rules:
            return None
        return component_rules.get(param_key)

    def get_component_rules(
        self,
        product_id: str,
        component_id: str
    ) -> Dict[str, DerivedRule]:
        """获取组件的所有派生规则"""
        product_rules = self._rules.get(product_id, {})
        return product_rules.get(component_id, {})

    def compute_derived_value(
        self,
        product_id: str,
        component_id: str,
        param_key: str,
        params: Dict[str, Any]
    ) -> Optional[float]:
        """
        计算派生参数的值

        Args:
            product_id: 产品 ID
            component_id: 组件 ID
            param_key: 参数键
            params: 当前所有参数

        Returns:
            计算出的值，如果无法计算则返回 None
        """
        rule = self.get_rule(product_id, component_id, param_key)
        if not rule:
            return None

        master_value = get_nested_value(params, rule.master_param)
        if master_value is None:
            return None

        try:
            return rule.compute_default(float(master_value), params)
        except Exception:
            return None

    def compute_derived_range(
        self,
        product_id: str,
        component_id: str,
        param_key: str,
        params: Dict[str, Any]
    ) -> Optional[Tuple[float, float]]:
        """
        计算派生参数的动态范围

        Args:
            product_id: 产品 ID
            component_id: 组件 ID
            param_key: 参数键
            params: 当前所有参数

        Returns:
            (min, max) 元组，如果无法计算则返回 None
        """
        rule = self.get_rule(product_id, component_id, param_key)
        if not rule:
            return None
        if rule.compute_range is None:
            return None

        master_value = get_nested_value(params, rule.master_param)
        if master_value is None:
            return None

        try:
            return rule.compute_range(float(master_value), params)
        except Exception:
            return None

    def export_for_frontend(self) -> Dict[str, Any]:
        """
        导出派生规则供前端使用

        Returns:
            前端可用的派生规则配置（不包含函数，只有元数据）
        """
        result: Dict[str, Dict[str, Dict[str, Any]]] = {}

        for product_id, product_rules in self._rules.items():
            result[product_id] = {}
            for component_id, component_rules in product_rules.items():
                result[product_id][component_id] = {}
                for param_key, rule in component_rules.items():
                    result[product_id][component_id][param_key] = {
                        "master": rule.master_param,
                        "desc": rule.description,
                        "has_range": rule.compute_range is not None,
                    }

        return result

    def clear(self) -> None:
        """清空所有规则"""
        self._rules.clear()
        self._registered_products.clear()


# 全局注册表实例
_derived_registry = DerivedParamRegistry()


def get_derived_registry() -> DerivedParamRegistry:
    """获取全局派生参数注册表"""
    return _derived_registry


# ═══════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════

def get_nested_value(d: Dict[str, Any], key: str) -> Any:
    """
    获取嵌套字典中的值

    支持点号分隔的键，如 "thread.pitch_mm"
    """
    parts = key.split(".")
    current: Any = d

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


def param_def_to_dict(pdef: ParamDef) -> Dict[str, Any]:
    """
    将 ParamDef 转换为字典（供前端使用）
    """
    out: Dict[str, Any] = {
        "k": pdef.k,
        "name": pdef.name,
        "unit": pdef.unit,
        "default": pdef.default,
        "type": pdef.type,
        "is_core": pdef.is_core,
        "group": pdef.group,
    }

    if pdef.min is not None:
        out["min"] = pdef.min
    if pdef.max is not None:
        out["max"] = pdef.max
    if pdef.step is not None:
        out["step"] = pdef.step
    if pdef.choices is not None:
        out["choices"] = pdef.choices
    if pdef.required:
        out["required"] = True
    if pdef.readonly:
        out["readonly"] = True

    # 派生规则元数据
    if pdef.derived_rule is not None:
        out["derived_from"] = pdef.derived_rule.master_param
        out["derived_desc"] = pdef.derived_rule.description
        out["derived_type"] = pdef.k

    return out
