<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAppStore } from '@/stores/app'
import { useParamsStore } from '@/stores/params'
import { useGenerate } from '@/composables/useGenerate'
import { getNested } from '@/utils/nested'
import * as api from '@/api/client'
import type { ProfileConstraints } from '@/api/types'

const props = defineProps<{
  paramKey: string // 'profile_points_json'
}>()

const { t } = useI18n()
const appStore = useAppStore()
const paramsStore = useParamsStore()
const { scheduleAutoGenerate } = useGenerate()

// ── SVG canvas size ────────────────────────────────
const W = 380
const H = 460
const PAD = 36

// ── Constraints from backend ────────────────────────
const constraints = ref<ProfileConstraints | null>(null)
const loadingConstraints = ref(false)

async function fetchConstraints() {
  if (!appStore.componentId) return
  loadingConstraints.value = true
  const params = JSON.parse(JSON.stringify(paramsStore.values))
  const result = await api.fetchProfileConstraints(appStore.componentId, params)
  constraints.value = result
  loadingConstraints.value = false
}

onMounted(fetchConstraints)

// Re-fetch when core params change
watch(
  () => [
    getNested(paramsStore.values, 'outer_od_mm', null),
    getNested(paramsStore.values, 'height_mm', null),
    getNested(paramsStore.values, 'inner_id_mm', null),
    getNested(paramsStore.values, 'cavity_depth_mm', null),
    getNested(paramsStore.values, 'taper_deg', null),
    getNested(paramsStore.values, 'body_od_mm', null),
    getNested(paramsStore.values, 'total_height_mm', null),
    getNested(paramsStore.values, 'neck_od_mm', null),
    getNested(paramsStore.values, 'wall_thickness_mm', null),
    appStore.componentId,
  ],
  fetchConstraints,
  { deep: true },
)

// ── Parse control points ────────────────────────────
const points = computed<number[][]>(() => {
  const raw = getNested(paramsStore.values, props.paramKey, '[]')
  try {
    const arr = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(arr) ? arr.filter((p: any) => Array.isArray(p) && p.length >= 2) : []
  } catch {
    return []
  }
})

// ── Asymmetric mode ────────────────────────────────
const isAsymmetric = computed(() => {
  return getNested(paramsStore.values, 'profile_symmetry', 'symmetric') === 'asymmetric'
})

const pointsB = computed<number[][]>(() => {
  if (!isAsymmetric.value) return []
  const raw = getNested(paramsStore.values, 'profile_b_points_json', '[]')
  try {
    const arr = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(arr) ? arr.filter((p: any) => Array.isArray(p) && p.length >= 2) : []
  } catch {
    return []
  }
})

function writePointsB(pts: number[][]) {
  paramsStore.setParam('profile_b_points_json', JSON.stringify(pts))
  if (appStore.autoGenerate) scheduleAutoGenerate()
}

function toggleSymmetry(mode: string) {
  paramsStore.setParam('profile_symmetry', mode)
  if (mode === 'asymmetric' && pointsB.value.length === 0) {
    // 首次切换到非对称：从 A 轮廓生成 B（中间点 R × 0.9）
    const ptsA = points.value
    const ptsB = ptsA.map(([r, z], i) => {
      if (i === 0 || i === ptsA.length - 1) return [r, z]
      return [parseFloat((r * 0.9).toFixed(1)), z]
    })
    writePointsB(ptsB)
  }
  if (appStore.autoGenerate) scheduleAutoGenerate()
}

// ── Data range for SVG coordinate mapping ────────────
const rRange = computed(() => {
  const c = constraints.value
  if (c) {
    // Full R range: from r_end (neck) to r_max, so S-curve narrowing is visible
    const lo = Math.min(c.r_end, c.r_min) // could be neck_r ~ 9
    const hi = c.r_max                      // could be body_r*1.05 ~ 12.6
    const span = hi - lo
    const margin = Math.max(span * 0.15, 0.5)
    return [Math.max(0, lo - margin), hi + margin]
  }
  if (points.value.length === 0) return [0, 15]
  const rs = points.value.map((p) => p[0])
  if (isAsymmetric.value && pointsB.value.length > 0) {
    rs.push(...pointsB.value.map((p) => p[0]))
  }
  const rMin = Math.min(...rs)
  const rMax = Math.max(...rs)
  const span = rMax - rMin
  const margin = Math.max(span * 0.15, 0.5)
  return [Math.max(0, rMin - margin), rMax + margin]
})
const zRange = computed(() => {
  const c = constraints.value
  if (c) return [-1, c.z_end * 1.08]
  if (points.value.length === 0) return [0, 70]
  const zs = points.value.map((p) => p[1])
  return [Math.min(0, ...zs), Math.max(...zs) * 1.05 + 2]
})

// Coordinate transforms
function toSvgX(r: number) {
  const [rMin, rMax] = rRange.value
  if (rMax <= rMin) return PAD
  return PAD + ((r - rMin) / (rMax - rMin)) * (W - 2 * PAD)
}
function toSvgY(z: number) {
  const [zMin, zMax] = zRange.value
  if (zMax <= zMin) return H - PAD
  return H - PAD - ((z - zMin) / (zMax - zMin)) * (H - 2 * PAD)
}
function fromSvgX(sx: number) {
  const [rMin, rMax] = rRange.value
  return rMin + ((sx - PAD) / (W - 2 * PAD)) * (rMax - rMin)
}
function fromSvgY(sy: number) {
  const [zMin, zMax] = zRange.value
  return zMin + ((H - PAD - sy) / (H - 2 * PAD)) * (zMax - zMin)
}

// ── SVG path: Catmull-Rom → cubic Bezier (matches backend B-spline) ──
const profilePath = computed(() => {
  const pts = points.value
  if (pts.length < 2) return ''

  const sx = (r: number) => toSvgX(r).toFixed(1)
  const sy = (z: number) => toSvgY(z).toFixed(1)

  let d = `M${sx(pts[0][0])},${sy(pts[0][1])}`

  if (pts.length === 2) {
    d += ` L${sx(pts[1][0])},${sy(pts[1][1])}`
    return d
  }

  // Catmull-Rom to cubic Bezier: for segment p[i]→p[i+1],
  // use neighbors p[i-1] and p[i+2] (clamped at boundaries)
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(i - 1, 0)]
    const p1 = pts[i]
    const p2 = pts[i + 1]
    const p3 = pts[Math.min(i + 2, pts.length - 1)]

    const cp1x = toSvgX(p1[0]) + (toSvgX(p2[0]) - toSvgX(p0[0])) / 6
    const cp1y = toSvgY(p1[1]) + (toSvgY(p2[1]) - toSvgY(p0[1])) / 6
    const cp2x = toSvgX(p2[0]) - (toSvgX(p3[0]) - toSvgX(p1[0])) / 6
    const cp2y = toSvgY(p2[1]) - (toSvgY(p3[1]) - toSvgY(p1[1])) / 6

    d += ` C${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${sx(p2[0])},${sy(p2[1])}`
  }

  return d
})

// ── SVG path for Profile B (asymmetric mode) ──
const profilePathB = computed(() => {
  if (!isAsymmetric.value) return ''
  const pts = pointsB.value
  if (pts.length < 2) return ''

  const sx2 = (r: number) => toSvgX(r).toFixed(1)
  const sy2 = (z: number) => toSvgY(z).toFixed(1)

  let d = `M${sx2(pts[0][0])},${sy2(pts[0][1])}`

  if (pts.length === 2) {
    d += ` L${sx2(pts[1][0])},${sy2(pts[1][1])}`
    return d
  }

  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(i - 1, 0)]
    const p1 = pts[i]
    const p2 = pts[i + 1]
    const p3 = pts[Math.min(i + 2, pts.length - 1)]

    const cp1x = toSvgX(p1[0]) + (toSvgX(p2[0]) - toSvgX(p0[0])) / 6
    const cp1y = toSvgY(p1[1]) + (toSvgY(p2[1]) - toSvgY(p0[1])) / 6
    const cp2x = toSvgX(p2[0]) - (toSvgX(p3[0]) - toSvgX(p1[0])) / 6
    const cp2y = toSvgY(p2[1]) - (toSvgY(p3[1]) - toSvgY(p1[1])) / 6

    d += ` C${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${sx2(p2[0])},${sy2(p2[1])}`
  }

  return d
})

// Axis line (r=0, only show if visible in current range)
const axisPath = computed(() => {
  const [rMin] = rRange.value
  if (rMin > 0) return '' // r=0 is outside visible range
  const x = toSvgX(0)
  return `M${x},${PAD} L${x},${H - PAD}`
})

// ── Safe zone / cavity rects ────────────────────────
// Safe zone rect: only in body area (z < r_min_z_max) where r_min is enforced
const safeZoneRect = computed(() => {
  const c = constraints.value
  if (!c) return null
  const zTop = c.r_min_z_max ?? c.z_end
  return {
    x: toSvgX(c.r_min),
    y: toSvgY(zTop),
    width: toSvgX(c.r_max) - toSvgX(c.r_min),
    height: toSvgY(0) - toSvgY(zTop),
  }
})

// Shoulder zone: wider R range allowed (from r_end to r_max)
const shoulderZoneRect = computed(() => {
  const c = constraints.value
  if (!c) return null
  const zTop = c.r_min_z_max ?? c.z_end
  if (zTop >= c.z_end) return null // no separate shoulder zone
  const rLo = Math.min(c.r_end, c.r_min) * 0.9
  return {
    x: toSvgX(rLo),
    y: toSvgY(c.z_end),
    width: toSvgX(c.r_max) - toSvgX(rLo),
    height: toSvgY(zTop) - toSvgY(c.z_end),
  }
})

const cavityRect = computed(() => {
  const c = constraints.value
  if (!c) return null
  return {
    x: toSvgX(0),
    y: toSvgY(c.cavity_z_max),
    width: toSvgX(c.cavity_r) - toSvgX(0),
    height: toSvgY(0) - toSvgY(c.cavity_z_max),
  }
})

// Boundary lines
const rMinLine = computed(() => {
  const c = constraints.value
  if (!c) return ''
  const x = toSvgX(c.r_min)
  const zTop = c.r_min_z_max ?? c.z_end
  return `M${x},${toSvgY(zTop)} L${x},${toSvgY(0)}`
})
const rMaxLine = computed(() => {
  const c = constraints.value
  if (!c) return ''
  const x = toSvgX(c.r_max)
  return `M${x},${toSvgY(c.z_end)} L${x},${toSvgY(0)}`
})

// ── Write points to params store ──────────────────────
function writePoints(pts: number[][]) {
  paramsStore.setParam(props.paramKey, JSON.stringify(pts))
  if (appStore.autoGenerate) scheduleAutoGenerate()
}

// ── Clamp point to constraints ────────────────────────
function clampPoint(idx: number, r: number, z: number, pts: number[][]): [number, number] {
  const c = constraints.value
  if (!c) return [Math.max(0.5, parseFloat(r.toFixed(1))), parseFloat(z.toFixed(1))]

  // Lock first and last points
  if (idx === 0) return [c.r_start, c.z_start]
  if (idx === pts.length - 1) return [c.r_end, c.z_end]

  // Clamp Z first: must be between neighbors (monotonic increasing, 0.5mm gap)
  const z_floor = pts[idx - 1][1] + 0.5
  const z_ceil = pts[idx + 1][1] - 0.5
  z = Math.max(z_floor, Math.min(z_ceil, z))

  // Zone-aware R clamping:
  // - Body zone (z < r_min_z_max): r_min enforced (wall thickness safety)
  // - Shoulder zone (z >= r_min_z_max): r can narrow freely toward r_end
  const rMinZMax = c.r_min_z_max ?? c.z_end
  const effectiveRMin = z < rMinZMax
    ? c.r_min
    : Math.max(0.5, Math.min(c.r_end, c.r_min) * 0.9) // shoulder: allow narrowing
  r = Math.max(effectiveRMin, Math.min(c.r_max, r))

  return [parseFloat(r.toFixed(1)), parseFloat(z.toFixed(1))]
}

// ── Drag interaction ─────────────────────────────────
const dragging = ref<number | null>(null)
const svgRef = ref<SVGSVGElement | null>(null)

function isLocked(idx: number) {
  return idx === 0 || idx === points.value.length - 1
}

function onPointerDown(idx: number, e: PointerEvent) {
  if (isLocked(idx)) return
  dragging.value = idx
  ;(e.target as Element)?.setPointerCapture?.(e.pointerId)
}

function onPointerMove(e: PointerEvent) {
  // Handle B profile dragging
  if (draggingB.value !== null) {
    onPointerMoveB(e)
    return
  }
  if (dragging.value === null || !svgRef.value) return
  const rect = svgRef.value.getBoundingClientRect()
  const sx = e.clientX - rect.left
  const sy = e.clientY - rect.top
  const rawR = fromSvgX(sx)
  const rawZ = fromSvgY(sy)
  const pts = points.value.map((p) => [...p])
  const [r, z] = clampPoint(dragging.value, rawR, rawZ, pts)
  pts[dragging.value] = [r, z]
  writePoints(pts)
}

function onPointerUp() {
  dragging.value = null
  draggingB.value = null
}

// ── Profile B drag interaction ────────────────────────
const draggingB = ref<number | null>(null)

function onPointerDownB(idx: number, e: PointerEvent) {
  if (isLocked(idx)) return
  draggingB.value = idx
  ;(e.target as Element)?.setPointerCapture?.(e.pointerId)
}

function onPointerMoveB(e: PointerEvent) {
  if (draggingB.value === null || !svgRef.value) return
  const rect = svgRef.value.getBoundingClientRect()
  const sx = e.clientX - rect.left
  const rawR = fromSvgX(sx)
  // B 轮廓拖拽只改变 R，Z 与 A 保持同步
  const ptsB = pointsB.value.map((p) => [...p])
  const ptsA = points.value
  const idx = draggingB.value
  const z = ptsA[idx] ? ptsA[idx][1] : ptsB[idx][1]
  const [r] = clampPoint(idx, rawR, z, ptsB)
  ptsB[idx] = [r, z]
  writePointsB(ptsB)
}

function updatePointB(idx: number, field: 0 | 1, val: string) {
  if (isLocked(idx)) return
  const n = parseFloat(val)
  if (isNaN(n)) return
  const ptsB = pointsB.value.map((p) => [...p])
  ptsB[idx][field] = parseFloat(n.toFixed(2))
  const [r, z] = clampPoint(idx, ptsB[idx][0], ptsB[idx][1], ptsB)
  ptsB[idx] = [r, z]
  writePointsB(ptsB)
}

// ── Point type classification (B-spline: all intermediate points are equal) ──
function pointType(idx: number): 'locked' | 'control' {
  if (idx === 0 || idx === points.value.length - 1) return 'locked'
  return 'control'
}

function pointColor(idx: number): string {
  return pointType(idx) === 'locked' ? '#f59e0b' : '#2563eb'
}

// ── Table editing ──────────────────────────────────
function updatePoint(idx: number, field: 0 | 1, val: string) {
  if (isLocked(idx)) return
  const n = parseFloat(val)
  if (isNaN(n)) return
  const pts = points.value.map((p) => [...p])
  pts[idx][field] = parseFloat(n.toFixed(2))
  const [r, z] = clampPoint(idx, pts[idx][0], pts[idx][1], pts)
  pts[idx] = [r, z]
  writePoints(pts)
}

// ── Smart add: insert 1 point in the longest segment (B-spline, any count ≥ 3 works) ──
function addPoint() {
  const c = constraints.value
  const pts = points.value.map((p) => [...p])
  if (pts.length < 3 && c) {
    applyPreset('barrel')
    return
  }
  if (pts.length < 2) return

  // Find the longest segment and insert a midpoint
  let maxGap = 0
  let gapIdx = 0
  for (let i = 0; i < pts.length - 1; i++) {
    const gap = pts[i + 1][1] - pts[i][1]
    if (gap > maxGap) {
      maxGap = gap
      gapIdx = i
    }
  }

  const startPt = pts[gapIdx]
  const endPt = pts[gapIdx + 1]
  const midZ = (startPt[1] + endPt[1]) / 2
  const midR = (startPt[0] + endPt[0]) / 2

  pts.splice(gapIdx + 1, 0,
    [parseFloat(midR.toFixed(1)), parseFloat(midZ.toFixed(1))],
  )
  writePoints(pts)

  // Sync B profile if asymmetric
  if (isAsymmetric.value) {
    const ptsB = pointsB.value.map((p) => [...p])
    const midRB = ptsB[gapIdx] && ptsB[gapIdx + 1]
      ? (ptsB[gapIdx][0] + ptsB[gapIdx + 1][0]) / 2
      : midR
    ptsB.splice(gapIdx + 1, 0,
      [parseFloat(midRB.toFixed(1)), parseFloat(midZ.toFixed(1))],
    )
    writePointsB(ptsB)
  }
}

// ── Remove single point (B-spline, minimum 3 points) ──
function removePoint(idx: number) {
  const pts = points.value.map((p) => [...p])
  if (pts.length <= 3) return
  if (isLocked(idx)) return
  pts.splice(idx, 1)
  writePoints(pts)

  // Sync B profile if asymmetric
  if (isAsymmetric.value) {
    const ptsB = pointsB.value.map((p) => [...p])
    if (idx < ptsB.length) {
      ptsB.splice(idx, 1)
      writePointsB(ptsB)
    }
  }
}

// ── Preset curves ────────────────────────────────────
type PresetId = 'barrel' | 'hourglass' | 'taper' | 'swave' | 'straight'

const PRESETS: { id: PresetId; labelKey: string }[] = [
  { id: 'barrel', labelKey: 'profile.presetBarrel' },
  { id: 'hourglass', labelKey: 'profile.presetHourglass' },
  { id: 'taper', labelKey: 'profile.presetTaper' },
  { id: 'swave', labelKey: 'profile.presetSwave' },
  { id: 'straight', labelKey: 'profile.presetStraight' },
]
const activePreset = ref<PresetId | null>(null)

function generatePresetPoints(preset: PresetId, c: ProfileConstraints): number[][] {
  const { r_start, z_start, r_end, z_end, r_min, r_max } = c
  const rMinZMax = c.r_min_z_max ?? z_end

  // Body zone helpers (z < rMinZMax): strict r_min
  const safeMin = r_min + 0.3
  // Shoulder zone helpers (z >= rMinZMax): free to narrow toward r_end
  // lerp: linearly interpolate R based on Z position within shoulder zone
  const shoulderR = (zFrac: number) => {
    // zFrac: 0 = start of shoulder, 1 = top
    const rTop = r_end
    const rBot = Math.min(r_start, safeMin) // shoulder bottom = body top radius
    return rBot + (rTop - rBot) * zFrac
  }

  // Z helpers relative to total height
  const dz = z_end - z_start
  const zAt = (frac: number) => z_start + dz * frac
  // Fraction of height where shoulder starts
  const shoulderFrac = (rMinZMax - z_start) / dz

  switch (preset) {
    case 'barrel':
      // 5 points: outward bulge in body, smooth taper in shoulder
      return [
        [r_start, z_start],
        [Math.min(r_start * 1.03, r_max), zAt(shoulderFrac * 0.3)],
        [Math.min(r_start * 1.04, r_max), zAt(shoulderFrac * 0.6)],
        [shoulderR(0.4), zAt(shoulderFrac + (1 - shoulderFrac) * 0.5)],
        [r_end, z_end],
      ]
    case 'hourglass':
      // 7 points: wide → narrow waist → wide → narrow to neck
      return [
        [r_start, z_start],
        [Math.min(r_start * 1.02, r_max), zAt(shoulderFrac * 0.2)],
        [safeMin + (r_max - safeMin) * 0.2, zAt(shoulderFrac * 0.5)],
        [Math.min(r_start * 1.01, r_max), zAt(shoulderFrac * 0.8)],
        [shoulderR(0.3), zAt(shoulderFrac + (1 - shoulderFrac) * 0.3)],
        [shoulderR(0.6), zAt(shoulderFrac + (1 - shoulderFrac) * 0.6)],
        [r_end, z_end],
      ]
    case 'taper':
      // 5 points: gradual narrowing from body through shoulder
      return [
        [r_start, z_start],
        [r_start * 0.98, zAt(shoulderFrac * 0.5)],
        [safeMin + (r_start - safeMin) * 0.5, zAt(shoulderFrac)],
        [shoulderR(0.5), zAt(shoulderFrac + (1 - shoulderFrac) * 0.5)],
        [r_end, z_end],
      ]
    case 'swave': {
      // 7 points: TRUE S-curve — body bulges OUT, then dramatic shoulder narrows IN
      const bulge = Math.min(r_start * 1.05, r_max)      // body: outward swell
      const waist = shoulderR(0.4)                         // shoulder: inward pull
      return [
        [r_start, z_start],
        [bulge, zAt(shoulderFrac * 0.25)],                 // outward control
        [bulge * 0.99, zAt(shoulderFrac * 0.55)],          // peak of body swell
        [safeMin + (r_start - safeMin) * 0.3, zAt(shoulderFrac * 0.9)], // body-shoulder transition
        [waist, zAt(shoulderFrac + (1 - shoulderFrac) * 0.35)],  // inward shoulder
        [shoulderR(0.7), zAt(shoulderFrac + (1 - shoulderFrac) * 0.7)], // narrowing
        [r_end, z_end],
      ]
    }
    case 'straight':
      // 3 points: nearly straight line from r_start to r_end
      return [
        [r_start, z_start],
        [(r_start + r_end) / 2, zAt(0.5)],
        [r_end, z_end],
      ]
    default:
      return [
        [r_start, z_start],
        [(r_start + r_end) / 2, zAt(0.5)],
        [r_end, z_end],
      ]
  }
}

function applyPreset(presetId: PresetId) {
  if (!constraints.value) return
  const pts = generatePresetPoints(presetId, constraints.value)
  // Round all values
  const rounded = pts.map(([r, z]) => [parseFloat(r.toFixed(1)), parseFloat(z.toFixed(1))])
  activePreset.value = presetId
  writePoints(rounded)

  // Sync B profile if asymmetric mode
  if (isAsymmetric.value) {
    const ptsB = rounded.map(([r, z], i) => {
      if (i === 0 || i === rounded.length - 1) return [r, z]
      return [parseFloat((r * 0.9).toFixed(1)), z]
    })
    writePointsB(ptsB)
  }
}

function resetToDefault() {
  applyPreset('barrel')
}

// ── Validation / status ──────────────────────────────
const status = computed<{ type: 'ok' | 'error' | 'warn'; msg: string }>(() => {
  const pts = points.value
  if (pts.length === 0) return { type: 'error', msg: t('profile.noPoints') }
  if (pts.length < 3) return { type: 'error', msg: t('profile.tooFewPoints') }
  for (let i = 1; i < pts.length; i++) {
    if (pts[i][1] <= pts[i - 1][1]) {
      return { type: 'error', msg: t('profile.zNotMonotonic') }
    }
  }
  for (let i = 0; i < pts.length; i++) {
    if (pts[i][0] <= 0) {
      return { type: 'error', msg: t('profile.rNotPositive') }
    }
  }
  const segCount = pts.length - 1
  return { type: 'ok', msg: `${t('profile.valid')} (${pts.length} ${t('profile.points')}, ${segCount} ${t('profile.segments')})` }
})

// ── Drag label position ──────────────────────────────
const dragLabel = computed(() => {
  if (dragging.value === null) return null
  const pt = points.value[dragging.value]
  if (!pt) return null
  return {
    x: toSvgX(pt[0]) + 12,
    y: toSvgY(pt[1]) - 12,
    text: `R:${pt[0].toFixed(1)} Z:${pt[1].toFixed(1)}`,
  }
})

// ── Help dialog ──────────────────────────────────────
const showHelp = ref(false)

// ── Expanded state ──────────────────────────────────
const expanded = ref(true)

// ── Scale label values ──────────────────────────────
const rScaleLabels = computed(() => {
  const [rMin, rMax] = rRange.value
  const step = (rMax - rMin) / 5
  return Array.from({ length: 6 }, (_, i) => ({
    val: rMin + step * i,
    x: toSvgX(rMin + step * i),
  }))
})
const zScaleLabels = computed(() => {
  const [zMin, zMax] = zRange.value
  const step = (zMax - zMin) / 5
  return Array.from({ length: 6 }, (_, i) => ({
    val: zMin + step * i,
    y: toSvgY(zMin + step * i),
  }))
})
</script>

<template>
  <div class="profile-editor">
    <div class="pe-header" @click="expanded = !expanded">
      <span class="pe-toggle">{{ expanded ? '\u25BE' : '\u25B8' }}</span>
      <span>{{ t('profile.editorTitle') }}</span>
      <el-tag size="small" type="info" effect="light" style="margin-left: 6px">
        {{ points.length }} {{ t('profile.points') }}
      </el-tag>
      <span class="pe-help-btn" @click.stop="showHelp = !showHelp" title="Help">?</span>
    </div>

    <!-- Help overlay -->
    <div v-if="showHelp" class="pe-help-overlay" @click="showHelp = false">
      <div class="pe-help-content" @click.stop>
        <div class="pe-help-title">{{ t('profile.helpTitle') }}</div>
        <ul class="pe-help-list">
          <li>{{ t('profile.helpLocked') }}</li>
          <li>{{ t('profile.helpDrag') }}</li>
          <li>{{ t('profile.helpSafeZone') }}</li>
          <li>{{ t('profile.helpClamp') }}</li>
          <li>{{ t('profile.helpPreset') }}</li>
        </ul>
        <el-button size="small" @click="showHelp = false">{{ t('ui.ok') }}</el-button>
      </div>
    </div>

    <div v-show="expanded" class="pe-body">
      <div class="pe-layout">
        <!-- LEFT: SVG Canvas -->
        <div class="pe-canvas-wrap">
          <svg
            ref="svgRef"
            :width="W"
            :height="H"
            class="pe-canvas"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointerleave="onPointerUp"
          >
            <!-- Grid -->
            <line
              v-for="i in 5"
              :key="'gv' + i"
              :x1="PAD + ((W - 2 * PAD) * i) / 5"
              :y1="PAD"
              :x2="PAD + ((W - 2 * PAD) * i) / 5"
              :y2="H - PAD"
              stroke="#e2e8f0"
              stroke-width="0.5"
            />
            <line
              v-for="i in 5"
              :key="'gh' + i"
              :x1="PAD"
              :y1="PAD + ((H - 2 * PAD) * i) / 5"
              :x2="W - PAD"
              :y2="PAD + ((H - 2 * PAD) * i) / 5"
              stroke="#e2e8f0"
              stroke-width="0.5"
            />

            <!-- Scale labels -->
            <text
              v-for="lbl in rScaleLabels"
              :key="'rs' + lbl.val"
              :x="lbl.x"
              :y="H - PAD + 14"
              text-anchor="middle"
              class="pe-scale-label"
            >{{ lbl.val.toFixed(0) }}</text>
            <text
              v-for="lbl in zScaleLabels"
              :key="'zs' + lbl.val"
              :x="PAD - 6"
              :y="lbl.y + 3"
              text-anchor="end"
              class="pe-scale-label"
            >{{ lbl.val.toFixed(0) }}</text>

            <!-- Layer 2: Cavity zone (red tint) -->
            <rect
              v-if="cavityRect"
              :x="cavityRect.x"
              :y="cavityRect.y"
              :width="cavityRect.width"
              :height="cavityRect.height"
              fill="rgba(239,68,68,0.06)"
              stroke="none"
            />

            <!-- Layer 3a: Safe zone - body area (green tint, strict r_min) -->
            <rect
              v-if="safeZoneRect"
              :x="safeZoneRect.x"
              :y="safeZoneRect.y"
              :width="safeZoneRect.width"
              :height="safeZoneRect.height"
              fill="rgba(34,197,94,0.08)"
              stroke="none"
            />
            <!-- Layer 3b: Shoulder zone (blue tint, wider R range) -->
            <rect
              v-if="shoulderZoneRect"
              :x="shoulderZoneRect.x"
              :y="shoulderZoneRect.y"
              :width="shoulderZoneRect.width"
              :height="shoulderZoneRect.height"
              fill="rgba(59,130,246,0.06)"
              stroke="none"
            />

            <!-- Layer 4: Boundary lines -->
            <path v-if="rMinLine" :d="rMinLine" stroke="#22c55e" stroke-width="1" stroke-dasharray="4,3" opacity="0.6" />
            <path v-if="rMaxLine" :d="rMaxLine" stroke="#3b82f6" stroke-width="1" stroke-dasharray="4,3" opacity="0.6" />
            <path :d="axisPath" stroke="#94a3b8" stroke-width="1" stroke-dasharray="4,3" />

            <!-- Layer 5a: Curve path A (Catmull-Rom spline) -->
            <path
              v-if="profilePath"
              :d="profilePath"
              fill="none"
              stroke="#2563eb"
              stroke-width="2"
              stroke-linejoin="round"
              stroke-linecap="round"
            />

            <!-- Layer 5b: Curve path B (asymmetric, cyan dashed) -->
            <path
              v-if="isAsymmetric && profilePathB"
              :d="profilePathB"
              fill="none"
              stroke="#06b6d4"
              stroke-width="2"
              stroke-dasharray="6,3"
              stroke-linejoin="round"
              stroke-linecap="round"
            />

            <!-- Layer 6a: Control points A -->
            <circle
              v-for="(p, i) in points"
              :key="'a' + i"
              :cx="toSvgX(p[0])"
              :cy="toSvgY(p[1])"
              :r="dragging === i ? 8 : (isLocked(i) ? 7 : 5)"
              :fill="pointColor(i)"
              stroke="white"
              stroke-width="1.5"
              :class="['pe-point', { 'pe-locked': isLocked(i) }]"
              @pointerdown.stop="onPointerDown(i, $event)"
            />

            <!-- Layer 6b: Control points B (asymmetric, cyan) -->
            <circle
              v-for="(p, i) in pointsB"
              v-if="isAsymmetric"
              :key="'b' + i"
              :cx="toSvgX(p[0])"
              :cy="toSvgY(p[1])"
              :r="draggingB === i ? 8 : (isLocked(i) ? 6 : 4)"
              :fill="isLocked(i) ? '#f59e0b' : '#06b6d4'"
              stroke="white"
              stroke-width="1.5"
              :class="['pe-point', { 'pe-locked': isLocked(i) }]"
              @pointerdown.stop="onPointerDownB(i, $event)"
            />

            <!-- Layer 7: Drag label -->
            <text
              v-if="dragLabel"
              :x="dragLabel.x"
              :y="dragLabel.y"
              class="pe-drag-label"
            >{{ dragLabel.text }}</text>

            <!-- Axis labels -->
            <text :x="W - PAD" :y="H - PAD + 26" text-anchor="end" class="pe-axis-label">
              R (mm)
            </text>
            <text :x="PAD - 4" :y="PAD - 8" text-anchor="start" class="pe-axis-label">
              Z (mm)
            </text>
          </svg>

          <!-- Status bar -->
          <div class="pe-status" :class="'pe-status-' + status.type">
            {{ status.type === 'ok' ? '\u2713' : status.type === 'warn' ? '\u26A0' : '\u2717' }}
            {{ status.msg }}
          </div>
        </div>

        <!-- RIGHT: Controls panel -->
        <div class="pe-controls">
          <!-- Symmetry toggle (bottle only) -->
          <div v-if="constraints?.supports_asymmetric" class="pe-section">
            <div class="pe-section-title">{{ t('profile.symmetryMode') }}</div>
            <div class="pe-symmetry-toggle">
              <div
                class="pe-sym-option"
                :class="{ 'pe-sym-active': !isAsymmetric }"
                @click="toggleSymmetry('symmetric')"
              >{{ t('profile.symmetric') }}</div>
              <div
                class="pe-sym-option"
                :class="{ 'pe-sym-active': isAsymmetric }"
                @click="toggleSymmetry('asymmetric')"
              >{{ t('profile.asymmetric') }}</div>
            </div>
          </div>

          <!-- Presets -->
          <div class="pe-section">
            <div class="pe-section-title">{{ t('profile.presets') }}</div>
            <div class="pe-preset-list">
              <div
                v-for="preset in PRESETS"
                :key="preset.id"
                class="pe-preset-item"
                :class="{ 'pe-preset-active': activePreset === preset.id }"
                @click="applyPreset(preset.id)"
              >
                {{ t(preset.labelKey) }}
              </div>
            </div>
          </div>

          <!-- Control points table -->
          <div class="pe-section">
            <div class="pe-section-title">{{ t('profile.controlPoints') }}</div>
            <!-- Table header for asymmetric mode -->
            <div v-if="isAsymmetric" class="pe-table-header">
              <span class="pe-idx">#</span>
              <span class="pe-col-label">{{ t('profile.rA') }}</span>
              <span class="pe-col-label">Z</span>
              <span class="pe-col-label pe-col-b">{{ t('profile.rB') }}</span>
              <span class="pe-col-del"></span>
            </div>
            <div class="pe-table">
              <div v-for="(p, i) in points" :key="i" class="pe-row">
                <span class="pe-idx">{{ i }}</span>
                <el-input-number
                  :model-value="p[0]"
                  @update:model-value="(v: number | undefined) => v !== undefined && updatePoint(i, 0, String(v))"
                  :step="0.1"
                  :min="0.1"
                  :controls="false"
                  :disabled="isLocked(i)"
                  size="small"
                  style="width: 60px"
                  placeholder="R"
                />
                <el-input-number
                  :model-value="p[1]"
                  @update:model-value="(v: number | undefined) => v !== undefined && updatePoint(i, 1, String(v))"
                  :step="1"
                  :controls="false"
                  :disabled="isLocked(i)"
                  size="small"
                  style="width: 60px"
                  placeholder="Z"
                />
                <!-- R(B) column for asymmetric mode -->
                <el-input-number
                  v-if="isAsymmetric && pointsB[i]"
                  :model-value="pointsB[i][0]"
                  @update:model-value="(v: number | undefined) => v !== undefined && updatePointB(i, 0, String(v))"
                  :step="0.1"
                  :min="0.1"
                  :controls="false"
                  :disabled="isLocked(i)"
                  size="small"
                  style="width: 60px"
                  class="pe-input-b"
                  placeholder="R(B)"
                />
                <span v-if="isLocked(i)" class="pe-lock-icon" :title="t('profile.lockedTip')">&#128274;</span>
                <el-button
                  v-else
                  size="small"
                  type="danger"
                  text
                  @click="removePoint(i)"
                  :disabled="points.length <= 3"
                  style="padding: 4px; min-width: 24px"
                >&times;</el-button>
              </div>
            </div>
          </div>

          <!-- Buttons -->
          <div class="pe-actions">
            <el-button size="small" @click="addPoint" style="width: 100%">
              + {{ t('profile.addPoint') }}
            </el-button>
            <el-button size="small" @click="resetToDefault" style="width: 100%">
              &#8634; {{ t('profile.resetDefault') }}
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.profile-editor {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
  margin-top: 4px;
  position: relative;
}

.pe-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  background: #f8fafc;
  user-select: none;
}
.pe-header:hover {
  background: #f1f5f9;
}
.pe-toggle {
  font-size: 10px;
  width: 14px;
}

.pe-help-btn {
  margin-left: auto;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  cursor: pointer;
}
.pe-help-btn:hover {
  background: #2563eb;
  color: white;
}

.pe-help-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
}
.pe-help-content {
  background: white;
  border-radius: 12px;
  padding: 20px;
  max-width: 320px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}
.pe-help-title {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 12px;
  color: #1e293b;
}
.pe-help-list {
  font-size: 12px;
  color: #475569;
  line-height: 1.8;
  padding-left: 16px;
  margin: 0 0 12px;
}

.pe-body {
  padding: 8px;
}

.pe-layout {
  display: flex;
  gap: 12px;
}

@media (max-width: 720px) {
  .pe-layout {
    flex-direction: column;
  }
}

.pe-canvas-wrap {
  flex-shrink: 0;
}

.pe-canvas {
  display: block;
  background: #fafbfc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  cursor: crosshair;
}

.pe-point {
  cursor: grab;
  transition: r 0.1s;
}
.pe-point:hover {
  r: 7;
}
.pe-point.pe-locked {
  cursor: not-allowed;
}

.pe-axis-label {
  font-size: 10px;
  fill: #94a3b8;
}

.pe-scale-label {
  font-size: 9px;
  fill: #94a3b8;
}

.pe-drag-label {
  font-size: 10px;
  fill: #1e293b;
  font-weight: 600;
  pointer-events: none;
}

.pe-status {
  font-size: 12px;
  font-weight: 600;
  padding: 6px 10px;
  margin-top: 4px;
  border-radius: 6px;
}
.pe-status-ok {
  background: #f0fdf4;
  color: #166534;
}
.pe-status-error {
  background: #fef2f2;
  color: #991b1b;
}
.pe-status-warn {
  background: #fffbeb;
  color: #92400e;
}

.pe-controls {
  flex: 1;
  min-width: 200px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pe-section {
  background: #fafbfc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px;
}

.pe-section-title {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 8px;
}

.pe-preset-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pe-preset-item {
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  color: #475569;
  transition: all 0.15s;
}
.pe-preset-item:hover {
  background: #eff6ff;
  color: #2563eb;
}
.pe-preset-item.pe-preset-active {
  background: #2563eb;
  color: white;
  font-weight: 600;
}

.pe-table {
  max-height: 200px;
  overflow-y: auto;
}

.pe-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 3px;
}

.pe-idx {
  font-size: 11px;
  color: #94a3b8;
  width: 16px;
  text-align: center;
  flex-shrink: 0;
}

.pe-lock-icon {
  font-size: 12px;
  width: 24px;
  text-align: center;
  flex-shrink: 0;
}

.pe-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pe-symmetry-toggle {
  display: flex;
  gap: 4px;
}

.pe-sym-option {
  flex: 1;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 11px;
  text-align: center;
  cursor: pointer;
  color: #475569;
  background: #f1f5f9;
  transition: all 0.15s;
}
.pe-sym-option:hover {
  background: #e2e8f0;
}
.pe-sym-option.pe-sym-active {
  background: #2563eb;
  color: white;
  font-weight: 600;
}

.pe-table-header {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
  padding-bottom: 4px;
  border-bottom: 1px solid #e2e8f0;
}

.pe-col-label {
  font-size: 10px;
  color: #64748b;
  font-weight: 600;
  width: 60px;
  text-align: center;
}

.pe-col-b {
  color: #06b6d4;
}

.pe-col-del {
  width: 24px;
}

.pe-input-b :deep(.el-input__inner) {
  color: #06b6d4;
}
</style>
