import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import type { CrossConstraintMap } from '@/api/types'
import { setNested, getNested, deleteNested } from '@/utils/nested'
import { dlog } from '@/utils/debugLog'

export const useParamsStore = defineStore('params', () => {
  // The actual parameter values (nested structure)
  const values = reactive<Record<string, any>>({})

  // Cross-component constraints from backend
  const crossConstraints = ref<CrossConstraintMap>({})

  /**
   * Set a single parameter value by dotted key.
   */
  function setParam(key: string, val: any) {
    setNested(values, key, val)
  }

  /**
   * Get a single parameter value by dotted key.
   */
  function getParam(key: string, fallback?: any): any {
    return getNested(values, key, fallback)
  }

  /**
   * Delete a parameter by dotted key.
   */
  function removeParam(key: string) {
    deleteNested(values, key)
  }

  /**
   * Reset all params from a preset's params object.
   */
  function setFromPreset(presetParams: Record<string, any> | undefined) {
    // Clear all existing
    for (const k of Object.keys(values)) {
      delete values[k]
    }
    if (!presetParams) return
    for (const [k, v] of Object.entries(presetParams)) {
      if (k.includes('.')) {
        setNested(values, k, v)
      } else {
        values[k] = v
      }
    }
  }

  /**
   * Bulk set params from an object (e.g., JSON import).
   */
  function setAll(obj: Record<string, any>) {
    for (const k of Object.keys(values)) {
      delete values[k]
    }
    Object.assign(values, JSON.parse(JSON.stringify(obj)))
  }

  /**
   * Set cross-component constraints.
   */
  function setCrossConstraints(constraints: CrossConstraintMap) {
    crossConstraints.value = constraints
  }

  /**
   * Apply cross-component constraints to current params:
   * - Locked params are set to constrained_default
   * - Unclamped params are clamped to range
   */
  function applyCrossConstraints() {
    dlog.constraint('=== applyCrossConstraints 开始 ===', {
      constraintCount: Object.keys(crossConstraints.value).length,
    })
    for (const [paramKey, constraint] of Object.entries(crossConstraints.value)) {
      const oldVal = getNested(values, paramKey, undefined)
      const cMin = constraint.constrained_min
      const cMax = constraint.constrained_max

      // 检测范围冲突
      if (cMin != null && cMax != null && cMin > cMax) {
        dlog.warn(`约束范围冲突: ${paramKey} min=${cMin} > max=${cMax}`, {
          paramKey,
          constraint,
          currentValue: oldVal,
          source: `${constraint.source_component}.${constraint.source_param}=${constraint.source_value}`,
        })
      }

      if (constraint.locked) {
        setNested(values, paramKey, constraint.constrained_default)
        dlog.constraint(`${paramKey}: 锁定 → ${constraint.constrained_default}`, {
          oldVal,
          source: `${constraint.source_component}.${constraint.source_param}`,
        })
      } else {
        const cur = getNested(values, paramKey, null)
        if (cur === null || cur === undefined) {
          setNested(values, paramKey, constraint.constrained_default)
          dlog.constraint(`${paramKey}: 无值 → 默认 ${constraint.constrained_default}`, {
            range: `[${cMin}, ${cMax}]`,
          })
        } else if (typeof cur === 'number') {
          if (cMin !== undefined && cMin !== null && cur < cMin) {
            setNested(values, paramKey, cMin)
            dlog.constraint(`${paramKey}: ${cur} < min(${cMin}) → 夹到 ${cMin}`, {
              range: `[${cMin}, ${cMax}]`,
              source: `${constraint.source_component}.${constraint.source_param}`,
            })
          } else if (cMax !== undefined && cMax !== null && cur > cMax) {
            setNested(values, paramKey, cMax)
            dlog.constraint(`${paramKey}: ${cur} > max(${cMax}) → 夹到 ${cMax}`, {
              range: `[${cMin}, ${cMax}]`,
              source: `${constraint.source_component}.${constraint.source_param}`,
            })
          } else {
            dlog.constraint(`${paramKey}: ${cur} 在范围内 [${cMin}, ${cMax}]`)
          }
        }
      }
    }
    dlog.constraint('=== applyCrossConstraints 结束 ===')
  }

  /**
   * Auto-fix cross-constraint violations before generate.
   * Returns array of warning messages.
   */
  function autoFixCrossConstraints(): string[] {
    const warnings: string[] = []
    dlog.constraint('=== autoFix 开始 ===')
    for (const [paramKey, constraint] of Object.entries(crossConstraints.value)) {
      const currentVal = getNested(values, paramKey, undefined)
      if (currentVal === undefined) continue
      if (constraint.locked) continue
      if (typeof currentVal !== 'number') continue
      const cMin = constraint.constrained_min
      const cMax = constraint.constrained_max
      if (cMin !== undefined && cMin !== null && currentVal < cMin - 0.01) {
        setNested(values, paramKey, cMin)
        const msg = `${paramKey}: ${currentVal} → ${cMin}`
        warnings.push(msg)
        dlog.warn(`autoFix: ${msg}`, { range: `[${cMin}, ${cMax}]` })
      } else if (cMax !== undefined && cMax !== null && currentVal > cMax + 0.01) {
        setNested(values, paramKey, cMax)
        const msg = `${paramKey}: ${currentVal} → ${cMax}`
        warnings.push(msg)
        dlog.warn(`autoFix: ${msg}`, { range: `[${cMin}, ${cMax}]` })
      }
    }
    if (warnings.length === 0) {
      dlog.constraint('autoFix: 无违规')
    }
    dlog.constraint('=== autoFix 结束 ===')
    return warnings
  }

  return {
    values,
    crossConstraints,
    setParam,
    getParam,
    removeParam,
    setFromPreset,
    setAll,
    setCrossConstraints,
    applyCrossConstraints,
    autoFixCrossConstraints,
  }
})
