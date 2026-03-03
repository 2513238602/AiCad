<script setup lang="ts">
import { ref, watch, onUnmounted, nextTick, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useViewerStore } from '@/stores/viewer'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import * as api from '@/api/client'
import { useParamsStore } from '@/stores/params'
import { getNested } from '@/utils/nested'

const { t } = useI18n()
const viewerStore = useViewerStore()
const paramsStore = useParamsStore()

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

const COMP_COLORS: Record<string, number> = {
  bottle: 0x4dabf7,
  wand: 0x69db7c,
  cap: 0xffa94d,
  wiper: 0xda77f2,
}

let assemblyMode: 'assembled' | 'exploded' = 'assembled'

// Clipping plane - NOT reactive (Three.js object)
let clipPlane: THREE.Plane | null = null
let clipHelperMesh: THREE.Mesh | null = null
let clipBoundsMin = new THREE.Vector3()
let clipBoundsMax = new THREE.Vector3()
// BackSide clone meshes for showing cut interior
const clipBackMeshes: Record<string, THREE.Mesh> = {}

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

  // TransformControls for drag/rotate/scale individual components
  transformControls = new TransformControls(camera, renderer.domElement)
  transformControls.setSize(0.8)
  transformControls.addEventListener('dragging-changed', (event) => {
    if (controls) controls.enabled = !event.value
  })
  scene.add(transformControls)

  renderer.domElement.addEventListener('click', onCanvasClick)
  window.addEventListener('keydown', onTransformKeydown)

  initialized = true
}

// ── TransformControls: click selection + mode switching ──

function onCanvasClick(event: MouseEvent) {
  if (!camera || !scene || !container.value) return
  if (transformControls?.dragging) return

  const rect = container.value.getBoundingClientRect()
  mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1

  raycaster.setFromCamera(mouse, camera)

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
    ;(prev.mesh.material as THREE.MeshPhongMaterial).emissive.setHex(0x000000)
  }

  selectedCompId = compId
  viewerStore.selectedComponentId = compId

  const m = sessionModels[compId]
  if (m?.mesh) {
    ;(m.mesh.material as THREE.MeshPhongMaterial).emissive.setHex(0x333333)
    transformControls?.attach(m.mesh)
  }
}

function deselectComponent() {
  if (selectedCompId && sessionModels[selectedCompId]) {
    const prev = sessionModels[selectedCompId]
    ;(prev.mesh.material as THREE.MeshPhongMaterial).emissive.setHex(0x000000)
  }
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
  if (e.key === 'w' || e.key === 'W') setTransformMode('translate')
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
        old.mesh.geometry.dispose()
        ;(old.mesh.material as THREE.Material).dispose()
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
      (geometry) => {
        geometry.computeBoundingBox()
        // 不调用 geometry.center() — 保留CadQuery原始坐标系
        // 装配定位由 autoAssemble() 通过精确参数计算完成
        const material = new THREE.MeshPhongMaterial({
          color,
          specular: 0x222222,
          shininess: 80,
          flatShading: false,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.95,
        })
        const newMesh = new THREE.Mesh(geometry, material)
        newMesh.userData.componentId = componentId
        newMesh.scale.set(0.5, 0.5, 0.5)
        scene!.add(newMesh)

        sessionModels[componentId] = { mesh: newMesh, stlUrl: url, visible: true, color, params }
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

  // 重置旋转
  for (const compId of compIds) {
    const m = sessionModels[compId]
    if (m?.mesh) m.mesh.rotation.set(0, 0, 0)
  }

  // 从后端获取最新装配位置（只传 viewer 中实际有的组件，避免旧状态影响）
  let positions: Record<string, { dz: number }> = {}
  if (assemblyMode === 'assembled') {
    try {
      const report = await api.fetchAssemblyReport(compIds)
      positions = report.positions || {}
      console.log('[Assembly] Backend positions (components=' + compIds.join(',') + '):', positions)
    } catch (e) {
      console.warn('[Assembly] Failed to fetch positions, using dz=0:', e)
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
    if (m.mesh?.material) (m.mesh.material as THREE.MeshPhongMaterial).wireframe = viewerStore.wireframeMode
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
    const mat = m.mesh?.material as THREE.MeshPhongMaterial
    if (!mat) continue

    // Switch main mesh to FrontSide only
    mat.side = THREE.FrontSide
    mat.clippingPlanes = [clipPlane]
    mat.clipShadows = true

    // Create BackSide clone for interior walls (darker color)
    if (!clipBackMeshes[compId] && scene && m.mesh) {
      const backMat = new THREE.MeshPhongMaterial({
        color: new THREE.Color(m.color).multiplyScalar(0.45),
        specular: 0x111111,
        shininess: 40,
        side: THREE.BackSide,
        clippingPlanes: [clipPlane],
        clipShadows: true,
      })
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
    const mat = sessionModels[compId].mesh?.material as THREE.MeshPhongMaterial
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
    m.mesh.geometry.dispose()
    ;(m.mesh.material as THREE.Material).dispose()
  }
  delete sessionModels[compId]
  viewerStore.removeModelMeta(compId)
  fitCameraToModels()
}

async function clearAllModels() {
  if (scene) {
    for (const compId of Object.keys(sessionModels)) {
      const m = sessionModels[compId]
      if (m.mesh) {
        scene.remove(m.mesh)
        m.mesh.geometry.dispose()
        ;(m.mesh.material as THREE.Material).dispose()
      }
    }
  }
  for (const k of Object.keys(sessionModels)) delete sessionModels[k]
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
  deselectComponent()
  stopRenderLoop()
  viewerStore.modalOpen = false
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

// Watch modal open
watch(
  () => viewerStore.modalOpen,
  async (open) => {
    if (open) {
      await nextTick()
      if (!initialized && container.value) {
        await new Promise((r) => requestAnimationFrame(r))
        initViewer()
      }

      // Load pending STLs
      const pendingKeys = Object.keys(viewerStore.pendingSTLs)
      if (pendingKeys.length > 0) {
        viewerStore.isLoading = true
        viewerStore.loadingProgress = 0
        let loaded = 0
        for (const compId of pendingKeys) {
          const info = viewerStore.pendingSTLs[compId]
          try {
            await loadOneSTL(info.url, compId, info.params)
          } catch (e) {
            console.error('Failed to load STL for', compId, e)
          }
          loaded++
          viewerStore.loadingProgress = Math.round((loaded / pendingKeys.length) * 100)
        }
        viewerStore.clearPending()
        viewerStore.isLoading = false
      }

      onWindowResize()
      await autoAssemble()
      startRenderLoop()
    } else {
      stopRenderLoop()
    }
  },
)

// Watch for new pending STLs while modal is already open
watch(
  () => viewerStore.hasPending,
  async (hasPending) => {
    if (!hasPending || !viewerStore.modalOpen || !initialized) return
    // Modal is open and new STLs were queued — load them immediately
    const pendingKeys = Object.keys(viewerStore.pendingSTLs)
    if (pendingKeys.length === 0) return

    viewerStore.isLoading = true
    viewerStore.loadingProgress = 0
    let loaded = 0
    for (const compId of pendingKeys) {
      const info = viewerStore.pendingSTLs[compId]
      try {
        await loadOneSTL(info.url, compId, info.params)
      } catch (e) {
        console.error('Failed to load STL for', compId, e)
      }
      loaded++
      viewerStore.loadingProgress = Math.round((loaded / pendingKeys.length) * 100)
    }
    viewerStore.clearPending()
    viewerStore.isLoading = false
    await autoAssemble()
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
          <div class="viewer-info">{{ t('ui.viewerTip') }}</div>

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
