<script setup lang="ts">
import { ref, watch, onUnmounted, nextTick, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useViewerStore } from '@/stores/viewer'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import { mergeVertices, toCreasedNormals } from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import * as api from '@/api/client'
import { useParamsStore } from '@/stores/params'
import { useAppStore } from '@/stores/app'
import { getNested } from '@/utils/nested'
import { useGenerate } from '@/composables/useGenerate'
import { updateDerivedParams } from '@/composables/useDerivedRules'
import type { DragHandle } from '@/api/types'

const { t } = useI18n()
const viewerStore = useViewerStore()
const paramsStore = useParamsStore()
const appStore = useAppStore()
const { generate } = useGenerate()

const container = ref<HTMLElement | null>(null)

// Three.js objects - NOT reactive (module-level plain variables)
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let renderer: THREE.WebGLRenderer | null = null
let controls: OrbitControls | null = null
let animFrameId: number | null = null
let initialized = false
let transformControls: TransformControls | null = null
let selectedCompId: string | null = null
const raycaster = new THREE.Raycaster()
const mouse = new THREE.Vector2()

// Session models - plain object, not reactive
const sessionModels: Record<
  string,
  { mesh: THREE.Mesh; stlUrl: string; visible: boolean; color: number; params: Record<string, any> }
> = {}
const LEGACY_RENDER_PROXY_NAMES = new Set(['__aicad_liquid_proxy', '__aicad_bottle_trim_proxy'])
const metalStripeTextureCache = new Map<string, THREE.CanvasTexture>()

const COMP_COLORS: Record<string, number> = {
  bottle: 0x4dabf7,
  wand: 0x69db7c,
  cap: 0xffa94d,
  wiper: 0xda77f2,
}

// ── 拟真渲染：材质类型 → MeshPhysicalMaterial 参数映射 ──
type PhysicalPreset = Partial<THREE.MeshPhysicalMaterialParameters> & {
  envMapIntensity?: number
  opacity?: number
}

const MATERIAL_PRESETS: Record<string, PhysicalPreset> = {
  transparent_glass: {
    transmission: 0.72,
    roughness: 0.08,
    metalness: 0,
    ior: 1.46,
    thickness: 2.4,
    transparent: true,
    opacity: 0.62,
    clearcoat: 1.0,
    clearcoatRoughness: 0.05,
    envMapIntensity: 1.05,
  },
  frosted_glass: {
    transmission: 0.36,
    roughness: 0.58,
    metalness: 0,
    ior: 1.46,
    thickness: 1.8,
    transparent: true,
    opacity: 0.78,
    clearcoat: 0.38,
    clearcoatRoughness: 0.24,
    envMapIntensity: 0.82,
  },
  glossy_plastic: {
    metalness: 0,
    roughness: 0.15,
    clearcoat: 0.5,
    clearcoatRoughness: 0.1,
    envMapIntensity: 0.85,
  },
  matte_plastic: {
    metalness: 0,
    roughness: 0.6,
    clearcoat: 0.08,
    clearcoatRoughness: 0.42,
    envMapIntensity: 0.45,
  },
  metal: {
    metalness: 0.9,
    roughness: 0.2,
    envMapIntensity: 1.1,
  },
  pearl: {
    metalness: 0.05,
    roughness: 0.25,
    iridescence: 0.42,
    iridescenceIOR: 1.3,
    sheen: 0.38,
    sheenRoughness: 0.35,
    sheenColor: new THREE.Color(0xffffff),
    clearcoat: 0.58,
    clearcoatRoughness: 0.16,
    envMapIntensity: 0.92,
  },
}

let assemblyMode: 'assembled' | 'exploded' = 'assembled'
// 防并发加载：单调递增 generation 计数器（比布尔锁更健壮）
let loadGeneration = 0

// Clipping plane - NOT reactive (Three.js object)
let clipPlane: THREE.Plane | null = null
let clipHelperMesh: THREE.Mesh | null = null
let clipBoundsMin = new THREE.Vector3()
let clipBoundsMax = new THREE.Vector3()
// BackSide clone meshes for showing cut interior
const clipBackMeshes: Record<string, THREE.Mesh> = {}

// ── Drag Handle state (NOT reactive) ──
const handleMeshes: THREE.Object3D[] = []   // arrow helpers in scene
let activeHandles: DragHandle[] = []        // current handle definitions
let draggingHandle: DragHandle | null = null
let dragStartMouse = new THREE.Vector2()
let dragOriginalValue = 0
// original scale snapshot for mesh preview during drag
let dragOriginalScale = new THREE.Vector3(1, 1, 1)
// labels overlay ref
const handleLabels = ref<{ text: string; x: number; y: number; color: string }[]>([])
// Auto-generation state (Approach B: auto-gen on close)
const autoGenerating = ref(false)
const autoGenError = ref('')

function initViewer() {
  if (initialized || !container.value) return
  const w = container.value.clientWidth
  const h = container.value.clientHeight
  if (w === 0 || h === 0) return

  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x1a1a2e)

  camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 1000)
  camera.position.set(80, 60, 80)

  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setSize(w, h)
  renderer.setPixelRatio(window.devicePixelRatio)
  renderer.localClippingEnabled = true
  // PBR 渲染增强（对 MeshPhongMaterial 无影响）
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.0
  renderer.outputColorSpace = THREE.SRGBColorSpace
  container.value.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.05

  scene.add(new THREE.AmbientLight(0xffffff, 0.5))
  const d1 = new THREE.DirectionalLight(0xffffff, 0.8)
  d1.position.set(50, 100, 50)
  scene.add(d1)
  const d2 = new THREE.DirectionalLight(0xffffff, 0.4)
  d2.position.set(-50, -50, -50)
  scene.add(d2)
  scene.add(new THREE.GridHelper(100, 20, 0x444466, 0x333355))
  scene.add(new THREE.AxesHelper(30))

  // PBR 环境光照（拟真模式的反射/折射来源）
  const pmrem = new THREE.PMREMGenerator(renderer)
  pmrem.compileEquirectangularShader()
  scene.environment = pmrem.fromScene(new RoomEnvironment()).texture
  pmrem.dispose()

  // TransformControls for drag/rotate/scale individual components
  transformControls = new TransformControls(camera, renderer.domElement)
  transformControls.setSize(0.8)
  transformControls.addEventListener('dragging-changed', (event) => {
    if (controls) controls.enabled = !event.value
  })
  scene.add(transformControls)

  renderer.domElement.addEventListener('click', onCanvasClick)
  renderer.domElement.addEventListener('pointerdown', onHandlePointerDown)
  window.addEventListener('keydown', onTransformKeydown)

  initialized = true
}

// ── TransformControls: click selection + mode switching ──

function onCanvasClick(event: MouseEvent) {
  if (!camera || !scene || !container.value) return
  if (transformControls?.dragging) return
  if (draggingHandle) return // Don't process click during handle drag

  const rect = container.value.getBoundingClientRect()
  mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1

  raycaster.setFromCamera(mouse, camera)

  // In handle mode, check if clicked on a handle first (handled by pointerdown)
  if (viewerStore.handleEditMode && handleMeshes.length > 0) {
    const hIntersects = raycaster.intersectObjects(handleMeshes, true)
    if (hIntersects.length > 0) return // handle interaction, skip component selection
  }

  const meshes = Object.entries(sessionModels)
    .filter(([, m]) => m.visible && m.mesh)
    .map(([id, m]) => ({ id, mesh: m.mesh }))

  const intersects = raycaster.intersectObjects(meshes.map((m) => m.mesh))

  if (intersects.length > 0) {
    const hit = intersects[0].object as THREE.Mesh
    const compId = hit.userData.componentId as string
    selectComponent(compId)
  } else {
    deselectComponent()
  }
}

function selectComponent(compId: string) {
  // Remove previous highlight
  if (selectedCompId && sessionModels[selectedCompId]) {
    const prev = sessionModels[selectedCompId]
    ;(prev.mesh.material as any).emissive.setHex(0x000000)
  }
  removeAllHandles()

  selectedCompId = compId
  viewerStore.selectedComponentId = compId

  const m = sessionModels[compId]
  if (m?.mesh) {
    ;(m.mesh.material as any).emissive.setHex(0x333333)
    if (!viewerStore.handleEditMode) {
      transformControls?.attach(m.mesh)
    }
  }

  // Show handles when in handle edit mode
  if (viewerStore.handleEditMode) {
    transformControls?.detach()
    showHandlesForComponent(compId)
  }
}

function deselectComponent() {
  if (selectedCompId && sessionModels[selectedCompId]) {
    const prev = sessionModels[selectedCompId]
    ;(prev.mesh.material as any).emissive.setHex(0x000000)
  }
  removeAllHandles()
  selectedCompId = null
  viewerStore.selectedComponentId = null
  transformControls?.detach()
}

function setTransformMode(mode: 'translate' | 'rotate' | 'scale') {
  if (transformControls) {
    transformControls.setMode(mode)
    viewerStore.transformMode = mode
  }
}

function onTransformKeydown(e: KeyboardEvent) {
  if (!viewerStore.modalOpen) return
  if (e.key === 'd' || e.key === 'D') toggleHandleMode()
  else if (e.key === 'w' || e.key === 'W') setTransformMode('translate')
  else if (e.key === 'e' || e.key === 'E') setTransformMode('rotate')
  else if (e.key === 'r' || e.key === 'R') setTransformMode('scale')
  else if (e.key === 'Escape') deselectComponent()
}

function onWindowResize() {
  if (!initialized || !viewerStore.modalOpen || !container.value) return
  const w = container.value.clientWidth
  const h = container.value.clientHeight
  if (w === 0 || h === 0 || !camera || !renderer) return
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  renderer.setSize(w, h)
}

function startRenderLoop() {
  if (animFrameId) return
  function animate() {
    if (!viewerStore.modalOpen) {
      animFrameId = null
      return
    }
    animFrameId = requestAnimationFrame(animate)
    if (viewerStore.autoRotate) {
      for (const compId of Object.keys(sessionModels)) {
        const m = sessionModels[compId]
        if (m.mesh && m.visible) m.mesh.rotation.z += 0.005
      }
    }
    controls?.update()
    if (viewerStore.handleEditMode && activeHandles.length > 0) updateHandleLabels()
    if (renderer && scene && camera) renderer.render(scene, camera)
  }
  animate()
}

function stopRenderLoop() {
  if (animFrameId) {
    cancelAnimationFrame(animFrameId)
    animFrameId = null
  }
}

function clampNumber(value: unknown, fallback: number, min: number, max: number): number {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return fallback
  return Math.min(max, Math.max(min, n))
}

function getRenderValue(params: Record<string, any>, componentId: string, field: string): any {
  return params[`_render_${componentId}_${field}`]
}

function getRenderNumber(
  params: Record<string, any>,
  componentId: string,
  field: string,
  fallback: number,
  min: number,
  max: number,
): number {
  return clampNumber(getRenderValue(params, componentId, field), fallback, min, max)
}

function getRenderRgb(
  params: Record<string, any>,
  componentId: string,
  field: string,
  fallback: number[] | null = null,
): number[] | null {
  const value = getRenderValue(params, componentId, field)
  if (Array.isArray(value) && value.length >= 3) {
    return [
      clampNumber(value[0], 128, 0, 255),
      clampNumber(value[1], 128, 0, 255),
      clampNumber(value[2], 128, 0, 255),
    ]
  }
  return fallback
}

function colorFromRgb(rgb: number[] | null, fallback: number): THREE.Color {
  if (!rgb) return new THREE.Color(fallback)
  return new THREE.Color(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255).convertSRGBToLinear()
}

function mixRgb(a: number[], b: number[], t: number): number[] {
  return [
    a[0] + (b[0] - a[0]) * t,
    a[1] + (b[1] - a[1]) * t,
    a[2] + (b[2] - a[2]) * t,
  ]
}

function metalStripeTexture(baseRgb: number[] | null, shadowRgb: number[] | null, highlightRgb: number[] | null) {
  const base = baseRgb || [190, 190, 190]
  const shadow = shadowRgb || mixRgb(base, [0, 0, 0], 0.45)
  const highlight = highlightRgb || mixRgb(base, [255, 255, 255], 0.55)
  const key = [...base, ...shadow, ...highlight].map((v) => Math.round(v)).join(',')
  const cached = metalStripeTextureCache.get(key)
  if (cached) return cached

  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 16
  const ctx = canvas.getContext('2d')!
  const image = ctx.createImageData(canvas.width, canvas.height)
  for (let x = 0; x < canvas.width; x++) {
    const u = x / (canvas.width - 1)
    const darkBand = Math.exp(-Math.pow((u - 0.55) / 0.055, 2))
    const brightBand = Math.exp(-Math.pow((u - 0.22) / 0.08, 2)) + 0.55 * Math.exp(-Math.pow((u - 0.82) / 0.07, 2))
    const fine = (Math.sin(u * Math.PI * 28) + 1) * 0.035
    let color = mixRgb(base, shadow, Math.min(0.82, darkBand * 0.78))
    color = mixRgb(color, highlight, Math.min(0.7, brightBand * 0.5 + fine))
    for (let y = 0; y < canvas.height; y++) {
      const i = (y * canvas.width + x) * 4
      image.data[i] = Math.round(color[0])
      image.data[i + 1] = Math.round(color[1])
      image.data[i + 2] = Math.round(color[2])
      image.data[i + 3] = 255
    }
  }
  ctx.putImageData(image, 0, 0)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.RepeatWrapping
  texture.needsUpdate = true
  metalStripeTextureCache.set(key, texture)
  return texture
}

function applyCylindricalUvs(geometry: THREE.BufferGeometry) {
  const position = geometry.attributes.position as THREE.BufferAttribute | undefined
  if (!position) return
  const box = geometry.boundingBox
    || new THREE.Box3().setFromBufferAttribute(position)
  const centerX = (box.min.x + box.max.x) * 0.5
  const centerY = (box.min.y + box.max.y) * 0.5
  const height = Math.max(0.0001, box.max.z - box.min.z)
  const uvs: number[] = []
  for (let i = 0; i < position.count; i++) {
    const x = position.getX(i) - centerX
    const y = position.getY(i) - centerY
    const z = position.getZ(i)
    const angle = Math.atan2(y, x)
    const u = 0.5 + angle / (Math.PI * 2)
    const v = (z - box.min.z) / height
    uvs.push(u, v)
  }
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2))
}

/**
 * 根据渲染模式创建材质。
 * simple: 原有 MeshPhongMaterial + 固定颜色
 * realistic: MeshPhysicalMaterial + 从 params 读取材质参数
 */
function createMaterial(componentId: string, params: Record<string, any>): THREE.Material {
  const fallbackColor = COMP_COLORS[componentId] || 0x3399ff

  if (viewerStore.renderMode !== 'realistic') {
    return new THREE.MeshPhongMaterial({
      color: fallbackColor,
      specular: 0x222222,
      shininess: 80,
      flatShading: false,
      side: THREE.DoubleSide,
    })
  }

  // 拟真模式
  const materialType: string = getRenderValue(params, componentId, 'material') || 'glossy_plastic'
  const preset = MATERIAL_PRESETS[materialType] || MATERIAL_PRESETS.glossy_plastic
  const colorRgb = getRenderRgb(
    params,
    componentId,
    'base_color_rgb',
    getRenderRgb(params, componentId, 'color_rgb'),
  )
  const shadowRgb = getRenderRgb(params, componentId, 'shadow_color_rgb')
  const highlightRgb = getRenderRgb(params, componentId, 'highlight_color_rgb')
  const attenuationRgb = getRenderRgb(params, componentId, 'attenuation_color_rgb', colorRgb)
  const roughnessFallback = clampNumber(preset.roughness, 0.25, 0.02, 1)
  const metalnessFallback = clampNumber(preset.metalness, 0, 0, 1)
  const clearcoatFallback = clampNumber((preset as any).clearcoat, 0, 0, 1)
  const clearcoatRoughnessFallback = clampNumber((preset as any).clearcoatRoughness, 0.15, 0, 1)
  const transmissionFallback = clampNumber((preset as any).transmission, 0, 0, 1)
  const opacityFallback = clampNumber(preset.opacity, 1, 0.05, 1)
  const opacity = getRenderNumber(params, componentId, 'opacity', opacityFallback, 0.05, 1)
  const transmission = getRenderNumber(params, componentId, 'transmission', transmissionFallback, 0, 1)

  const materialParams = {
    ...preset,
    color: materialType === 'metal' ? new THREE.Color(0xffffff) : colorFromRgb(colorRgb, fallbackColor),
    map: materialType === 'metal' ? metalStripeTexture(colorRgb, shadowRgb, highlightRgb) : null,
    side: THREE.DoubleSide,
    roughness: getRenderNumber(params, componentId, 'roughness', roughnessFallback, 0.02, 1),
    metalness: getRenderNumber(params, componentId, 'metalness', metalnessFallback, 0, 1),
    clearcoat: getRenderNumber(params, componentId, 'clearcoat', clearcoatFallback, 0, 1),
    clearcoatRoughness: getRenderNumber(
      params,
      componentId,
      'clearcoat_roughness',
      clearcoatRoughnessFallback,
      0,
      1,
    ),
    transmission,
    ior: getRenderNumber(params, componentId, 'ior', clampNumber((preset as any).ior, 1.46, 1, 2.33), 1, 2.33),
    thickness: getRenderNumber(params, componentId, 'thickness', clampNumber((preset as any).thickness, 1.2, 0, 12), 0, 12),
    attenuationColor: colorFromRgb(attenuationRgb, fallbackColor),
    attenuationDistance: getRenderNumber(params, componentId, 'attenuation_distance', 24, 1, 80),
    iridescence: getRenderNumber(params, componentId, 'iridescence', clampNumber((preset as any).iridescence, 0, 0, 1), 0, 1),
    sheen: getRenderNumber(params, componentId, 'sheen', clampNumber((preset as any).sheen, 0, 0, 1), 0, 1),
    sheenRoughness: getRenderNumber(
      params,
      componentId,
      'sheen_roughness',
      clampNumber((preset as any).sheenRoughness, 0.5, 0, 1),
      0,
      1,
    ),
    envMapIntensity: getRenderNumber(params, componentId, 'env_intensity', preset.envMapIntensity ?? 0.75, 0, 2),
    transparent: opacity < 0.999 || transmission > 0.001,
    opacity,
    depthWrite: !(opacity < 0.72 || transmission > 0.15),
  } as THREE.MeshPhysicalMaterialParameters & Record<string, any>

  const material = new THREE.MeshPhysicalMaterial(materialParams)
  material.needsUpdate = true
  return material
}

function disposeMeshTree(root: THREE.Object3D) {
  root.traverse((child) => {
    const mesh = child as THREE.Mesh
    if (!mesh.isMesh) return
    mesh.geometry?.dispose()
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
    for (const material of materials) material?.dispose()
  })
}

function removeRenderGeometryProxies(parent: THREE.Mesh) {
  const existing = parent.children.filter((child) => LEGACY_RENDER_PROXY_NAMES.has(child.name))
  for (const child of existing) {
    parent.remove(child)
    disposeMeshTree(child)
  }
}

function enforceMaterialOnlyRendering(componentId: string) {
  const model = sessionModels[componentId]
  if (!model?.mesh) return
  removeRenderGeometryProxies(model.mesh)
}

function loadOneSTL(url: string, componentId: string, params: Record<string, any>): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!scene) {
      reject(new Error('Scene not initialized'))
      return
    }

    // Remove old model
    if (sessionModels[componentId]) {
      const old = sessionModels[componentId]
      if (old.mesh) {
        scene.remove(old.mesh)
        disposeMeshTree(old.mesh)
      }
      delete sessionModels[componentId]
    }
    // Also remove clip back-mesh if clipping was active (prevent ghost mesh)
    if (clipBackMeshes[componentId]) {
      scene.remove(clipBackMeshes[componentId])
      ;(clipBackMeshes[componentId].material as THREE.Material).dispose()
      delete clipBackMeshes[componentId]
    }

    const color = COMP_COLORS[componentId] || 0x3399ff
    const loader = new STLLoader()

    loader.load(
      url,
      (rawGeometry) => {
        // STL 格式每个三角形独立（无共享顶点），法线为面法线 → 弯曲表面显示条带
        // toCreasedNormals: 面间角度 < creaseAngle → 共享顶点+平滑法线（消除条带）
        //                   面间角度 ≥ creaseAngle → 保留独立法线（保持锐边）
        // Math.PI/6 (30°) 是常用阈值，足够平滑曲面同时保留瓶口/底部等锐边
        const geometry = toCreasedNormals(rawGeometry, Math.PI / 6)
        geometry.computeBoundingBox()
        applyCylindricalUvs(geometry)
        // 不调用 geometry.center() — 保留CadQuery原始坐标系
        // 装配定位由 autoAssemble() 通过精确参数计算完成
        const material = createMaterial(componentId, params)
        const newMesh = new THREE.Mesh(geometry, material)
        newMesh.userData.componentId = componentId
        newMesh.scale.set(0.5, 0.5, 0.5)
        scene!.add(newMesh)

        sessionModels[componentId] = { mesh: newMesh, stlUrl: url, visible: true, color, params }
        enforceMaterialOnlyRendering(componentId)
        viewerStore.addModel(componentId, color)
        resolve(componentId)
      },
      undefined,
      (err) => {
        console.error('STL load error:', componentId, err)
        reject(err)
      },
    )
  })
}

function fitCameraToModels() {
  if (!initialized || !camera || !controls) return
  const box = new THREE.Box3()
  let hasModels = false
  for (const compId of Object.keys(sessionModels)) {
    const m = sessionModels[compId]
    if (m.mesh && m.visible) {
      box.expandByObject(m.mesh)
      hasModels = true
    }
  }
  if (!hasModels) {
    resetCamera()
    return
  }
  const center = box.getCenter(new THREE.Vector3())
  const size = box.getSize(new THREE.Vector3())
  const maxDim = Math.max(size.x, size.y, size.z)
  const distance = maxDim * 2
  camera.position.set(center.x + distance, center.y + distance * 0.6, center.z + distance)
  camera.lookAt(center)
  controls.target.copy(center)
  controls.update()
}

async function autoAssemble() {
  // 装配定位：每次都从后端 /api/assembly 获取最新位置
  // 后端 state_mgr 持有所有已生成组件的完整参数，计算结果最可靠
  // CadQuery Z轴 → Three.js Y轴（通过 -π/2 旋转）
  // mesh.position.y = dz * scale

  // Deselect any selected component (reset transform gizmo)
  deselectComponent()

  const scale = 0.5
  const compIds = Object.keys(sessionModels)
  if (compIds.length === 0) return

  // 重置变换（旋转 + 缩放）— 拖拽编辑会修改 scale，必须在定位前恢复
  for (const compId of compIds) {
    const m = sessionModels[compId]
    if (m?.mesh) {
      m.mesh.rotation.set(0, 0, 0)
      m.mesh.scale.set(scale, scale, scale)
    }
  }

  // 装配位置：优先使用 store 中已缓存的（展览馆等场景直接传入），否则从后端获取
  let positions: Record<string, { dz: number }> = {}
  if (assemblyMode === 'assembled') {
    const cached = viewerStore.assemblyPositions
    if (Object.keys(cached).length > 0) {
      positions = cached
      console.log('[Assembly] Using cached positions:', positions)
    } else {
      try {
        const report = await api.fetchAssemblyReport(compIds)
        positions = report.positions || {}
        console.log('[Assembly] Backend positions (components=' + compIds.join(',') + '):', positions)
      } catch (e) {
        console.warn('[Assembly] Failed to fetch positions, using dz=0:', e)
      }
    }
  }

  if (assemblyMode === 'assembled') {
    for (const compId of compIds) {
      const model = sessionModels[compId]
      if (!model?.mesh) continue

      const pos = positions[compId]
      const dz = pos ? pos.dz : 0
      console.log(`[Assembly] ${compId}: dz=${dz}mm → Y=${(dz * scale).toFixed(1)}`)

      model.mesh.position.set(0, dz * scale, 0)
      model.mesh.rotation.set(-Math.PI / 2, 0, 0)
    }
  } else {
    // 爆炸视图：获取瓶身高度用于布局
    const bP = sessionModels['bottle']?.params || {}
    const bottleH = getNested(bP, 'height_mm', 70) as number
    const spacing = 20
    let idx = 0
    for (const compId of compIds) {
      const model = sessionModels[compId]
      if (!model?.mesh) continue

      if (compId === 'bottle') {
        model.mesh.position.set(0, 0, 0)
      } else {
        const xOffset = (idx - 1) * 30
        model.mesh.position.set(xOffset * scale, (bottleH + spacing) * scale, 0)
        idx++
      }
      model.mesh.rotation.set(-Math.PI / 2, 0, 0)
    }
  }
  fitCameraToModels()
}

// Public actions
function resetCamera() {
  if (!initialized || !camera || !controls) return
  camera.position.set(80, 60, 80)
  camera.lookAt(0, 0, 0)
  controls.reset()
}

function toggleWireframe() {
  viewerStore.wireframeMode = !viewerStore.wireframeMode
  for (const compId of Object.keys(sessionModels)) {
    const m = sessionModels[compId]
    if (m.mesh?.material) (m.mesh.material as any).wireframe = viewerStore.wireframeMode
  }
}

function toggleRenderMode() {
  viewerStore.renderMode = viewerStore.renderMode === 'simple' ? 'realistic' : 'simple'
  // 重建所有已加载模型的材质
  for (const compId of Object.keys(sessionModels)) {
    const m = sessionModels[compId]
    if (!m?.mesh) continue
    const oldMat = m.mesh.material as THREE.Material
    const newMat = createMaterial(compId, m.params)
    m.mesh.material = newMat
    if (viewerStore.wireframeMode && 'wireframe' in newMat) {
      ;(newMat as any).wireframe = true
    }
    oldMat.dispose()
    enforceMaterialOnlyRendering(compId)
  }
  // 同步裁剪面
  if (viewerStore.clipEnabled) {
    disableClip()
    enableClip()
  }
}

function toggleAutoRotate() {
  viewerStore.autoRotate = !viewerStore.autoRotate
}

// ── Clipping plane logic ──

function getModelsBoundingBox(): THREE.Box3 {
  const box = new THREE.Box3()
  for (const compId of Object.keys(sessionModels)) {
    const m = sessionModels[compId]
    if (m.mesh && m.visible) box.expandByObject(m.mesh)
  }
  return box
}

function toggleClip() {
  viewerStore.clipEnabled = !viewerStore.clipEnabled
  if (viewerStore.clipEnabled) {
    enableClip()
  } else {
    disableClip()
  }
}

function enableClip() {
  if (!clipPlane) clipPlane = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0)

  // Compute bounds from all models
  const box = getModelsBoundingBox()
  if (box.isEmpty()) return
  clipBoundsMin.copy(box.min)
  clipBoundsMax.copy(box.max)

  // Apply clipping to each model: FrontSide for exterior, BackSide clone for interior
  for (const compId of Object.keys(sessionModels)) {
    const m = sessionModels[compId]
    const mat = m.mesh?.material as any
    if (!mat) continue

    // Switch main mesh to FrontSide only
    mat.side = THREE.FrontSide
    mat.clippingPlanes = [clipPlane]
    mat.clipShadows = true

    // Create BackSide clone for interior walls (darker color)
    if (!clipBackMeshes[compId] && scene && m.mesh) {
      let backMat: THREE.Material
      if (viewerStore.renderMode === 'realistic' && mat.isMeshPhysicalMaterial) {
        backMat = mat.clone()
        ;(backMat as any).side = THREE.BackSide
        ;(backMat as any).color = new THREE.Color((backMat as any).color).multiplyScalar(0.45)
        ;(backMat as any).clippingPlanes = [clipPlane]
        ;(backMat as any).clipShadows = true
      } else {
        backMat = new THREE.MeshPhongMaterial({
          color: new THREE.Color(m.color).multiplyScalar(0.45),
          specular: 0x111111,
          shininess: 40,
          side: THREE.BackSide,
          clippingPlanes: [clipPlane],
          clipShadows: true,
        })
      }
      const backMesh = new THREE.Mesh(m.mesh.geometry, backMat)
      // Sync transform with the original mesh
      backMesh.position.copy(m.mesh.position)
      backMesh.rotation.copy(m.mesh.rotation)
      backMesh.scale.copy(m.mesh.scale)
      backMesh.userData.isClipBack = true
      scene.add(backMesh)
      clipBackMeshes[compId] = backMesh
    }
  }

  // Create helper plane visualization
  createClipHelper()
  updateClipPlane()
}

function disableClip() {
  // Restore materials and remove BackSide clones
  for (const compId of Object.keys(sessionModels)) {
    const mat = sessionModels[compId].mesh?.material as any
    if (mat) {
      mat.clippingPlanes = []
      mat.side = THREE.DoubleSide
    }
  }
  removeClipBackMeshes()
  removeClipHelper()
}

function removeClipBackMeshes() {
  for (const compId of Object.keys(clipBackMeshes)) {
    const bm = clipBackMeshes[compId]
    if (bm && scene) {
      scene.remove(bm)
      ;(bm.material as THREE.Material).dispose()
      // Don't dispose geometry — shared with original mesh
    }
    delete clipBackMeshes[compId]
  }
}

function createClipHelper() {
  removeClipHelper()
  if (!scene) return
  const size = clipBoundsMax.clone().sub(clipBoundsMin)
  // Size the helper to the perpendicular dimensions, not the full bounding box
  const dimA = Math.max(size.x, size.y, size.z) * 0.8
  const geo = new THREE.PlaneGeometry(dimA, dimA)
  const mat = new THREE.MeshBasicMaterial({
    color: 0xff4444,
    transparent: true,
    opacity: 0.08,
    side: THREE.DoubleSide,
    depthWrite: false,
  })
  clipHelperMesh = new THREE.Mesh(geo, mat)
  clipHelperMesh.renderOrder = 999
  scene.add(clipHelperMesh)
}

function removeClipHelper() {
  if (clipHelperMesh && scene) {
    scene.remove(clipHelperMesh)
    clipHelperMesh.geometry.dispose()
    ;(clipHelperMesh.material as THREE.Material).dispose()
    clipHelperMesh = null
  }
}

function setClipAxis(axis: 'x' | 'y' | 'z') {
  viewerStore.clipAxis = axis
  if (viewerStore.clipEnabled) updateClipPlane()
}

function onClipSlider(val: number) {
  viewerStore.clipPosition = val
  if (viewerStore.clipEnabled) updateClipPlane()
}

function flipClip() {
  viewerStore.clipFlip = !viewerStore.clipFlip
  if (viewerStore.clipEnabled) updateClipPlane()
}

function updateClipPlane() {
  if (!clipPlane) return
  const axis = viewerStore.clipAxis
  const pct = viewerStore.clipPosition / 100
  const flip = viewerStore.clipFlip ? -1 : 1

  // Normal vector based on axis
  const normal = new THREE.Vector3(
    axis === 'x' ? -1 * flip : 0,
    axis === 'y' ? -1 * flip : 0,
    axis === 'z' ? -1 * flip : 0,
  )
  clipPlane.normal.copy(normal)

  // Position along the axis: interpolate between bounds min and max
  const lo = axis === 'x' ? clipBoundsMin.x : axis === 'y' ? clipBoundsMin.y : clipBoundsMin.z
  const hi = axis === 'x' ? clipBoundsMax.x : axis === 'y' ? clipBoundsMax.y : clipBoundsMax.z
  const pos = lo + (hi - lo) * pct
  clipPlane.constant = pos * flip

  // Sync BackSide mesh transforms with originals
  for (const compId of Object.keys(clipBackMeshes)) {
    const orig = sessionModels[compId]?.mesh
    const back = clipBackMeshes[compId]
    if (orig && back) {
      back.position.copy(orig.position)
      back.rotation.copy(orig.rotation)
      back.scale.copy(orig.scale)
    }
  }

  // Update helper mesh position and rotation
  if (clipHelperMesh) {
    const center = clipBoundsMin.clone().add(clipBoundsMax).multiplyScalar(0.5)
    if (axis === 'x') {
      clipHelperMesh.position.set(pos, center.y, center.z)
      clipHelperMesh.rotation.set(0, Math.PI / 2, 0)
    } else if (axis === 'y') {
      clipHelperMesh.position.set(center.x, pos, center.z)
      clipHelperMesh.rotation.set(Math.PI / 2, 0, 0)
    } else {
      clipHelperMesh.position.set(center.x, center.y, pos)
      clipHelperMesh.rotation.set(0, 0, 0)
    }
  }
}

// ── Drag Handle logic ──

function toggleHandleMode() {
  viewerStore.handleEditMode = !viewerStore.handleEditMode
  if (viewerStore.handleEditMode) {
    // If a component is already selected, show handles for it
    if (selectedCompId) showHandlesForComponent(selectedCompId)
  } else {
    removeAllHandles()
  }
}

async function showHandlesForComponent(compId: string) {
  if (!viewerStore.handleEditMode || !scene) return
  removeAllHandles()
  const model = sessionModels[compId]
  if (!model) return

  // Fetch handle definitions from backend
  const handles = await api.fetchDragHandles(compId, model.params)
  if (handles.length === 0) return
  activeHandles = handles

  const scale = 0.5 // same scale as mesh
  for (const h of handles) {
    // CadQuery coords (Z-up) — arrow is added to mesh which has rotation applied
    const origin = new THREE.Vector3(h.position[0], h.position[1], h.position[2])
    const dir = new THREE.Vector3(h.axis[0], h.axis[1], h.axis[2]).normalize()
    const arrowLen = 8
    const arrowColor = new THREE.Color(h.color)
    const arrow = new THREE.ArrowHelper(dir, origin, arrowLen, arrowColor, 3, 2)
    arrow.userData.handleId = h.id
    arrow.userData.isHandle = true
    // Render on top
    arrow.renderOrder = 900
    arrow.traverse((child) => {
      if ((child as THREE.Mesh).material) {
        const mat = (child as THREE.Mesh).material as THREE.Material
        mat.depthTest = false
        mat.transparent = true
      }
    })
    // Add to mesh as child (inherits position/rotation/scale)
    model.mesh.add(arrow)
    handleMeshes.push(arrow)
  }
  updateHandleLabels()
}

function removeAllHandles() {
  for (const h of handleMeshes) {
    h.parent?.remove(h)
    h.traverse((child) => {
      if ((child as THREE.Mesh).geometry) (child as THREE.Mesh).geometry.dispose()
      if ((child as THREE.Mesh).material) {
        const mat = (child as THREE.Mesh).material
        if (Array.isArray(mat)) mat.forEach((m) => m.dispose())
        else (mat as THREE.Material).dispose()
      }
    })
  }
  handleMeshes.length = 0
  activeHandles = []
  handleLabels.value = []
}

function updateHandleLabels() {
  if (!camera || !container.value || activeHandles.length === 0 || !selectedCompId) {
    handleLabels.value = []
    return
  }
  const model = sessionModels[selectedCompId]
  if (!model) { handleLabels.value = []; return }

  const rect = container.value.getBoundingClientRect()
  const labels: typeof handleLabels.value = []

  for (const h of activeHandles) {
    // Get world position of handle tip
    const localPos = new THREE.Vector3(
      h.position[0] + h.axis[0] * 10,
      h.position[1] + h.axis[1] * 10,
      h.position[2] + h.axis[2] * 10,
    )
    // Transform from mesh local to world
    const worldPos = localPos.clone()
    model.mesh.localToWorld(worldPos)
    // Project to screen
    const projected = worldPos.clone().project(camera!)
    const x = (projected.x * 0.5 + 0.5) * rect.width
    const y = (-projected.y * 0.5 + 0.5) * rect.height

    // Get current value (may be modified by drag)
    const pending = viewerStore.pendingParamChanges[selectedCompId]
    const currentVal = pending?.[h.paramKey] ?? h.currentValue
    const colorHex = '#' + h.color.toString(16).padStart(6, '0')

    labels.push({
      text: `${currentVal.toFixed(1)}mm`,
      x,
      y,
      color: colorHex,
    })
  }
  handleLabels.value = labels
}

function onHandlePointerDown(event: PointerEvent) {
  if (!viewerStore.handleEditMode || !camera || !container.value || activeHandles.length === 0) return
  if (!selectedCompId) return

  const rect = container.value.getBoundingClientRect()
  mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(mouse, camera)

  // Check intersection with handle meshes
  const intersects = raycaster.intersectObjects(handleMeshes, true)
  if (intersects.length === 0) return

  // Find which handle was hit
  let hitObj: THREE.Object3D | null = intersects[0].object
  while (hitObj && !hitObj.userData.isHandle) hitObj = hitObj.parent
  if (!hitObj) return

  const handleId = hitObj.userData.handleId
  const handle = activeHandles.find((h) => h.id === handleId)
  if (!handle) return

  event.preventDefault()
  event.stopPropagation()

  draggingHandle = handle
  dragStartMouse.set(event.clientX, event.clientY)
  const pending = viewerStore.pendingParamChanges[selectedCompId]
  dragOriginalValue = pending?.[handle.paramKey] ?? handle.currentValue

  // Snapshot original mesh scale
  const model = sessionModels[selectedCompId]
  if (model?.mesh) {
    dragOriginalScale.copy(model.mesh.scale)
  }

  // Disable orbit controls during drag
  if (controls) controls.enabled = false

  // Listen for move and up on window
  window.addEventListener('pointermove', onHandleDrag)
  window.addEventListener('pointerup', onHandleDragEnd)
}

function onHandleDrag(event: PointerEvent) {
  if (!draggingHandle || !selectedCompId || !container.value) return

  const rect = container.value.getBoundingClientRect()
  // Pixels moved
  const dx = event.clientX - dragStartMouse.x
  const dy = -(event.clientY - dragStartMouse.y) // screen Y is inverted

  // Convert pixel delta to parameter delta
  // Use a sensitivity factor: ~0.15 mm per pixel
  const sensitivity = 0.15
  const axisMag = Math.abs(draggingHandle.axis[0]) + Math.abs(draggingHandle.axis[1]) + Math.abs(draggingHandle.axis[2])
  // For radial (X-axis): use dx; for vertical (Z-axis): use dy
  let pixelDelta: number
  if (draggingHandle.scaleAxis === 'z') {
    pixelDelta = dy
  } else {
    pixelDelta = dx
  }
  const paramDelta = pixelDelta * sensitivity

  // Clamp to [min, max]
  let newValue = dragOriginalValue + paramDelta
  newValue = Math.max(draggingHandle.min, Math.min(draggingHandle.max, newValue))
  newValue = Math.round(newValue * 10) / 10 // round to 0.1

  // Store pending param
  viewerStore.storePendingParam(selectedCompId, draggingHandle.paramKey, newValue)

  // Apply instant mesh scale preview
  const model = sessionModels[selectedCompId]
  if (model?.mesh && dragOriginalValue > 0) {
    const ratio = newValue / dragOriginalValue
    if (draggingHandle.scaleAxis === 'z') {
      // CadQuery Z-up → mesh local Z
      model.mesh.scale.set(
        dragOriginalScale.x,
        dragOriginalScale.y,
        dragOriginalScale.z * ratio,
      )
    } else {
      // XY radial scale
      model.mesh.scale.set(
        dragOriginalScale.x * ratio,
        dragOriginalScale.y * ratio,
        dragOriginalScale.z,
      )
    }
  }

  updateHandleLabels()
}

function onHandleDragEnd(_event: PointerEvent) {
  draggingHandle = null
  if (controls) controls.enabled = true
  window.removeEventListener('pointermove', onHandleDrag)
  window.removeEventListener('pointerup', onHandleDragEnd)
}

function cleanupAndClose() {
  removeAllHandles()
  deselectComponent()
  stopRenderLoop()
  viewerStore.handleEditMode = false
  viewerStore.modalOpen = false
}

async function applyPendingParamsAndClose() {
  if (!viewerStore.hasPendingParamChanges()) {
    cleanupAndClose()
    return
  }

  const currentCompId = appStore.componentId
  const changes = viewerStore.getPendingParams()
  const compChanges = currentCompId ? changes[currentCompId] : null

  if (!compChanges || Object.keys(compChanges).length === 0) {
    // Changes are for a different component — discard and restore mesh scales
    for (const [cid] of Object.entries(changes)) {
      const m = sessionModels[cid]
      if (m?.mesh) m.mesh.scale.set(0.5, 0.5, 0.5)
    }
    viewerStore.clearPendingParams()
    cleanupAndClose()
    return
  }

  // 1. Write core params to paramsStore
  for (const [key, val] of Object.entries(compChanges)) {
    paramsStore.setParam(key, val)
  }

  // 2. Recalculate derived params for each changed core param
  for (const key of Object.keys(compChanges)) {
    updateDerivedParams(currentCompId!, key, paramsStore.values, paramsStore.setParam)
  }

  viewerStore.clearPendingParams()
  console.log('[Handles] Params + derived recalculated:', compChanges)

  // 3. Auto-generate (Approach B)
  autoGenerating.value = true
  autoGenError.value = ''

  try {
    const result = await generate({ silent: true })

    if (result.error || result.response?.ok === false) {
      autoGenerating.value = false
      autoGenError.value = result.error || result.response?.error || t('ui.genFailed')
      return // Don't close — show error popup
    }

    // Success — the generate() already stored pendingSTL in viewerStore,
    // the watcher will auto-load the new mesh. Wait briefly then close.
    autoGenerating.value = false
    await new Promise(r => setTimeout(r, 300))
    cleanupAndClose()
  } catch (e: any) {
    autoGenerating.value = false
    autoGenError.value = String(e)
  }
}

function dismissAutoGenError() {
  autoGenError.value = ''
  cleanupAndClose()
}

function stayAndAdjust() {
  autoGenError.value = ''
}

function toggleModelVisibility(compId: string) {
  const m = sessionModels[compId]
  if (!m) return
  m.visible = !m.visible
  if (m.mesh) m.mesh.visible = m.visible
  viewerStore.toggleVisibility(compId)
}

function removeModel(compId: string) {
  const m = sessionModels[compId]
  if (!m) return
  if (m.mesh && scene) {
    scene.remove(m.mesh)
    disposeMeshTree(m.mesh)
  }
  delete sessionModels[compId]
  viewerStore.removeModelMeta(compId)
  fitCameraToModels()
}

async function clearAllModels() {
  purgeScene()
  viewerStore.clearAll()

  try {
    await api.deleteAllGenerated()
  } catch {}

  paramsStore.setCrossConstraints({})
  closeModal()
}

async function toggleAssemblyModeUI() {
  assemblyMode = assemblyMode === 'assembled' ? 'exploded' : 'assembled'
  viewerStore.assemblyMode = assemblyMode
  await autoAssemble()
}

function closeModal() {
  if (autoGenerating.value) return // Can't close during auto-generation
  if (autoGenError.value) {
    dismissAutoGenError()
    return
  }
  applyPendingParamsAndClose()
}

// Component list for assembly panel
const assemblyList = computed(() =>
  viewerStore.sessionModelIds.map((id) => ({
    id,
    color: '#' + (viewerStore.modelColors[id] || 0x3399ff).toString(16).padStart(6, '0'),
    visible: viewerStore.modelVisibility[id] !== false,
    name: t(`components.${id}`, id),
  })),
)

/**
 * 彻底清空 Three.js 场景中的所有模型（sessionModels + clipBackMeshes）。
 * 只操作 Three.js 对象，不碰 Pinia store（调用方自行处理 store）。
 */
function purgeScene() {
  // 清理 clipBackMeshes
  for (const cid of Object.keys(clipBackMeshes)) {
    if (scene) scene.remove(clipBackMeshes[cid])
    ;(clipBackMeshes[cid].material as THREE.Material).dispose()
    clipBackMeshes[cid].geometry.dispose()
    delete clipBackMeshes[cid]
  }
  // 清理 sessionModels
  for (const cid of Object.keys(sessionModels)) {
    const m = sessionModels[cid]
    if (m.mesh && scene) {
      scene.remove(m.mesh)
      disposeMeshTree(m.mesh)
    }
    delete sessionModels[cid]
    viewerStore.removeModelMeta(cid)
  }
  // 重置 clip 状态
  if (clipHelperMesh && scene) { scene.remove(clipHelperMesh) }
  clipHelperMesh = null
  viewerStore.clipEnabled = false
  // 取消选中
  deselectComponent()
  console.log('[Viewer] purgeScene done')
}

/**
 * 加载所有 pendingSTLs 并执行装配。
 * 使用 generation 计数器防止并发/过时加载。
 * @param clearOld 为 true 时先清空场景（展览馆等场景）
 */
async function performLoadPending(clearOld: boolean) {
  const pendingKeys = Object.keys(viewerStore.pendingSTLs)
  if (pendingKeys.length === 0) return

  const myGen = ++loadGeneration

  // 显式标志检测：由 clearAll() 设置，用于展览馆等需要全量替换的场景
  if (viewerStore.clearSceneOnNextLoad) {
    clearOld = true
    viewerStore.clearSceneOnNextLoad = false
  }

  // ★ 全量加载时重置装配模式（Gallery 等场景应始终显示装配视图）
  if (clearOld) {
    assemblyMode = 'assembled'
    viewerStore.assemblyMode = 'assembled'
  }

  console.log(`[Viewer] performLoadPending gen=${myGen}, clear=${clearOld}, keys=${pendingKeys}`)

  if (clearOld) purgeScene()

  viewerStore.isLoading = true
  viewerStore.loadingProgress = 0
  let loaded = 0

  for (const compId of pendingKeys) {
    // 如果有新的加载请求覆盖了本次，中止
    if (loadGeneration !== myGen) {
      console.warn(`[Viewer] gen=${myGen} aborted (superseded by gen=${loadGeneration})`)
      return
    }
    const info = viewerStore.pendingSTLs[compId]
    if (!info) continue
    try {
      await loadOneSTL(info.url, compId, info.params)
    } catch (e) {
      console.error('[Viewer] STL load failed:', compId, e)
    }
    loaded++
    viewerStore.loadingProgress = Math.round((loaded / pendingKeys.length) * 100)
  }

  // 再次检查 generation（异步操作期间可能有新请求）
  if (loadGeneration !== myGen) return

  viewerStore.clearPending()
  viewerStore.isLoading = false

  await autoAssemble()
  console.log(`[Viewer] performLoadPending gen=${myGen} done, models:`, Object.keys(sessionModels))
}

// ━━ Watch: modal open/close ━━
watch(
  () => viewerStore.modalOpen,
  async (open) => {
    if (open) {
      await nextTick()
      if (!initialized && container.value) {
        await new Promise((r) => requestAnimationFrame(r))
        initViewer()
      }

      // 有 pendingSTLs 时执行加载
      // clearOld=false：保留已有组件，只追加新生成的组件
      // （purgeScene 会清除 sessionModelIds 导致其他组件消失）
      const hasPending = Object.keys(viewerStore.pendingSTLs).length > 0
      if (hasPending) {
        await performLoadPending(false)
      }

      onWindowResize()
      // 如果没有 pending（纯开启已有模型的 modal），执行装配
      if (!hasPending && Object.keys(sessionModels).length > 0) {
        await autoAssemble()
      }
      startRenderLoop()
    } else {
      stopRenderLoop()
    }
  },
)

// ━━ Watch: new pending STLs while modal is already open ━━
// 仅用于：modal 已打开后，用户在别处又触发了生成（如普通工作流）
watch(
  () => viewerStore.hasPending,
  async (hasPending) => {
    if (!hasPending || !viewerStore.modalOpen || !initialized) return
    // 等一个 tick 让 modalOpen watcher 先执行（如果同时触发）
    await nextTick()
    // 若 modalOpen watcher 已经在处理或即将处理，不重复
    if (Object.keys(viewerStore.pendingSTLs).length === 0) return
    await performLoadPending(false)
  },
)

// Clean up
onUnmounted(() => {
  stopRenderLoop()
  if (transformControls) {
    transformControls.dispose()
    transformControls = null
  }
  if (renderer) {
    renderer.domElement.removeEventListener('click', onCanvasClick)
    renderer.domElement.removeEventListener('pointerdown', onHandlePointerDown)
    renderer.dispose()
    renderer = null
  }
  window.removeEventListener('keydown', onTransformKeydown)
  window.removeEventListener('resize', onWindowResize)
})

// Listen for window resize
if (typeof window !== 'undefined') {
  window.addEventListener('resize', onWindowResize)
}
</script>

<template>
  <Teleport to="body">
    <!-- Backdrop -->
    <div
      v-show="viewerStore.modalOpen"
      class="viewer-modal-backdrop"
      @click="closeModal"
    ></div>

    <!-- Modal -->
    <div v-show="viewerStore.modalOpen" class="viewer-modal">
      <div class="viewer-modal-header">
        <span>{{ t('ui.modal3dTitle') }}</span>
        <button class="viewer-modal-close" @click="closeModal">&times;</button>
      </div>
      <div class="viewer-modal-body">
        <div ref="container" id="viewer3d">
          <div class="viewer-info">
            {{ viewerStore.handleEditMode ? t('ui.handlesTip') : t('ui.viewerTip') }}
          </div>

          <!-- Handle value labels (HTML overlay) -->
          <div
            v-for="(lbl, idx) in handleLabels"
            :key="idx"
            class="handle-label"
            :style="{ left: lbl.x + 'px', top: lbl.y + 'px', borderColor: lbl.color, color: lbl.color }"
          >{{ lbl.text }}</div>

          <!-- Controls -->
          <div class="viewer-controls">
            <button @click="resetCamera">{{ t('ui.btnResetView') }}</button>
            <button @click="toggleWireframe">{{ t('ui.btnWireframe') }}</button>
            <button @click="toggleAutoRotate">{{ t('ui.btnAutoRotate') }}</button>
            <span class="ctrl-separator"></span>
            <button
              :class="{ 'ctrl-active': viewerStore.transformMode === 'translate' }"
              @click="setTransformMode('translate')"
              title="W"
            >{{ t('ui.btnMove') }}</button>
            <button
              :class="{ 'ctrl-active': viewerStore.transformMode === 'rotate' }"
              @click="setTransformMode('rotate')"
              title="E"
            >{{ t('ui.btnRotate') }}</button>
            <button
              :class="{ 'ctrl-active': viewerStore.transformMode === 'scale' }"
              @click="setTransformMode('scale')"
              title="R"
            >{{ t('ui.btnScale') }}</button>
            <span class="ctrl-separator"></span>
            <button
              :class="{ 'ctrl-active': viewerStore.clipEnabled }"
              @click="toggleClip"
            >{{ t('ui.btnClip') }}</button>
            <span class="ctrl-separator"></span>
            <button
              :class="{ 'ctrl-active': viewerStore.handleEditMode }"
              @click="toggleHandleMode"
              title="D"
            >{{ t('ui.btnHandles') }}</button>
            <span class="ctrl-separator"></span>
            <button
              :class="{ 'ctrl-active': viewerStore.renderMode === 'realistic' }"
              @click="toggleRenderMode"
            >{{ viewerStore.renderMode === 'realistic' ? t('ui.btnRealistic') : t('ui.btnSimple') }}</button>
          </div>

          <!-- Clip controls panel -->
          <div v-if="viewerStore.clipEnabled" class="clip-panel">
            <div class="clip-axis-row">
              <span class="clip-label">{{ t('ui.clipAxis') }}</span>
              <button
                v-for="ax in (['x','y','z'] as const)"
                :key="ax"
                :class="['clip-axis-btn', { active: viewerStore.clipAxis === ax }]"
                @click="setClipAxis(ax)"
              >{{ ax.toUpperCase() }}</button>
              <button class="clip-flip-btn" @click="flipClip" :title="t('ui.clipFlip')">&#8644;</button>
            </div>
            <div class="clip-slider-row">
              <input
                type="range"
                min="0" max="100" step="1"
                :value="viewerStore.clipPosition"
                @input="(e: Event) => onClipSlider(Number((e.target as HTMLInputElement).value))"
                class="clip-slider"
              />
              <span class="clip-pct">{{ viewerStore.clipPosition }}%</span>
            </div>
          </div>

          <!-- Assembly panel -->
          <div class="assembly-panel">
            <div class="assembly-title">
              <span>{{ t('ui.assemblyTitle') }}</span>
              <span>({{ assemblyList.length }})</span>
            </div>
            <div class="assembly-list">
              <template v-if="assemblyList.length > 0">
                <div
                  v-for="item in assemblyList"
                  :key="item.id"
                  class="assembly-item"
                  :class="{ hidden: !item.visible }"
                >
                  <span class="color-dot" :style="{ background: item.color }"></span>
                  <span
                    class="comp-name"
                    :class="{ selected: viewerStore.selectedComponentId === item.id }"
                    @click="selectComponent(item.id)"
                  >{{ item.name }}</span>
                  <span class="comp-actions">
                    <button @click="toggleModelVisibility(item.id)">&#128065;</button>
                    <button @click="removeModel(item.id)">&times;</button>
                  </span>
                </div>
              </template>
              <div v-else class="assembly-empty">{{ t('ui.assemblyEmpty') }}</div>
            </div>
            <div class="assembly-actions">
              <button @click="clearAllModels">{{ t('ui.btnClearAll') }}</button>
              <button @click="toggleAssemblyModeUI">{{ t('ui.btnToggleMode') }}</button>
              <button class="primary" @click="autoAssemble">{{ t('ui.btnAutoAssemble') }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Auto-generation overlay (inside modal) -->
    <div v-if="autoGenerating" class="auto-gen-overlay">
      <div class="loading-spinner"></div>
      <div class="auto-gen-text">{{ t('ui.autoGenerating') }}</div>
    </div>

    <!-- Auto-generation error popup -->
    <div v-if="autoGenError" class="auto-gen-error-backdrop">
      <div class="auto-gen-error-popup">
        <div class="auto-gen-error-title">{{ t('ui.genFailed') }}</div>
        <div class="auto-gen-error-msg">{{ autoGenError }}</div>
        <div class="auto-gen-error-actions">
          <button @click="stayAndAdjust">{{ t('ui.handlesDismissStay') }}</button>
          <button class="primary" @click="dismissAutoGenError">{{ t('ui.handlesDismissClose') }}</button>
        </div>
      </div>
    </div>

    <!-- Loading overlay -->
    <div v-show="viewerStore.isLoading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <div class="loading-text">{{ t('ui.loadingModels') }}</div>
      <div class="loading-bar-wrap">
        <div class="loading-bar" :style="{ width: viewerStore.loadingProgress + '%' }"></div>
      </div>
      <div class="loading-pct">{{ viewerStore.loadingProgress }}%</div>
    </div>
  </Teleport>
</template>

<style scoped>
.viewer-modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.6);
  z-index: 8000;
}

.viewer-modal {
  position: fixed;
  top: 3vh;
  left: 3vw;
  width: 94vw;
  height: 94vh;
  background: var(--viewer-bg);
  border-radius: 16px;
  z-index: 8001;
  overflow: hidden;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.5);
}

.viewer-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
}

.viewer-modal-close {
  background: none;
  border: none;
  color: #fff;
  font-size: 22px;
  cursor: pointer;
  padding: 4px 10px;
  border-radius: 6px;
}
.viewer-modal-close:hover {
  background: rgba(255, 255, 255, 0.15);
}

.viewer-modal-body {
  width: 100%;
  height: calc(100% - 44px);
  position: relative;
}

#viewer3d {
  width: 100%;
  height: 100%;
  background: var(--viewer-bg-gradient);
  position: relative;
  overflow: hidden;
}

#viewer3d :deep(canvas) {
  display: block;
}

.viewer-info {
  position: absolute;
  top: 10px;
  left: 10px;
  color: #fff;
  font-size: 12px;
  background: rgba(0, 0, 0, 0.5);
  padding: 6px 10px;
  border-radius: 6px;
}

.viewer-controls {
  position: absolute;
  bottom: 10px;
  left: 10px;
  display: flex;
  gap: 8px;
  z-index: 10;
}
.viewer-controls button {
  background: rgba(255, 255, 255, 0.9);
  border: none;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}
.viewer-controls button:hover {
  background: #fff;
}
.viewer-controls button.ctrl-active {
  background: #ff4444;
  color: #fff;
}
.viewer-controls button.ctrl-active:hover {
  background: #ee3333;
}
.ctrl-separator {
  width: 1px;
  height: 20px;
  background: rgba(0, 0, 0, 0.15);
  align-self: center;
}

/* Clip panel */
.clip-panel {
  position: absolute;
  bottom: 50px;
  left: 10px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 8px;
  padding: 10px 12px;
  z-index: 15;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  min-width: 220px;
}
.clip-axis-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.clip-label {
  font-size: 11px;
  font-weight: 600;
  color: #333;
  margin-right: 4px;
}
.clip-axis-btn {
  padding: 3px 10px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 11px;
  font-weight: 700;
}
.clip-axis-btn:hover { background: #f0f0f0; }
.clip-axis-btn.active {
  background: #ff4444;
  color: #fff;
  border-color: #ff4444;
}
.clip-flip-btn {
  padding: 3px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 14px;
  margin-left: auto;
}
.clip-flip-btn:hover { background: #f0f0f0; }
.clip-slider-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.clip-slider {
  flex: 1;
  height: 4px;
  -webkit-appearance: none;
  appearance: none;
  background: #ddd;
  border-radius: 2px;
  outline: none;
}
.clip-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #ff4444;
  cursor: pointer;
}
.clip-pct {
  font-size: 11px;
  font-weight: 600;
  color: #666;
  min-width: 32px;
  text-align: right;
}

/* Assembly panel */
.assembly-panel {
  position: absolute;
  top: 10px;
  right: 10px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 8px;
  padding: 10px;
  min-width: 160px;
  max-width: 200px;
  z-index: 20;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}
.assembly-title {
  font-size: 12px;
  font-weight: 700;
  color: #333;
  margin-bottom: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.assembly-list {
  max-height: 200px;
  overflow-y: auto;
}
.assembly-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  margin: 2px 0;
  border-radius: 4px;
  font-size: 11px;
  background: #f5f5f5;
}
.assembly-item:hover {
  background: #e8e8e8;
}
.assembly-item .color-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.assembly-item .comp-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}
.assembly-item .comp-name:hover {
  color: var(--color-accent);
}
.assembly-item .comp-name.selected {
  font-weight: 700;
  color: var(--color-accent);
}
.assembly-item .comp-actions {
  display: flex;
  gap: 2px;
}
.assembly-item .comp-actions button {
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 4px;
  font-size: 10px;
  border-radius: 3px;
}
.assembly-item .comp-actions button:hover {
  background: #ddd;
}
.assembly-item.hidden {
  opacity: 0.5;
}
.assembly-empty {
  font-size: 11px;
  color: #999;
  text-align: center;
  padding: 10px 0;
}
.assembly-actions {
  margin-top: 8px;
  display: flex;
  gap: 6px;
}
.assembly-actions button {
  flex: 1;
  font-size: 10px;
  padding: 4px 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
}
.assembly-actions button:hover {
  background: #f0f0f0;
}
.assembly-actions button.primary {
  background: var(--color-accent);
  color: #fff;
  border-color: var(--color-accent);
}
.assembly-actions button.primary:hover {
  background: var(--color-accent-hover);
}

/* Auto-generation overlay */
.auto-gen-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(10, 10, 30, 0.8);
  z-index: 8500;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
}
.auto-gen-text {
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  margin-top: 16px;
}

/* Auto-generation error popup */
.auto-gen-error-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.5);
  z-index: 8600;
  display: flex;
  align-items: center;
  justify-content: center;
}
.auto-gen-error-popup {
  background: #fff;
  border-radius: 12px;
  padding: 24px 28px;
  max-width: 420px;
  width: 90%;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}
.auto-gen-error-title {
  font-size: 16px;
  font-weight: 700;
  color: #e03131;
  margin-bottom: 12px;
}
.auto-gen-error-msg {
  font-size: 13px;
  color: #555;
  line-height: 1.5;
  margin-bottom: 20px;
  max-height: 200px;
  overflow-y: auto;
  word-break: break-all;
}
.auto-gen-error-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
.auto-gen-error-actions button {
  padding: 8px 18px;
  border: 1px solid #ddd;
  border-radius: 6px;
  background: #f8f8f8;
  cursor: pointer;
  font-size: 13px;
}
.auto-gen-error-actions button:hover {
  background: #eee;
}
.auto-gen-error-actions button.primary {
  background: var(--color-accent);
  color: #fff;
  border-color: var(--color-accent);
}
.auto-gen-error-actions button.primary:hover {
  background: var(--color-accent-hover);
}

/* Handle labels */
.handle-label {
  position: absolute;
  font-size: 12px;
  font-weight: 700;
  background: rgba(0, 0, 0, 0.75);
  padding: 3px 8px;
  border-radius: 4px;
  border: 2px solid;
  pointer-events: none;
  z-index: 25;
  transform: translate(8px, -50%);
  white-space: nowrap;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}

/* Loading overlay */
.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(10, 10, 30, 0.92);
  z-index: 9000;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
}
.loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid rgba(255, 255, 255, 0.15);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 20px;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.loading-text {
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
}
.loading-bar-wrap {
  width: 320px;
  height: 6px;
  background: rgba(255, 255, 255, 0.12);
  border-radius: 3px;
  overflow: hidden;
}
.loading-bar {
  height: 100%;
  width: 0%;
  background: linear-gradient(90deg, var(--color-accent), var(--color-accent-hover));
  border-radius: 3px;
  transition: width 0.3s ease;
}
.loading-pct {
  color: rgba(255, 255, 255, 0.6);
  font-size: 13px;
  margin-top: 10px;
}
</style>
