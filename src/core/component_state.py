# -*- coding: utf-8 -*-
"""
组件状态管理器（Component State Manager）

管理已生成组件的参数状态，用于跨组件约束传递。

当用户生成一个组件后，该组件的参数被存储到全局状态。
当用户切换到其他组件时，系统根据已生成组件的参数计算约束。

关键特性：
- 任意组件可为首发（多米诺骨牌的第一推力）
- 双向约束：外部定→内部上限锁定；内部定→外部下限锁定
- 多约束区间交集：当多条规则约束同一参数时，取交集

使用流程：
1. 用户生成 cap → set_generated("cap", params)
2. 用户切换到 wand → get_all_constraints_for_component("wand")
3. UI 根据约束显示锁定的参数和受限的范围

作者：AiCad
日期：2026
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.param_system import CrossComponentDerived, get_nested_value


class ComponentStateManager:
    """
    组件状态管理器 - 管理已生成组件的参数

    支持：
    - 存储已生成组件的最终参数
    - 根据跨组件规则计算目标参数的约束
    - 多约束区间交集（多条规则约束同一参数时取交集）
    - 导出约束信息供前端使用
    """

    def __init__(self) -> None:
        self._generated: Dict[str, Dict[str, Any]] = {}
        self._cross_rules: List[CrossComponentDerived] = []

    def set_generated(self, component_id: str, params: Dict[str, Any]) -> None:
        """存储已生成组件的参数"""
        self._generated[component_id] = params.copy()

    def get_generated(self, component_id: str) -> Optional[Dict[str, Any]]:
        """获取已生成组件的参数"""
        return self._generated.get(component_id)

    def is_generated(self, component_id: str) -> bool:
        """检查组件是否已生成"""
        return component_id in self._generated

    def get_all_generated(self) -> Dict[str, Dict[str, Any]]:
        """获取所有已生成组件的参数"""
        return self._generated.copy()

    def clear(self, component_id: Optional[str] = None) -> None:
        """清除已生成状态"""
        if component_id:
            self._generated.pop(component_id, None)
        else:
            self._generated.clear()

    def register_cross_rules(self, rules: List[CrossComponentDerived]) -> None:
        """注册跨组件派生规则"""
        self._cross_rules.extend(rules)

    def get_cross_rules_for_target(
        self, target_component: str
    ) -> List[CrossComponentDerived]:
        """获取影响目标组件的所有跨组件规则"""
        return [r for r in self._cross_rules if r.target_component == target_component]

    def get_all_constraints_for_component(
        self, target_component: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        获取目标组件所有参数的约束（支持区间交集）

        当多条规则约束同一个目标参数时，取所有约束的区间交集：
        - 最终 min = max(所有规则的 min)
        - 最终 max = min(所有规则的 max)
        - 如果交集为空（min > max），标记为不可满足
        - locked = 只要有一条规则 lock_when_set，则锁定

        Returns:
            {param_key: constraint_info} 字典
        """
        # 按目标参数分组收集所有匹配的约束
        param_constraints: Dict[str, List[Dict[str, Any]]] = {}

        for rule in self._cross_rules:
            if rule.target_component != target_component:
                continue

            src_params = self._generated.get(rule.source_component)
            if src_params is None:
                continue

            src_value = get_nested_value(src_params, rule.source_param)
            if src_value is None:
                continue

            try:
                src_float = float(src_value)
                min_val, max_val = rule.compute_range(src_float, src_params)
                default_val = rule.compute_default(src_float, src_params)
            except Exception:
                # finish 等字符串参数特殊处理
                try:
                    default_val = rule.compute_default(src_value, src_params)
                    # 字符串类参数直接返回值，不做区间交集
                    param_constraints.setdefault(rule.target_param, []).append({
                        "constrained_min": None,
                        "constrained_max": None,
                        "constrained_default": default_val,
                        "locked": rule.lock_when_set,
                        "source_component": rule.source_component,
                        "source_param": rule.source_param,
                        "source_value": src_value,
                        "description": rule.description,
                        "is_string": True,
                    })
                    continue
                except Exception:
                    continue

            constraint_info = {
                "constrained_min": min_val,
                "constrained_max": max_val,
                "constrained_default": default_val,
                "locked": rule.lock_when_set,
                "source_component": rule.source_component,
                "source_param": rule.source_param,
                "source_value": src_float,
                "description": rule.description,
                "is_string": False,
            }

            param_constraints.setdefault(rule.target_param, []).append(constraint_info)

        # 合并：对同一参数的多条约束取区间交集
        result: Dict[str, Dict[str, Any]] = {}

        for param_key, constraints in param_constraints.items():
            if len(constraints) == 1:
                # 只有一条规则，直接使用
                c = constraints[0]
                c.pop("is_string", None)
                result[param_key] = c
            else:
                # 多条规则 → 区间交集
                # 检查是否全是字符串类型
                if all(c.get("is_string") for c in constraints):
                    # 字符串约束：取第一个 locked 的
                    for c in constraints:
                        if c["locked"]:
                            c.pop("is_string", None)
                            result[param_key] = c
                            break
                    else:
                        c = constraints[0]
                        c.pop("is_string", None)
                        result[param_key] = c
                    continue

                # 数值约束：区间交集
                numeric = [c for c in constraints if not c.get("is_string")]
                if not numeric:
                    continue

                merged_min = max(c["constrained_min"] for c in numeric)
                merged_max = min(c["constrained_max"] for c in numeric)
                any_locked = any(c["locked"] for c in numeric)

                # 计算合并默认值（取区间中点或最后一条的默认值，夹到交集范围内）
                merged_default = numeric[-1]["constrained_default"]
                if merged_min <= merged_max:
                    # 交集有效：确保 default 在范围内
                    merged_default = max(merged_min, min(merged_max, merged_default))
                    merged_default = round(merged_default, 1)
                # else: 交集为空，保持原值，标记冲突

                # 描述来源
                sources = [f"{c['source_component']}.{c['source_param']}" for c in numeric]

                result[param_key] = {
                    "constrained_min": round(merged_min, 2),
                    "constrained_max": round(merged_max, 2),
                    "constrained_default": merged_default,
                    "locked": any_locked,
                    "source_component": numeric[0]["source_component"],
                    "source_param": numeric[0]["source_param"],
                    "source_value": numeric[0]["source_value"],
                    "description": " | ".join(c["description"] for c in numeric),
                    "conflict": merged_min > merged_max,  # 交集为空 = 冲突
                    "sources": sources,
                }

        return result

    def export_state(self) -> Dict[str, Any]:
        """导出当前状态供前端使用"""
        return {
            "generated": {
                comp_id: {
                    "params": params,
                    "param_count": len(params),
                }
                for comp_id, params in self._generated.items()
            },
            "rules_count": len(self._cross_rules),
        }


# 全局状态管理器实例
_state_manager = ComponentStateManager()


def get_state_manager() -> ComponentStateManager:
    """获取全局组件状态管理器"""
    return _state_manager
