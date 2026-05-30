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
  params?: Record<string, any>
  flat?: Record<string, any>
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

// ============ Drag Handle Types ============

export interface DragHandle {
  id: string
  paramKey: string
  position: [number, number, number] // CadQuery 坐标 (Z-up)
  axis: [number, number, number]
  color: number
  min: number
  max: number
  currentValue: number
  scaleAxis: 'z' | 'xy' // 预览变形轴
}

// ============ VLM Generate Types ============

export interface VlmProgressEvent {
  step: string        // 'vlm' | 'bottle' | 'cap' | 'wand' | 'wiper' | 'assembly' | 'complete' | 'error'
  status: 'running' | 'done' | 'error'
  message: string
  stl_url?: string
  step_url?: string
  time_sec?: number
  description?: string
  confidence?: number
  assembly?: any
  results?: Record<string, any>
}

// ============ Gallery Types ============

export interface GalleryVariant {
  cat_id: string
  label: string
  desc: string
  prebuilt?: boolean
}

export interface GalleryItem {
  cat_id: string
  desc: string
  thumbnail: string | null
  image_count: number
  prebuilt?: boolean
  variants?: GalleryVariant[]
}

export interface GalleryComponentResult {
  ok: boolean
  stl_url?: string
  step_url?: string
  svg_url?: string
  qc?: QCResult
  error?: string
}

export interface GalleryGenerateResponse {
  ok: boolean
  error?: string
  cat_id: string
  results: Record<string, GalleryComponentResult>
  assembly?: Record<string, any>
}

// ============ Showroom Types ============

export interface ShowroomSlot {
  id: string
  position: [number, number, number]
  rotation: [number, number, number]
  camera_target: [number, number, number]
  camera_position: [number, number, number]
  display_radius: number
}

export interface ShowroomManifest {
  id: string
  asset: string
  units: 'meters' | string
  default_camera: {
    position: [number, number, number]
    target: [number, number, number]
    fov: number
  }
  navigation: {
    bounds: {
      min: [number, number, number]
      max: [number, number, number]
    }
    walk_speed: number
    look_sensitivity: number
  }
  slots: ShowroomSlot[]
}

// ============ Exotic Cap Types ============

export interface ExoticPreset {
  id: string
  name: string
  description: string
  thumbnail_url: string | null
  model_format: string
  tags: string[]
  default_height_mm?: number
}

export interface ExoticCapGenerateResponse {
  ok: boolean
  error?: string
  stl?: string
  stl_url?: string
  time_sec?: number
  wall_check?: {
    ok: boolean
    min_wall_mm: number
    threshold_mm: number
    worst_z: number
    details: string
  }
  final_params?: Record<string, any>
  assembly?: Record<string, any>
}

// ============ Profile Constraints ============

export interface ProfileConstraints {
  r_start: number
  z_start: number
  r_end: number
  z_end: number
  r_min: number
  r_max: number
  r_min_z_max: number // r_min 仅在 z < 此值的区域强制生效
  cavity_r: number
  cavity_z_max: number
  supports_asymmetric?: boolean
}
