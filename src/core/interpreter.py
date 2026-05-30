# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional, Callable


def _flatten(d: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (d or {}).items():
        kk = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten(v, kk))
        else:
            out[kk] = v
    return out


def _set_path(dst: Dict[str, Any], path: str, value: Any) -> None:
    cur = dst
    parts = path.split(".")
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value


@dataclass(frozen=True)
class Rule:
    """
    组件级硬/软约束（跨字段）。
    - fn(params) -> bool
    - data_fn(params) -> dict (可选，用于错误回显)
    """
    id: str
    severity: str  # "hard" / "soft"
    msg: str
    fn: Callable[[Dict[str, Any]], bool]
    data_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None


class Interpreter:
    """
    严格解释器（Strict）
    目标：
    - dot-path 参数（thread.pitch_mm）与 nested dict（{"thread": {...}}）统一处理
    - 类型转换：float/int/bool/enum/str
    - 校验：min/max/choices/required + 组件跨字段规则
    重要：不做 clamp、不做“自动修正”，发现打架直接 fail（hard）。
    """

    def normalize_strict(
        self,
        param_defs: List[Dict[str, Any]],
        preset_params: Dict[str, Any] | None,
        user_params: Dict[str, Any] | None,
        *,
        rules: List[Rule] | None = None,
        accept_legacy_keys: Dict[str, str] | None = None,
        allow_unknown_keys: bool = False,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        """
        returns: (nested_params, flat_params, qc)
        qc = { ok, checks, params, flat }
        """
        preset_flat = _flatten(preset_params or {})
        user_flat = _flatten(user_params or {})

        # legacy mapping（旧字段 -> 新字段）
        if accept_legacy_keys:
            for oldk, newk in accept_legacy_keys.items():
                if oldk in user_flat and newk not in user_flat:
                    user_flat[newk] = user_flat[oldk]

        defs_by_k: Dict[str, Dict[str, Any]] = {d["k"]: d for d in (param_defs or [])}

        checks: List[Dict[str, Any]] = []

        def add(cid: str, ok: bool, severity: str, msg: str, data: Optional[Dict[str, Any]] = None) -> None:
            checks.append({"id": cid, "ok": bool(ok), "severity": severity, "msg": msg, "data": data or {}})

        # unknown keys
        if not allow_unknown_keys:
            for k in user_flat.keys():
                if k.startswith("_render_"):
                    continue  # 渲染元数据，非 CAD 参数，跳过校验
                if k not in defs_by_k:
                    add("unknown_param:" + k, False, "hard", "未知参数（前端/调用方传了 schema 不支持的字段）", {"k": k})

        flat_out: Dict[str, Any] = {}
        nested_out: Dict[str, Any] = {}

        for k, d in defs_by_k.items():
            typ = d.get("type", "float")
            required = bool(d.get("required", False))

            if k in user_flat:
                raw = user_flat[k]
            elif k in preset_flat:
                raw = preset_flat[k]
            else:
                raw = d.get("default", None)

            if raw is None:
                if required:
                    add("missing:" + k, False, "hard", "缺少必填参数", {"k": k})
                continue

            # cast
            try:
                if typ == "float":
                    v = float(raw)
                elif typ == "int":
                    v = int(float(raw))
                elif typ == "bool":
                    if isinstance(raw, bool):
                        v = raw
                    elif isinstance(raw, (int, float)):
                        v = bool(raw)
                    else:
                        s = str(raw).strip().lower()
                        v = s in ("1", "true", "yes", "y", "on")
                elif typ == "enum":
                    v = str(raw)
                else:  # str
                    v = "" if raw is None else str(raw)
            except Exception as e:
                add("cast:" + k, False, "hard", "类型转换失败", {"k": k, "raw": raw, "type": typ, "err": repr(e)})
                continue

            # enum check
            if typ == "enum":
                choices = d.get("choices") or []
                if choices and v not in choices:
                    add("enum:" + k, False, "hard", "枚举值不在可选范围", {"k": k, "v": v, "choices": choices})
                    continue

            # range check（不 clamp，只报错）
            # 派生参数（有 derived_from 标记）跳过静态范围检查，
            # 其合理性由 cross-field rules 保证（如 cavity_in_height）
            if typ in ("float", "int") and isinstance(v, (int, float)) and "derived_from" not in d:
                if "min" in d and v < float(d["min"]):
                    add("min:" + k, False, "hard", "小于最小值", {"k": k, "v": v, "min": d["min"]})
                if "max" in d and v > float(d["max"]):
                    add("max:" + k, False, "hard", "大于最大值", {"k": k, "v": v, "max": d["max"]})

            flat_out[k] = v
            _set_path(nested_out, k, v)

        # apply component cross-field rules
        for r in (rules or []):
            ok = False
            try:
                ok = bool(r.fn(nested_out))
            except Exception as e:
                add("rule_exc:" + r.id, False, "hard", "规则执行异常（请检查规则实现）", {"rule": r.id, "err": repr(e)})
                continue

            data = {}
            if r.data_fn:
                try:
                    data = r.data_fn(nested_out) or {}
                except Exception:
                    data = {}

            add(r.id, ok, r.severity, r.msg, data)

        # 透传 _render_* 渲染元数据到输出（不参与 CAD 校验，但需传给前端）
        for k, v in user_flat.items():
            if k.startswith("_render_"):
                flat_out[k] = v
                nested_out[k] = v

        ok_all = all(c["ok"] for c in checks if c["severity"] == "hard")
        qc = {"ok": ok_all, "checks": checks, "params": nested_out, "flat": flat_out}
        return nested_out, flat_out, qc
