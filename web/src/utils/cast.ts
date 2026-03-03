import type { ParamDef } from '@/api/types'

export function inferTypeByValue(v: any): ParamDef['type'] {
  if (typeof v === 'boolean') return 'bool'
  if (typeof v === 'number') return Number.isInteger(v) ? 'int' : 'float'
  return 'str'
}

export function inferParamDef(k: string, seedVal: any): ParamDef {
  const def: ParamDef = {
    k,
    name: k,
    unit: '',
    type: inferTypeByValue(seedVal),
    default: seedVal,
  }
  if (def.type === 'float' || def.type === 'int') {
    def.step = def.type === 'int' ? 1 : 0.1
  }
  if (k.endsWith('_mm')) def.unit = 'mm'
  if (k.endsWith('_deg')) def.unit = 'deg'
  return def
}

export function castValue(def: ParamDef, raw: string): any {
  if (def.type === 'int') return parseInt(raw, 10)
  if (def.type === 'float') return parseFloat(raw)
  if (def.type === 'bool') return raw === 'true'
  return raw
}
