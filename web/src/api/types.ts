// ============ Backend Schema Types ============

export interface ParamDef {
  k: string
  name: string
  unit: string
  type: 'float' | 'int' | 'bool' | 'enum' | 'str'
  default: any
  min?: number
  max?: number
  step?: number
  choices?: string[]
  is_core?: boolean
  group?: string
  readonly?: boolean
}

export interface Preset {
  id: string
  name: string
  desc: string
  params: Record<string, any>
}

export interface Component {
  id: string
  name: string
  desc: string
  enabled: boolean
  params: ParamDef[]
  style_presets: Preset[]
}

export interface Product {
  id: string
  name: string
  components: Component[]
}

export interface Schema {
  products: Product[]
}

// ============ API Response Types ============

export interface QCCheck {
  id: string
  ok: boolean
  severity: 'hard' | 'soft'
  msg: string
}

export interface QCResult {
  ok: boolean
  checks: QCCheck[]
}

export interface GenerateResponse {
  ok: boolean
  error?: string
  step_url?: string
  stl_url?: string
  svg_url?: string
  time_sec?: number
  qc?: QCResult
}

// ============ Cross-Component Constraint Types ============

export interface CrossConstraint {
  locked: boolean
  constrained_default: any
  constrained_min?: number
  constrained_max?: number
  description: string
  source_component: string
  source_param: string
  source_value: any
}

export type CrossConstraintMap = Record<string, CrossConstraint>

// ============ Derived Rule Types ============

export interface DerivedRuleSpec {
  master: string
  computeDefault: (masterVal: number, allParams: Record<string, any>) => number
  computeRange: ((masterVal: number, allParams: Record<string, any>) => [number, number]) | null
  desc: string
  readonly?: boolean
}

export type DerivedRulesMap = Record<string, Record<string, DerivedRuleSpec>>

// ============ Viewer Types ============

export interface ModelInfo {
  mesh: any // THREE.Mesh - not typed to avoid Vue reactivity
  stlUrl: string
  visible: boolean
  color: number
  params: Record<string, any>
}

export interface PendingSTL {
  url: string
  params: Record<string, any>
}
