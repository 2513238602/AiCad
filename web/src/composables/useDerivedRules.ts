import type { DerivedRulesMap } from '@/api/types'
import { getNested } from '@/utils/nested'

/**
 * Frontend derived parameter computation rules.
 * These mirror the backend rules in src/products/lip_gloss/derived_params.py
 * and are kept in frontend for real-time slider responsiveness.
 */
export const DERIVED_RULES: DerivedRulesMap = {
  cap: {
    inner_id_mm: {
      master: 'outer_od_mm',
      computeDefault: (od) => od - 1.6,
      computeRange: (od) => [8.0, od - 1.6],
      desc: '内径 = 外径 - 1.6mm',
    },
    cavity_depth_mm: {
      master: 'height_mm',
      computeDefault: (h) => h - 1.5,
      computeRange: (h) => [5.0, h - 1.5],
      desc: '内腔深 = 总高 - 1.5mm',
    },
  },
  bottle: {
    shoulder_height_mm: {
      master: 'body_od_mm',
      computeDefault: (od, p) => {
        const neck_od = getNested(p, 'neck_od_mm', 18.0)
        const diff = od - neck_od
        return Math.max(5.0, diff * 0.5 + 3.0)
      },
      computeRange: (od, p) => {
        const neck_od = getNested(p, 'neck_od_mm', 18.0)
        const height = getNested(p, 'height_mm', 70.0)
        const diff = od - neck_od
        return [Math.max(5.0, diff * 0.3), Math.min(height * 0.4, 30.0)]
      },
      desc: '肩高随外径和颈径差联动',
    },
    inner_depth_mm: {
      master: 'height_mm',
      computeDefault: (h, p) => {
        const bottom_t = getNested(p, 'bottom_thickness_mm', 2.0)
        return h - bottom_t - 3.0
      },
      computeRange: (h, p) => {
        const bottom_t = getNested(p, 'bottom_thickness_mm', 2.0)
        const neck_h = getNested(p, 'neck_height_mm', 10.0)
        return [neck_h + 5.0, h - bottom_t - 0.5]
      },
      desc: '内深 = 总高 - 底厚 - 余量',
    },
    wall_thickness_mm: {
      master: 'body_od_mm',
      computeDefault: (od) => Math.max(1.0, Math.min(2.0, od * 0.05)),
      computeRange: (od) => [1.0, Math.min(od * 0.15, 3.0)],
      desc: '壁厚约外径的5%',
    },
    capacity_ml: {
      master: 'body_od_mm',
      computeDefault: (od, p) => {
        const wall = getNested(p, 'wall_thickness_mm', 1.2)
        const inner_depth = getNested(p, 'inner_depth_mm', 55.0)
        const inner_d = od - 2 * wall
        const inner_r = inner_d / 2.0
        const v_ml = (Math.PI * inner_r * inner_r * inner_depth) / 1000.0
        return Math.round(v_ml * 10) / 10
      },
      computeRange: null,
      desc: '容量由尺寸计算',
      readonly: true,
    },
    full_capacity_ml: {
      master: 'body_od_mm',
      computeDefault: (od, p) => {
        const wall = getNested(p, 'wall_thickness_mm', 1.2)
        const height = getNested(p, 'height_mm', 70.0)
        const bottom_t = getNested(p, 'bottom_thickness_mm', 2.0)
        const inner_d = od - 2 * wall
        const inner_r = inner_d / 2.0
        const full_depth = height - bottom_t
        const v_ml = (Math.PI * inner_r * inner_r * full_depth) / 1000.0
        return Math.round(v_ml * 10) / 10
      },
      computeRange: null,
      desc: '满口容量由尺寸计算',
      readonly: true,
    },
  },
  wand: {
    'seal_ring.od_mm': {
      master: 'outer_od_mm',
      computeDefault: (od, p) => {
        let basic = od - 5.5
        // 确保气密环不超过螺牙底径 + 1.0（为 seal_fit 留余量）
        const threadEnabled = getNested(p, 'thread.enabled', true)
        if (threadEnabled !== false) {
          const crest = Number(getNested(p, 'thread.crest_dia_mm', od - 5.0))
          const depth = Number(getNested(p, 'thread.depth_mm', 0.5))
          const root = crest - 2 * depth
          basic = Math.min(basic, root + 1.0)
        }
        return Math.max(8.0, basic)
      },
      computeRange: (od, p) => {
        let maxOd = od - 3.0
        const threadEnabled = getNested(p, 'thread.enabled', true)
        if (threadEnabled !== false) {
          const crest = Number(getNested(p, 'thread.crest_dia_mm', od - 5.0))
          const depth = Number(getNested(p, 'thread.depth_mm', 0.5))
          const root = crest - 2 * depth
          maxOd = Math.min(maxOd, root + 1.5)
        }
        return [10.0, maxOd]
      },
      desc: '气密环外径 = min(外径 - 5.5, 螺牙底径 + 1.0)',
    },
    cavity_depth_mm: {
      master: 'cap_height_mm',
      computeDefault: (h) => h - 0.5,
      computeRange: (h) => [5.0, h - 0.3],
      desc: '内腔深 = 盖高 - 0.5mm（薄顶壁）',
    },
    stem_length_mm: {
      master: 'total_height_mm',
      computeDefault: (th, p) => {
        const cap_h = getNested(p, 'cap_height_mm', 19.0)
        return Math.round((th - cap_h) * 10) / 10
      },
      computeRange: (th, p) => {
        const cap_h = getNested(p, 'cap_height_mm', 19.0)
        return [Math.max(20.0, th - cap_h - 10.0), th - cap_h + 5.0]
      },
      desc: '杆长 = 总高 - 盖高',
    },
    mouth_to_top_mm: {
      master: 'cap_height_mm',
      computeDefault: (ch) => Math.round(ch * 0.63 * 10) / 10,
      computeRange: (ch) => [Math.max(5.0, ch * 0.5), Math.min(25.0, ch * 0.8)],
      desc: '口部至顶 ≈ 盖高 × 0.63',
    },
    'thread.crest_dia_mm': {
      master: 'outer_od_mm',
      computeDefault: (od) => Math.round((od - 5.0) * 10) / 10,
      computeRange: (od) => [Math.max(10.0, od - 8.0), od - 4.0],
      desc: '螺纹峰径 ≈ 外径 - 5mm',
    },
  },
  wiper: {
    inner_id_mm: {
      master: 'outer_od_mm',
      computeDefault: (od) => od - 2.0,
      computeRange: (od, p) => {
        const orifice = getNested(p, 'orifice_mm', 7.0)
        return [orifice + 1.0, od - 1.0]
      },
      desc: '内径 = 外径 - 2mm',
    },
    flange_od_mm: {
      master: 'outer_od_mm',
      computeDefault: (od) => od + 1.5,
      computeRange: (od) => [od, od + 4.0],
      desc: '凸环外径 = 外径 + 1.5mm',
    },
    flange_id_mm: {
      master: 'outer_od_mm',
      computeDefault: (od) => od - 1.0,
      computeRange: (od, p) => {
        const flange_od = getNested(p, 'flange_od_mm', od + 1.5)
        return [5.0, flange_od - 1.0]
      },
      desc: '凸环内径 = 外径 - 1mm',
    },
  },
}

export function isDerivedParam(componentId: string, paramKey: string): boolean {
  return !!(DERIVED_RULES[componentId] && DERIVED_RULES[componentId][paramKey])
}

export function isDerivedReadonly(componentId: string, paramKey: string): boolean {
  const rules = DERIVED_RULES[componentId]
  if (!rules || !rules[paramKey]) return false
  return rules[paramKey].readonly === true
}

export function getDerivedDesc(componentId: string, paramKey: string): string {
  const rules = DERIVED_RULES[componentId]
  if (!rules || !rules[paramKey]) return ''
  return rules[paramKey].desc || ''
}

export function computeDerivedDefault(
  componentId: string,
  paramKey: string,
  params: Record<string, any>,
): number | null {
  const rules = DERIVED_RULES[componentId]
  if (!rules) return null
  const rule = rules[paramKey]
  if (!rule) return null
  const masterValue = getNested(params, rule.master, null)
  if (masterValue === null) return null
  try {
    return rule.computeDefault(masterValue, params)
  } catch {
    return null
  }
}

export function computeDerivedRange(
  componentId: string,
  paramKey: string,
  params: Record<string, any>,
): [number, number] | null {
  const rules = DERIVED_RULES[componentId]
  if (!rules) return null
  const rule = rules[paramKey]
  if (!rule || !rule.computeRange) return null
  const masterValue = getNested(params, rule.master, null)
  if (masterValue === null) return null
  try {
    return rule.computeRange(masterValue, params)
  } catch {
    return null
  }
}

/**
 * When a core parameter changes, update all derived parameters that depend on it.
 */
export function updateDerivedParams(
  componentId: string,
  changedParamKey: string,
  params: Record<string, any>,
  setParam: (key: string, val: any) => void,
) {
  const rules = DERIVED_RULES[componentId]
  if (!rules) return
  for (const [derivedKey, rule] of Object.entries(rules)) {
    if (rule.master === changedParamKey) {
      const newDefault = computeDerivedDefault(componentId, derivedKey, params)
      if (newDefault !== null) {
        setParam(derivedKey, newDefault)
      }
    }
  }
}

/**
 * Recalculate ALL derived parameters for a component.
 * Used after cross-component constraints may have modified core params.
 * Skips params that are locked by cross-component constraints.
 */
export function recalcAllDerivedParams(
  componentId: string,
  params: Record<string, any>,
  setParam: (key: string, val: any) => void,
  lockedKeys?: Set<string>,
) {
  const rules = DERIVED_RULES[componentId]
  if (!rules) return
  for (const [derivedKey, rule] of Object.entries(rules)) {
    if (lockedKeys && lockedKeys.has(derivedKey)) continue // respect constraint locks
    const newVal = computeDerivedDefault(componentId, derivedKey, params)
    if (newVal !== null) {
      setParam(derivedKey, Math.round(newVal * 100) / 100)
    }
  }
}
