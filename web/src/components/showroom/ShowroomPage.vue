<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js'

const { t } = useI18n()

type Quality = 'high' | 'balanced' | 'low'

const host = ref<HTMLDivElement | null>(null)
const loading = ref(true)
const error = ref('')
const moveSpeed = ref(5)
const quality = ref<Quality>('high')

const CORRIDOR_WIDTH = 8.4
const CORRIDOR_HEIGHT = 4.15
const SEGMENT_LENGTH = 8
const SEGMENT_POOL = 9
const SIDE_SLOT_COUNT = SEGMENT_POOL * 2
const START_Z = 2.4
const VISIBLE_LENGTH = SEGMENT_LENGTH * SEGMENT_POOL
const DISPLAY_X = CORRIDOR_WIDTH / 2 - 0.86
const FRAME_X = CORRIDOR_WIDTH / 2 - 0.32
const PANEL_X = CORRIDOR_WIDTH / 2 - 0.075
const GALLERY_ASSET_URL = '/assets/showroom-gallery/gallery_shell.glb'
const GALLERY_MANIFEST_URL = '/assets/showroom-gallery/gallery_manifest.json'
const GALLERY_START_Z = 5.95
const GALLERY_END_Z = -28.25
const GALLERY_MAX_X = 6.45
const UNREAL_MANIFEST_URL = '/assets/showroom-unreal/manifest.json'
const UNREAL_ASSET_NAMES = ['ShadowBox_1MPanel'] as const

type UnrealAssetName = (typeof UNREAL_ASSET_NAMES)[number]
type UnrealPoolName = 'backPanel'
type UnrealPool = Record<UnrealPoolName, THREE.Group[]>

interface GallerySlotCalibration {
  id: string
  module: string
  kind: string
  anchor_name: string
  position: [number, number, number]
  rotation: [number, number, number]
  usable_volume_m: {
    width: number
    depth: number
    height: number
  }
  cad_fit: {
    cad_units: 'millimeters' | string
    meters_per_cad_mm: number
    presentation_boost: number
    max_fit_scale: number
    target_height_m: number
    max_diameter_m: number
    placement_z_offset_m: number
  }
  lighting: Record<string, unknown>
  glass: Record<string, unknown>
}

interface GalleryCalibrationManifest {
  id: string
  asset: string
  units: 'meters' | string
  module_library: Record<string, unknown>
  cad_model_calibration: Record<string, unknown>
  lighting_calibration: Record<string, unknown>
  glass_calibration: Record<string, unknown>
  slots: GallerySlotCalibration[]
}

let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let renderer: THREE.WebGLRenderer | null = null
let composer: EffectComposer | null = null
let bloomPass: UnrealBloomPass | null = null
let rafId: number | null = null
let lastTime = 0
let yaw = 0
let pitch = -0.04
let dragging = false
let dragX = 0
let dragY = 0
let currentFirstSegment = Number.NaN
let activePixelRatio = 1
let frameCount = 0
let frameAccum = 0
let renderAccum = 0
let renderMax = 0
let statsLast = 0

const pressed = new Set<string>()
const tmpForward = new THREE.Vector3()
const tmpRight = new THREE.Vector3()
const tmpMove = new THREE.Vector3()
const tmpMatrix = new THREE.Matrix4()
const tmpQuat = new THREE.Quaternion()
const tmpScale = new THREE.Vector3(1, 1, 1)
const tmpCadBox = new THREE.Box3()
const tmpCadSize = new THREE.Vector3()
const tmpCadAnchor = new THREE.Vector3()
const tmpCadCenter = new THREE.Vector3()

const instancedMeshes: THREE.InstancedMesh[] = []
const unrealTemplates = new Map<UnrealAssetName, THREE.Group>()
const unrealMaterials = new Map<UnrealAssetName, THREE.MeshStandardMaterial>()
const unrealPools: UnrealPool = {
  backPanel: [],
}
const unrealSceneObjects: THREE.Object3D[] = []
let galleryRoot: THREE.Group | null = null
let galleryAssetsReady = false
let galleryMeshCount = 0
let galleryManifest: GalleryCalibrationManifest | null = null
const galleryAnchors = new Map<string, THREE.Object3D>()
let unrealAssetsReady = false
let floorMesh: THREE.InstancedMesh | null = null
let ceilingMesh: THREE.InstancedMesh | null = null
let ceilingChannelMesh: THREE.InstancedMesh | null = null
let wallMesh: THREE.InstancedMesh | null = null
let sideLightMesh: THREE.InstancedMesh | null = null
let ceilingLightMesh: THREE.InstancedMesh | null = null
let plinthMesh: THREE.InstancedMesh | null = null
let plinthTopMesh: THREE.InstancedMesh | null = null
let plinthKickMesh: THREE.InstancedMesh | null = null
let plaqueMesh: THREE.InstancedMesh | null = null
let turntableMesh: THREE.InstancedMesh | null = null
let acrylicCoverMesh: THREE.InstancedMesh | null = null
let framePostMesh: THREE.InstancedMesh | null = null
let frameRailMesh: THREE.InstancedMesh | null = null
let displayPanelMesh: THREE.InstancedMesh | null = null
let trimMesh: THREE.InstancedMesh | null = null
let verticalFinMesh: THREE.InstancedMesh | null = null
let wallGlowMesh: THREE.InstancedMesh | null = null
let floorShadowMesh: THREE.InstancedMesh | null = null
let floorEdgeShadowMesh: THREE.InstancedMesh | null = null

function seededNoise(seed: number) {
  const x = Math.sin(seed * 12.9898) * 43758.5453
  return x - Math.floor(x)
}

function qualityCap() {
  if (quality.value === 'high') return 1.0
  if (quality.value === 'balanced') return 0.82
  return 0.58
}

function applyQuality() {
  if (!renderer) return
  activePixelRatio = qualityCap()
  renderer.setPixelRatio(activePixelRatio)
  composer?.setPixelRatio(activePixelRatio)
}

function resizeRenderer() {
  if (!host.value || !renderer || !camera) return
  const w = host.value.clientWidth
  const h = host.value.clientHeight
  if (w <= 0 || h <= 0) return
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  renderer.setSize(w, h, false)
  composer?.setSize(w, h)
  if (bloomPass) bloomPass.setSize(w, h)
}

function setInstance(mesh: THREE.InstancedMesh | null, index: number, x: number, y: number, z: number) {
  if (!mesh) return
  tmpMatrix.compose(new THREE.Vector3(x, y, z), tmpQuat, tmpScale)
  mesh.setMatrixAt(index, tmpMatrix)
}

function createInstanceMesh(
  geometry: THREE.BufferGeometry,
  material: THREE.Material,
  count: number,
) {
  const mesh = new THREE.InstancedMesh(geometry, material, count)
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
  mesh.frustumCulled = false
  instancedMeshes.push(mesh)
  scene?.add(mesh)
  return mesh
}

function materialForUnrealAsset(name: UnrealAssetName) {
  const cached = unrealMaterials.get(name)
  if (cached) return cached

  const material = new THREE.MeshStandardMaterial({
    color: 0xf4f0e8,
    roughness: 0.58,
    metalness: 0.04,
  })
  unrealMaterials.set(name, material)
  return material
}

function normalizeAsset(root: THREE.Group, name: UnrealAssetName) {
  const box = new THREE.Box3().setFromObject(root)
  const center = box.getCenter(new THREE.Vector3())
  root.position.sub(new THREE.Vector3(center.x, box.min.y, center.z))
  const pivot = new THREE.Group()
  pivot.add(root)
  pivot.traverse((child) => {
    if (!(child as THREE.Mesh).isMesh) return
    const mesh = child as THREE.Mesh
    mesh.frustumCulled = false
    mesh.material = materialForUnrealAsset(name)
  })
  return pivot
}

function cloneUnrealAsset(name: UnrealAssetName) {
  const template = unrealTemplates.get(name)
  if (!template || !scene) return null
  const clone = template.clone(true)
  clone.visible = false
  unrealSceneObjects.push(clone)
  scene.add(clone)
  return clone
}

function setProceduralDisplayVisible(visible: boolean) {
  for (const mesh of [
    plinthMesh,
    plinthTopMesh,
    plinthKickMesh,
    plaqueMesh,
    turntableMesh,
    acrylicCoverMesh,
    framePostMesh,
    frameRailMesh,
    displayPanelMesh,
  ]) {
    if (mesh) mesh.visible = visible
  }
}

function createUnrealPools() {
  for (let i = 0; i < SIDE_SLOT_COUNT; i++) {
    const backPanel = cloneUnrealAsset('ShadowBox_1MPanel')
    if (backPanel) unrealPools.backPanel.push(backPanel)
  }
}

async function loadUnrealAssets() {
  if (!scene) return
  const response = await fetch(UNREAL_MANIFEST_URL)
  if (!response.ok) throw new Error(`showroom manifest ${response.status}`)
  const manifest = await response.json()
  const byName = new Map<string, string>(
    (manifest.assets || []).map((asset: { name: string; url: string }) => [asset.name, asset.url]),
  )
  const loader = new GLTFLoader()

  await Promise.all(
    UNREAL_ASSET_NAMES.map(async (name) => {
      const url = byName.get(name)
      if (!url) throw new Error(`missing showroom asset ${name}`)
      const gltf = await loader.loadAsync(url)
      unrealTemplates.set(name, normalizeAsset(gltf.scene, name))
    }),
  )

  createUnrealPools()
  unrealAssetsReady = true
  setProceduralDisplayVisible(true)
}

function transformAsset(
  object: THREE.Object3D | undefined,
  x: number,
  y: number,
  z: number,
  rotationY: number,
  scaleX: number,
  scaleY: number,
  scaleZ: number,
) {
  if (!object) return
  object.visible = true
  object.position.set(x, y, z)
  object.rotation.set(0, rotationY, 0)
  object.scale.set(scaleX, scaleY, scaleZ)
}

function updateUnrealAssets(first: number) {
  if (!unrealAssetsReady) return
  for (const object of unrealSceneObjects) {
    object.visible = false
  }
  for (let i = 0; i < SEGMENT_POOL; i++) {
    const segment = first + i
    const z = -(segment * SEGMENT_LENGTH + SEGMENT_LENGTH / 2)
    const slotZ = z + SEGMENT_LENGTH * 0.04
    const leftSlot = i * 2
    const rightSlot = i * 2 + 1

    transformAsset(unrealPools.backPanel[leftSlot], -CORRIDOR_WIDTH / 2 + 0.11, 0.72, slotZ, Math.PI / 2, 1.38, 0.42, 0.9)
    transformAsset(unrealPools.backPanel[rightSlot], CORRIDOR_WIDTH / 2 - 0.11, 0.72, slotZ, -Math.PI / 2, 1.38, 0.42, 0.9)
  }
}

function prepareGalleryMaterial(material: THREE.Material) {
  const source = material as THREE.Material & {
    color?: THREE.Color
    map?: THREE.Texture
    alphaMap?: THREE.Texture
    roughness?: number
    metalness?: number
    emissive?: THREE.Color
    emissiveIntensity?: number
  }
  const signature = material.name.toLowerCase()
  const transparent = material.transparent || material.opacity < 1
  const overlay = /shadow|occlusion|wash|sunlight|shade/.test(signature)
  if (source.map) {
    source.map.anisotropy = renderer?.capabilities.getMaxAnisotropy() || 1
    source.map.colorSpace = THREE.SRGBColorSpace
    source.map.needsUpdate = true
  }

  if (transparent && overlay) {
    const overlayMaterial = new THREE.MeshBasicMaterial({
      color: source.color ? source.color.clone() : new THREE.Color(0x1f1810),
      map: source.map || null,
      alphaMap: source.alphaMap || null,
      transparent: true,
      opacity: material.opacity,
      depthWrite: false,
      depthTest: true,
      side: THREE.DoubleSide,
      blending: /sunlight|wash/.test(signature) ? THREE.AdditiveBlending : THREE.NormalBlending,
    })
    overlayMaterial.name = material.name
    return overlayMaterial
  }

  if (transparent) {
    const glass = new THREE.MeshPhysicalMaterial({
      color: source.color ? source.color.clone() : new THREE.Color(0xd8f3ff),
      map: source.map || null,
      alphaMap: source.alphaMap || null,
      transparent: true,
      opacity: /liquid/.test(signature) ? Math.max(material.opacity, 0.62) : material.opacity,
      roughness: /frosted|skylight/.test(signature) ? 0.36 : 0.045,
      metalness: 0,
      transmission: /liquid/.test(signature) ? 0.25 : 0.72,
      thickness: /glass|skylight|acrylic/.test(signature) ? 0.34 : 0.12,
      ior: /liquid/.test(signature) ? 1.36 : 1.48,
      clearcoat: /glass|skylight/.test(signature) ? 0.7 : 0.2,
      clearcoatRoughness: 0.06,
      depthWrite: false,
      side: THREE.DoubleSide,
      envMapIntensity: 0.82,
    })
    glass.name = material.name
    return glass
  }

  const pbr = new THREE.MeshStandardMaterial({
    color: source.color ? source.color.clone() : new THREE.Color(0xffffff),
    map: source.map || null,
    alphaMap: source.alphaMap || null,
    roughness: source.roughness ?? (/floor|oak|wood/.test(signature) ? 0.46 : 0.52),
    metalness: source.metalness ?? (/champagne|metal|bronze|black cap/.test(signature) ? 0.72 : 0.04),
    emissive: source.emissive ? source.emissive.clone() : new THREE.Color(0x000000),
    emissiveIntensity: source.emissiveIntensity || (/light|glow|lens|wash|sunlight/.test(signature) ? 1.2 : 0),
    side: THREE.FrontSide,
    envMapIntensity: /floor|oak|wood|lacquer|cap|champagne|metal|bronze|stone/.test(signature) ? 0.56 : 0.34,
  })
  pbr.name = material.name
  return pbr
}

function applyGalleryShadowFlags(mesh: THREE.Mesh) {
  const names = Array.isArray(mesh.material)
    ? mesh.material.map((material) => material.name).join(' ')
    : mesh.material.name
  const signature = `${mesh.name} ${names}`.toLowerCase()
  const transparent = Array.isArray(mesh.material)
    ? mesh.material.some((material) => material.transparent || material.opacity < 1)
    : mesh.material.transparent || mesh.material.opacity < 1
  const decorativeLight = /skylight|sunlight|lens|shadow|glass|wash|glow|liquid/.test(signature)
  const receives = /floor|plinth|display|stone|oak|wood/.test(signature)
  const casts = /showcase|product|cap|collar|bottle|compact|tube|planter|frame|champagne|lacquer|stone/.test(signature)
  mesh.receiveShadow = !transparent && receives
  mesh.castShadow = !transparent && !decorativeLight && casts
}

async function loadGalleryManifest() {
  try {
    const response = await fetch(GALLERY_MANIFEST_URL)
    if (!response.ok) throw new Error(`gallery manifest ${response.status}`)
    galleryManifest = (await response.json()) as GalleryCalibrationManifest
  } catch (manifestError) {
    console.warn('Gallery calibration manifest unavailable.', manifestError)
    galleryManifest = null
  }
}

function getGallerySlot(slotId?: string) {
  if (!galleryManifest?.slots.length) return null
  if (!slotId) return galleryManifest.slots[0]
  return galleryManifest.slots.find((slot) => slot.id === slotId) || null
}

function computeCadPackageScale(sizeMm: THREE.Vector3, slot: GallerySlotCalibration) {
  const heightMm = Math.max(1, sizeMm.z || sizeMm.y || 120)
  const diameterMm = Math.max(1, sizeMm.x || 24, sizeMm.y || 24)
  const baseScale = slot.cad_fit.meters_per_cad_mm
  const heightFit = slot.cad_fit.target_height_m / (heightMm * baseScale)
  const diameterFit = slot.cad_fit.max_diameter_m / (diameterMm * baseScale)
  const presentationFit = Math.min(slot.cad_fit.presentation_boost, slot.cad_fit.max_fit_scale)
  return baseScale * Math.min(presentationFit, heightFit, diameterFit)
}

function fitCadPackageObjectToSlot(object: THREE.Object3D, slotId?: string) {
  const slot = getGallerySlot(slotId)
  if (!slot) return null
  const anchor = galleryAnchors.get(slot.anchor_name)
  if (!anchor) return null

  object.rotation.set(0, 0, 0)
  object.scale.set(1, 1, 1)
  object.updateMatrixWorld(true)
  tmpCadBox.setFromObject(object)
  tmpCadBox.getSize(tmpCadSize)

  const finalScale = computeCadPackageScale(tmpCadSize, slot)
  object.scale.setScalar(finalScale)
  object.quaternion.copy(anchor.getWorldQuaternion(tmpQuat))
  object.rotateX(-Math.PI / 2)
  object.updateMatrixWorld(true)

  anchor.getWorldPosition(tmpCadAnchor)
  tmpCadAnchor.y += slot.cad_fit.placement_z_offset_m
  tmpCadBox.setFromObject(object)
  tmpCadBox.getCenter(tmpCadCenter)
  object.position.add(tmpCadAnchor.sub(tmpCadCenter))
  object.updateMatrixWorld(true)

  object.traverse((child) => {
    const mesh = child as THREE.Mesh
    if (!mesh.isMesh) return
    mesh.castShadow = false
    mesh.receiveShadow = false
    const material = mesh.material as THREE.Material & { envMapIntensity?: number }
    if ('envMapIntensity' in material) material.envMapIntensity = 0.42
  })

  return {
    slotId: slot.id,
    anchorName: slot.anchor_name,
    finalScale,
    sourceSizeMm: {
      x: Number(tmpCadSize.x.toFixed(3)),
      y: Number(tmpCadSize.y.toFixed(3)),
      z: Number(tmpCadSize.z.toFixed(3)),
    },
    targetHeightM: slot.cad_fit.target_height_m,
    maxDiameterM: slot.cad_fit.max_diameter_m,
  }
}

function publishGalleryCalibration() {
  ;(window as any).__showroomCalibration = {
    manifest: galleryManifest,
    anchors: Array.from(galleryAnchors.keys()),
    fitCadPackageObjectToSlot,
    computeCadPackageScale: (sizeMm: { x: number; y: number; z: number }, slotId?: string) => {
      const slot = getGallerySlot(slotId)
      if (!slot) return null
      return computeCadPackageScale(new THREE.Vector3(sizeMm.x, sizeMm.y, sizeMm.z), slot)
    },
  }
}

async function loadGalleryShell() {
  if (!scene) return
  const loader = new GLTFLoader()
  const [gltf] = await Promise.all([loader.loadAsync(GALLERY_ASSET_URL), loadGalleryManifest()])
  galleryRoot = gltf.scene
  galleryRoot.name = 'BlenderGalleryShell'
  galleryMeshCount = 0
  galleryAnchors.clear()
  galleryRoot.traverse((child) => {
    if (child.name.startsWith('CAD_SLOT_')) {
      galleryAnchors.set(child.name, child)
    }
    if (!(child as THREE.Mesh).isMesh) return
    const mesh = child as THREE.Mesh
    galleryMeshCount += 1
    mesh.frustumCulled = true
    mesh.material = Array.isArray(mesh.material)
      ? mesh.material.map(prepareGalleryMaterial)
      : prepareGalleryMaterial(mesh.material)
    applyGalleryShadowFlags(mesh)
  })
  scene.add(galleryRoot)
  if (renderer) renderer.shadowMap.needsUpdate = true
  publishGalleryCalibration()
  galleryAssetsReady = true
}

function createWoodFloorMaterial() {
  const canvas = document.createElement('canvas')
  canvas.width = 1024
  canvas.height = 1024
  const ctx = canvas.getContext('2d')
  if (!ctx) return new THREE.MeshBasicMaterial({ color: 0x8f6a3e })

  const base = ctx.createLinearGradient(0, 0, canvas.width, canvas.height)
  base.addColorStop(0, '#aa8454')
  base.addColorStop(0.55, '#967348')
  base.addColorStop(1, '#b08b5c')
  ctx.fillStyle = base
  ctx.fillRect(0, 0, canvas.width, canvas.height)

  const plankCount = 12
  const plankW = canvas.width / plankCount
  for (let i = 0; i < plankCount; i++) {
    const tone = Math.floor((seededNoise(i + 3) - 0.5) * 8)
    ctx.fillStyle = `rgba(${tone > 0 ? 255 : 50}, ${tone > 0 ? 240 : 34}, ${tone > 0 ? 205 : 22}, ${Math.abs(tone) / 150})`
    ctx.fillRect(i * plankW, 0, plankW, canvas.height)

    ctx.fillStyle = 'rgba(58, 38, 20, 0.14)'
    ctx.fillRect(i * plankW, 0, 1, canvas.height)
    ctx.fillStyle = 'rgba(255, 238, 204, 0.035)'
    ctx.fillRect(i * plankW + plankW * 0.48, 0, 1, canvas.height)

    for (let g = 0; g < 12; g++) {
      const y = Math.floor(seededNoise(i * 100 + g) * canvas.height)
      const x = i * plankW + seededNoise(i * 70 + g) * plankW
      const len = 220 + seededNoise(i * 17 + g) * 520
      ctx.strokeStyle = `rgba(72, 45, 26, ${0.018 + seededNoise(i + g) * 0.028})`
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(x, y)
      ctx.bezierCurveTo(x + 20, y + len * 0.25, x - 18, y + len * 0.6, x + 10, y + len)
      ctx.stroke()
    }
  }

  ctx.fillStyle = 'rgba(255, 242, 214, 0.055)'
  ctx.fillRect(0, 0, canvas.width, canvas.height)

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.RepeatWrapping
  texture.repeat.set(1.7, 1.0)
  texture.anisotropy = renderer ? Math.min(4, renderer.capabilities.getMaxAnisotropy()) : 1
  texture.needsUpdate = true

  return new THREE.MeshBasicMaterial({ map: texture })
}

function createWallPaintMaterial() {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 512
  const ctx = canvas.getContext('2d')
  if (!ctx) return new THREE.MeshBasicMaterial({ color: 0xe7e3d8 })

  const grad = ctx.createLinearGradient(0, 0, 0, canvas.height)
  grad.addColorStop(0, '#f1eee5')
  grad.addColorStop(0.52, '#e5e1d6')
  grad.addColorStop(1, '#d7d1c4')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, canvas.width, canvas.height)

  const image = ctx.getImageData(0, 0, canvas.width, canvas.height)
  for (let i = 0; i < image.data.length; i += 4) {
    const n = (seededNoise(i) - 0.5) * 7
    image.data[i] += n
    image.data[i + 1] += n
    image.data[i + 2] += n
  }
  ctx.putImageData(image, 0, 0)

  ctx.fillStyle = 'rgba(255, 255, 250, 0.12)'
  ctx.fillRect(0, 70, canvas.width, 120)
  ctx.fillStyle = 'rgba(88, 72, 55, 0.08)'
  ctx.fillRect(0, canvas.height - 42, canvas.width, 42)

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.RepeatWrapping
  texture.repeat.set(1, 1.6)
  texture.anisotropy = renderer ? Math.min(4, renderer.capabilities.getMaxAnisotropy()) : 1
  texture.needsUpdate = true

  return new THREE.MeshBasicMaterial({ map: texture })
}

function createPlinthMaterial() {
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 256
  const ctx = canvas.getContext('2d')
  if (!ctx) return new THREE.MeshBasicMaterial({ color: 0xf0f0ea })

  const grad = ctx.createLinearGradient(0, 0, 0, canvas.height)
  grad.addColorStop(0, '#fbfaf5')
  grad.addColorStop(0.62, '#ecece5')
  grad.addColorStop(1, '#d3d2ca')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  for (let i = 0; i < 360; i++) {
    const x = seededNoise(i * 2) * canvas.width
    const y = seededNoise(i * 5) * canvas.height
    const a = 0.015 + seededNoise(i * 7) * 0.02
    ctx.fillStyle = `rgba(80, 80, 72, ${a})`
    ctx.fillRect(x, y, 1, 1)
  }

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.RepeatWrapping
  texture.repeat.set(1, 1)
  texture.needsUpdate = true

  return new THREE.MeshBasicMaterial({ map: texture })
}

function buildCorridor() {
  if (!scene) return

  const floorMat = createWoodFloorMaterial()
  const ceilingMat = new THREE.MeshBasicMaterial({ color: 0xeee7d9 })
  const ceilingChannelMat = new THREE.MeshBasicMaterial({ color: 0x172128 })
  const wallMat = createWallPaintMaterial()
  const lightMat = new THREE.MeshBasicMaterial({ color: 0xfffbeb })
  const plinthMat = createPlinthMaterial()
  const plinthTopMat = new THREE.MeshBasicMaterial({ color: 0xfffef7 })
  const champagneMat = new THREE.MeshBasicMaterial({ color: 0xc9a66a })
  const plaqueMat = new THREE.MeshBasicMaterial({ color: 0x111111 })
  const frameMat = new THREE.MeshBasicMaterial({ color: 0xb9aa89 })
  const panelMat = new THREE.MeshBasicMaterial({ color: 0xfffcf2 })
  const trimMat = new THREE.MeshBasicMaterial({ color: 0xd5c9b4 })
  const wallGlowMat = new THREE.MeshBasicMaterial({
    color: 0xfff1c2,
    transparent: true,
    opacity: 0.2,
    depthWrite: false,
  })
  const acrylicMat = new THREE.MeshBasicMaterial({
    color: 0xdff7ff,
    transparent: true,
    opacity: 0.18,
    depthWrite: false,
  })
  const shadowMat = new THREE.MeshBasicMaterial({
    color: 0x1d160f,
    transparent: true,
    opacity: 0.18,
    depthWrite: false,
  })
  const edgeShadowMat = new THREE.MeshBasicMaterial({
    color: 0x21170f,
    transparent: true,
    opacity: 0.09,
    depthWrite: false,
  })

  floorMesh = createInstanceMesh(
    new THREE.BoxGeometry(CORRIDOR_WIDTH, 0.08, VISIBLE_LENGTH + 0.2),
    floorMat,
    1,
  )
  ceilingMesh = createInstanceMesh(
    new THREE.BoxGeometry(CORRIDOR_WIDTH, 0.12, VISIBLE_LENGTH + 0.2),
    ceilingMat,
    1,
  )
  ceilingChannelMesh = createInstanceMesh(
    new THREE.BoxGeometry(2.7, 0.055, VISIBLE_LENGTH * 0.96),
    ceilingChannelMat,
    1,
  )
  wallMesh = createInstanceMesh(
    new THREE.BoxGeometry(0.1, CORRIDOR_HEIGHT, VISIBLE_LENGTH + 0.2),
    wallMat,
    2,
  )
  sideLightMesh = createInstanceMesh(
    new THREE.BoxGeometry(0.04, 0.045, VISIBLE_LENGTH * 0.96),
    lightMat,
    2,
  )
  ceilingLightMesh = createInstanceMesh(
    new THREE.BoxGeometry(0.065, 0.05, VISIBLE_LENGTH * 0.96),
    lightMat,
    2,
  )
  plinthMesh = createInstanceMesh(
    new RoundedBoxGeometry(0.9, 0.74, 1.28, 4, 0.075),
    plinthMat,
    SIDE_SLOT_COUNT,
  )
  plinthTopMesh = createInstanceMesh(
    new RoundedBoxGeometry(0.94, 0.05, 1.32, 3, 0.045),
    plinthTopMat,
    SIDE_SLOT_COUNT,
  )
  plinthKickMesh = createInstanceMesh(
    new RoundedBoxGeometry(0.98, 0.1, 1.38, 3, 0.04),
    champagneMat,
    SIDE_SLOT_COUNT,
  )
  plaqueMesh = createInstanceMesh(
    new RoundedBoxGeometry(0.58, 0.13, 0.045, 3, 0.018),
    plaqueMat,
    SIDE_SLOT_COUNT,
  )
  turntableMesh = createInstanceMesh(
    new THREE.CylinderGeometry(0.34, 0.36, 0.075, 32),
    champagneMat,
    SIDE_SLOT_COUNT,
  )
  acrylicCoverMesh = createInstanceMesh(
    new RoundedBoxGeometry(0.86, 0.82, 0.98, 3, 0.045),
    acrylicMat,
    SIDE_SLOT_COUNT,
  )
  displayPanelMesh = createInstanceMesh(
    new RoundedBoxGeometry(0.035, 1.56, 1.26, 4, 0.045),
    panelMat,
    SIDE_SLOT_COUNT,
  )
  framePostMesh = createInstanceMesh(
    new THREE.BoxGeometry(0.045, 1.34, 0.045),
    frameMat,
    SIDE_SLOT_COUNT * 2,
  )
  frameRailMesh = createInstanceMesh(
    new THREE.BoxGeometry(0.045, 0.045, 1.34),
    frameMat,
    SIDE_SLOT_COUNT * 2,
  )
  trimMesh = createInstanceMesh(
    new THREE.BoxGeometry(0.08, 0.12, VISIBLE_LENGTH + 0.2),
    trimMat,
    4,
  )
  verticalFinMesh = createInstanceMesh(
    new THREE.BoxGeometry(0.055, 2.05, 0.055),
    champagneMat,
    (SEGMENT_POOL + 1) * 2,
  )
  wallGlowMesh = createInstanceMesh(
    new THREE.BoxGeometry(0.012, 0.72, VISIBLE_LENGTH * 0.94),
    wallGlowMat,
    2,
  )
  const shadowGeometry = new THREE.PlaneGeometry(1.18, 1.72)
  shadowGeometry.rotateX(-Math.PI / 2)
  floorShadowMesh = createInstanceMesh(
    shadowGeometry,
    shadowMat,
    SIDE_SLOT_COUNT,
  )
  const edgeShadowGeometry = new THREE.PlaneGeometry(0.82, SEGMENT_LENGTH + 0.04)
  edgeShadowGeometry.rotateX(-Math.PI / 2)
  floorEdgeShadowMesh = createInstanceMesh(
    edgeShadowGeometry,
    edgeShadowMat,
    2,
  )
}

function updateCorridorInstances(force = false) {
  if (!camera) return
  const segmentAtCamera = Math.max(0, Math.floor(Math.max(0, -camera.position.z) / SEGMENT_LENGTH))
  const first = Math.max(0, segmentAtCamera - 1)
  if (!force && first === currentFirstSegment) return
  currentFirstSegment = first

  const visibleZ = -(first * SEGMENT_LENGTH + VISIBLE_LENGTH / 2)
  setInstance(floorMesh, 0, 0, -0.04, visibleZ)
  setInstance(ceilingMesh, 0, 0, CORRIDOR_HEIGHT, visibleZ)
  setInstance(ceilingChannelMesh, 0, 0, CORRIDOR_HEIGHT - 0.085, visibleZ)
  setInstance(wallMesh, 0, -CORRIDOR_WIDTH / 2, CORRIDOR_HEIGHT / 2, visibleZ)
  setInstance(wallMesh, 1, CORRIDOR_WIDTH / 2, CORRIDOR_HEIGHT / 2, visibleZ)
  setInstance(sideLightMesh, 0, -CORRIDOR_WIDTH / 2 + 0.06, 2.46, visibleZ)
  setInstance(sideLightMesh, 1, CORRIDOR_WIDTH / 2 - 0.06, 2.46, visibleZ)
  setInstance(ceilingLightMesh, 0, -2.08, CORRIDOR_HEIGHT - 0.08, visibleZ)
  setInstance(ceilingLightMesh, 1, 2.08, CORRIDOR_HEIGHT - 0.08, visibleZ)
  setInstance(trimMesh, 0, -CORRIDOR_WIDTH / 2 + 0.05, 0.14, visibleZ)
  setInstance(trimMesh, 1, CORRIDOR_WIDTH / 2 - 0.05, 0.14, visibleZ)
  setInstance(trimMesh, 2, -CORRIDOR_WIDTH / 2 + 0.05, CORRIDOR_HEIGHT - 0.2, visibleZ)
  setInstance(trimMesh, 3, CORRIDOR_WIDTH / 2 - 0.05, CORRIDOR_HEIGHT - 0.2, visibleZ)
  setInstance(wallGlowMesh, 0, -CORRIDOR_WIDTH / 2 + 0.07, 2.1, visibleZ)
  setInstance(wallGlowMesh, 1, CORRIDOR_WIDTH / 2 - 0.07, 2.1, visibleZ)
  setInstance(floorEdgeShadowMesh, 0, -CORRIDOR_WIDTH / 2 + 0.44, 0.012, visibleZ)
  setInstance(floorEdgeShadowMesh, 1, CORRIDOR_WIDTH / 2 - 0.44, 0.012, visibleZ)

  for (let i = 0; i <= SEGMENT_POOL; i++) {
    const z = -(first * SEGMENT_LENGTH + i * SEGMENT_LENGTH)
    setInstance(verticalFinMesh, i * 2, -CORRIDOR_WIDTH / 2 + 0.11, 1.66, z)
    setInstance(verticalFinMesh, i * 2 + 1, CORRIDOR_WIDTH / 2 - 0.11, 1.66, z)
  }

  for (let i = 0; i < SEGMENT_POOL; i++) {
    const segment = first + i
    const z = -(segment * SEGMENT_LENGTH + SEGMENT_LENGTH / 2)

    const slotZ = z + SEGMENT_LENGTH * 0.04
    const leftSlot = i * 2
    const rightSlot = i * 2 + 1
    setInstance(plinthMesh, leftSlot, -DISPLAY_X, 0.43, slotZ)
    setInstance(plinthMesh, rightSlot, DISPLAY_X, 0.43, slotZ)
    setInstance(plinthTopMesh, leftSlot, -DISPLAY_X, 0.815, slotZ)
    setInstance(plinthTopMesh, rightSlot, DISPLAY_X, 0.815, slotZ)
    setInstance(plinthKickMesh, leftSlot, -DISPLAY_X, 0.07, slotZ)
    setInstance(plinthKickMesh, rightSlot, DISPLAY_X, 0.07, slotZ)
    setInstance(turntableMesh, leftSlot, -DISPLAY_X, 0.89, slotZ)
    setInstance(turntableMesh, rightSlot, DISPLAY_X, 0.89, slotZ)
    setInstance(acrylicCoverMesh, leftSlot, -DISPLAY_X, 1.28, slotZ)
    setInstance(acrylicCoverMesh, rightSlot, DISPLAY_X, 1.28, slotZ)
    setInstance(floorShadowMesh, leftSlot, -DISPLAY_X, 0.016, slotZ + 0.08)
    setInstance(floorShadowMesh, rightSlot, DISPLAY_X, 0.016, slotZ + 0.08)
    setInstance(plaqueMesh, leftSlot, -DISPLAY_X, 0.93, slotZ - 0.7)
    setInstance(plaqueMesh, rightSlot, DISPLAY_X, 0.93, slotZ - 0.7)
    setInstance(displayPanelMesh, leftSlot, -PANEL_X, 1.66, slotZ)
    setInstance(displayPanelMesh, rightSlot, PANEL_X, 1.66, slotZ)

    setInstance(framePostMesh, leftSlot * 2, -FRAME_X, 1.66, slotZ - 0.68)
    setInstance(framePostMesh, leftSlot * 2 + 1, -FRAME_X, 1.66, slotZ + 0.68)
    setInstance(framePostMesh, rightSlot * 2, FRAME_X, 1.66, slotZ - 0.68)
    setInstance(framePostMesh, rightSlot * 2 + 1, FRAME_X, 1.66, slotZ + 0.68)
    setInstance(frameRailMesh, leftSlot * 2, -FRAME_X, 2.31, slotZ)
    setInstance(frameRailMesh, leftSlot * 2 + 1, -FRAME_X, 1.01, slotZ)
    setInstance(frameRailMesh, rightSlot * 2, FRAME_X, 2.31, slotZ)
    setInstance(frameRailMesh, rightSlot * 2 + 1, FRAME_X, 1.01, slotZ)
  }

  for (const mesh of instancedMeshes) {
    mesh.instanceMatrix.needsUpdate = true
  }
  updateUnrealAssets(first)
}

function setCameraDefaults() {
  if (!camera) return
  camera.position.set(0, galleryAssetsReady ? 1.62 : 1.58, galleryAssetsReady ? GALLERY_START_Z : START_Z)
  yaw = 0
  pitch = galleryAssetsReady ? -0.02 : -0.04
  updateCameraRotation()
  if (!galleryAssetsReady) updateCorridorInstances(true)
}

function updateCameraRotation() {
  if (!camera) return
  camera.rotation.order = 'YXZ'
  camera.rotation.y = yaw
  camera.rotation.x = pitch
  camera.rotation.z = 0
}

function clampCamera() {
  if (!camera) return
  if (galleryAssetsReady) {
    camera.position.x = Math.min(GALLERY_MAX_X, Math.max(-GALLERY_MAX_X, camera.position.x))
    camera.position.y = Math.min(2.45, Math.max(1.12, camera.position.y))
    camera.position.z = Math.min(GALLERY_START_Z, Math.max(GALLERY_END_Z, camera.position.z))
    return
  }
  camera.position.x = Math.min(2.05, Math.max(-2.05, camera.position.x))
  camera.position.y = Math.min(2.56, Math.max(1.18, camera.position.y))
  camera.position.z = Math.min(START_Z, camera.position.z)
}

function updateMovement(dt: number) {
  if (!camera) return
  tmpMove.set(0, 0, 0)
  camera.getWorldDirection(tmpForward)
  tmpForward.y = 0
  if (tmpForward.lengthSq() < 0.0001) tmpForward.set(0, 0, -1)
  else tmpForward.normalize()
  tmpRight.crossVectors(tmpForward, camera.up).normalize()

  if (pressed.has('KeyW')) tmpMove.add(tmpForward)
  if (pressed.has('KeyS')) tmpMove.sub(tmpForward)
  if (pressed.has('KeyA')) tmpMove.sub(tmpRight)
  if (pressed.has('KeyD')) tmpMove.add(tmpRight)
  if (pressed.has('KeyE')) tmpMove.y += 1
  if (pressed.has('KeyQ')) tmpMove.y -= 1

  if (tmpMove.lengthSq() > 0) {
    tmpMove.normalize().multiplyScalar(moveSpeed.value * dt)
    camera.position.add(tmpMove)
    clampCamera()
    if (!galleryAssetsReady) updateCorridorInstances()
  }
}

function publishStats(frameMs: number, renderMs: number) {
  if (!renderer || !camera) return
  frameCount += 1
  frameAccum += frameMs
  renderAccum += renderMs
  renderMax = Math.max(renderMax, renderMs)
  if (frameCount < 30) return
  const avgMs = frameAccum / frameCount
  const avgRenderMs = renderAccum / frameCount
  ;(window as any).__showroomStats = {
    fps: Math.round(1000 / avgMs),
    avgMs: Number(avgMs.toFixed(2)),
    renderMs: Number(avgRenderMs.toFixed(3)),
    renderMaxMs: Number(renderMax.toFixed(3)),
    pixelRatio: activePixelRatio,
    drawCalls: renderer.info.render.calls,
    triangles: renderer.info.render.triangles,
    assetMode: galleryAssetsReady ? 'blender-gallery' : 'procedural-corridor',
    galleryAssetsReady,
    galleryMeshes: galleryMeshCount,
    gallerySlots: galleryManifest?.slots.length || 0,
    galleryAnchors: galleryAnchors.size,
    unrealAssetsReady,
    unrealObjects: unrealSceneObjects.length,
    visibleUnrealObjects: unrealSceneObjects.filter((object) => object.visible).length,
    segment: galleryAssetsReady ? 0 : Math.max(0, Math.floor(Math.max(0, -camera.position.z) / SEGMENT_LENGTH)),
  }
  frameCount = 0
  frameAccum = 0
  renderAccum = 0
  renderMax = 0
}

function adaptQuality(frameMs: number) {
  if (!renderer) return
  if (quality.value === 'low') return
  statsLast += frameMs
  if (statsLast < 1000) return
  statsLast = 0
  const maxCap = qualityCap()
  if (frameMs > 20 && activePixelRatio > 0.45) {
    activePixelRatio = Math.max(0.45, activePixelRatio - 0.08)
    renderer.setPixelRatio(activePixelRatio)
    composer?.setPixelRatio(activePixelRatio)
    resizeRenderer()
  } else if (frameMs < 13.5 && activePixelRatio < maxCap) {
    activePixelRatio = Math.min(maxCap, activePixelRatio + 0.04)
    renderer.setPixelRatio(activePixelRatio)
    composer?.setPixelRatio(activePixelRatio)
    resizeRenderer()
  }
}

function renderLoop(now: number) {
  if (!renderer || !scene || !camera) return
  const dt = lastTime ? Math.min((now - lastTime) / 1000, 0.05) : 0
  const frameMs = lastTime ? now - lastTime : 16.67
  lastTime = now
  updateMovement(dt)
  const renderStart = performance.now()
  if (composer) composer.render()
  else renderer.render(scene, camera)
  publishStats(frameMs, performance.now() - renderStart)
  rafId = requestAnimationFrame(renderLoop)
}

function stopLoop() {
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
}

function startLoop() {
  stopLoop()
  lastTime = 0
  frameCount = 0
  frameAccum = 0
  renderAccum = 0
  renderMax = 0
  statsLast = 0
  rafId = requestAnimationFrame(renderLoop)
}

async function loadShowroom() {
  if (!host.value) return
  loading.value = true
  error.value = ''

  try {
    scene = new THREE.Scene()
    scene.background = new THREE.Color(0xf0f2f0)
    scene.fog = new THREE.Fog(0xf0f2f0, 46, 92)
    scene.add(new THREE.AmbientLight(0xfff3e4, 0.32))
    scene.add(new THREE.HemisphereLight(0xfff4e8, 0x6d5c49, 0.78))
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.55)
    keyLight.position.set(-6.5, -3.8, 10.5)
    keyLight.target.position.set(0, 12, 0)
    scene.add(keyLight.target)
    keyLight.castShadow = true
    keyLight.shadow.mapSize.set(4096, 4096)
    keyLight.shadow.bias = -0.00018
    keyLight.shadow.normalBias = 0.018
    const shadowCamera = keyLight.shadow.camera as THREE.OrthographicCamera
    shadowCamera.left = -15
    shadowCamera.right = 15
    shadowCamera.top = 34
    shadowCamera.bottom = -16
    shadowCamera.near = 1
    shadowCamera.far = 48
    shadowCamera.updateProjectionMatrix()
    scene.add(keyLight)
    const fillLight = new THREE.DirectionalLight(0xffead0, 0.58)
    fillLight.position.set(4.5, 4.4, -8)
    scene.add(fillLight)
    const displaySpot = new THREE.SpotLight(0xffdfaa, 2.4, 26, Math.PI / 5.5, 0.42, 1.2)
    displaySpot.position.set(0, 4.5, 5.7)
    displaySpot.target.position.set(0, 14, 1.2)
    displaySpot.castShadow = true
    displaySpot.shadow.mapSize.set(2048, 2048)
    displaySpot.shadow.bias = -0.0002
    scene.add(displaySpot)
    scene.add(displaySpot.target)

    camera = new THREE.PerspectiveCamera(58, 1, 0.08, 84)
    renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      powerPreference: 'high-performance',
      stencil: false,
      depth: true,
    })
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 0.94
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    renderer.shadowMap.autoUpdate = true
    renderer.shadowMap.needsUpdate = true
    const pmrem = new THREE.PMREMGenerator(renderer)
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    pmrem.dispose()
    composer = new EffectComposer(renderer)
    composer.setPixelRatio(activePixelRatio)
    const renderPass = new RenderPass(scene, camera)
    bloomPass = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.035, 0.42, 0.92)
    composer.addPass(renderPass)
    composer.addPass(bloomPass)
    composer.addPass(new OutputPass())
    applyQuality()
    host.value.appendChild(renderer.domElement)

    resizeRenderer()
    try {
      await loadGalleryShell()
    } catch (assetError) {
      console.warn('Blender gallery asset unavailable, keeping procedural fallback.', assetError)
      ;(window as any).__showroomAssetError = String(assetError)
      buildCorridor()
      try {
        await loadUnrealAssets()
      } catch (fallbackAssetError) {
        console.warn('Unreal showroom assets unavailable, keeping procedural fallback.', fallbackAssetError)
        ;(window as any).__showroomFallbackAssetError = String(fallbackAssetError)
        setProceduralDisplayVisible(true)
      }
    }
    setCameraDefaults()
    startLoop()
  } catch (e: any) {
    error.value = String(e?.message || e)
  } finally {
    loading.value = false
  }
}

function resetView() {
  setCameraDefaults()
}

function cycleQuality() {
  quality.value = quality.value === 'low' ? 'balanced' : quality.value === 'balanced' ? 'high' : 'low'
  applyQuality()
  resizeRenderer()
}

function onPointerDown(e: PointerEvent) {
  if (e.button !== 0) return
  e.preventDefault()
  dragging = true
  dragX = e.clientX
  dragY = e.clientY
  host.value?.setPointerCapture(e.pointerId)
}

function onPointerMove(e: PointerEvent) {
  if (!dragging) return
  e.preventDefault()
  const sensitivity = 0.0022
  const dx = e.clientX - dragX
  const dy = e.clientY - dragY
  dragX = e.clientX
  dragY = e.clientY
  yaw -= dx * sensitivity
  pitch -= dy * sensitivity
  pitch = Math.max(-1.12, Math.min(1.12, pitch))
  updateCameraRotation()
}

function onPointerUp(e: PointerEvent) {
  dragging = false
  host.value?.releasePointerCapture(e.pointerId)
}

function onWheel(e: WheelEvent) {
  if (!camera) return
  e.preventDefault()
  camera.getWorldDirection(tmpForward)
  camera.position.addScaledVector(tmpForward, -Math.sign(e.deltaY) * moveSpeed.value * 0.28)
  clampCamera()
  if (!galleryAssetsReady) updateCorridorInstances()
}

function onKeyDown(e: KeyboardEvent) {
  if (['KeyW', 'KeyA', 'KeyS', 'KeyD', 'KeyQ', 'KeyE', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space'].includes(e.code)) {
    e.preventDefault()
  }
  pressed.add(e.code)
}

function onKeyUp(e: KeyboardEvent) {
  pressed.delete(e.code)
}

function disposeMaterial(material: THREE.Material) {
  for (const value of Object.values(material as unknown as Record<string, unknown>)) {
    const texture = value as THREE.Texture | undefined
    if (texture?.isTexture) texture.dispose()
  }
  material.dispose()
}

function disposeObjectTree(root: THREE.Object3D) {
  const disposedMaterials = new Set<THREE.Material>()
  root.traverse((child) => {
    if (!(child as THREE.Mesh).isMesh) return
    const mesh = child as THREE.Mesh
    mesh.geometry.dispose()
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
    for (const material of materials) {
      if (disposedMaterials.has(material)) continue
      disposedMaterials.add(material)
      disposeMaterial(material)
    }
  })
  root.removeFromParent()
}

function disposeScene() {
  stopLoop()
  if (galleryRoot) {
    disposeObjectTree(galleryRoot)
  }
  galleryRoot = null
  galleryAssetsReady = false
  galleryMeshCount = 0
  for (const mesh of instancedMeshes) {
    mesh.geometry.dispose()
    if (Array.isArray(mesh.material)) mesh.material.forEach(disposeMaterial)
    else disposeMaterial(mesh.material)
  }
  instancedMeshes.length = 0
  for (const object of unrealSceneObjects) {
    object.removeFromParent()
  }
  unrealSceneObjects.length = 0
  for (const key of Object.keys(unrealPools) as UnrealPoolName[]) {
    unrealPools[key].length = 0
  }
  unrealTemplates.clear()
  for (const material of unrealMaterials.values()) {
    material.dispose()
  }
  unrealMaterials.clear()
  unrealAssetsReady = false
  if (composer) {
    composer.dispose()
  }
  if (renderer) {
    renderer.dispose()
    renderer.domElement.remove()
  }
  floorMesh = null
  ceilingMesh = null
  ceilingChannelMesh = null
  wallMesh = null
  sideLightMesh = null
  ceilingLightMesh = null
  plinthMesh = null
  plinthTopMesh = null
  plinthKickMesh = null
  plaqueMesh = null
  turntableMesh = null
  acrylicCoverMesh = null
  framePostMesh = null
  frameRailMesh = null
  displayPanelMesh = null
  trimMesh = null
  verticalFinMesh = null
  wallGlowMesh = null
  floorShadowMesh = null
  floorEdgeShadowMesh = null
  scene = null
  camera = null
  renderer = null
  composer = null
  bloomPass = null
}

onMounted(async () => {
  await nextTick()
  await loadShowroom()
  window.addEventListener('resize', resizeRenderer)
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeRenderer)
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  disposeScene()
})
</script>

<template>
  <main class="showroom-page">
    <section class="showroom-toolbar">
      <div class="showroom-titleblock">
        <h2>{{ t('showroom.title') }}</h2>
        <span>{{ t('showroom.infiniteCorridor') }}</span>
      </div>
      <div class="showroom-actions">
        <button @click="resetView">{{ t('showroom.resetView') }}</button>
        <button @click="cycleQuality">{{ t(`showroom.quality.${quality}`) }}</button>
        <label class="speed-control">
          <span>{{ t('showroom.speed') }}</span>
          <input v-model.number="moveSpeed" type="range" min="2" max="9" step="0.5" />
        </label>
      </div>
    </section>

    <section
      ref="host"
      class="showroom-viewport"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @wheel="onWheel"
    >
      <div v-if="loading" class="viewport-state">{{ t('ui.loading') }}</div>
      <div v-else-if="error" class="viewport-state viewport-error">{{ error }}</div>
    </section>
  </main>
</template>

<style scoped>
.showroom-page {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 108px);
  gap: 12px;
}

.showroom-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.showroom-titleblock {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.showroom-titleblock h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 800;
  color: var(--color-text-primary, #1e293b);
  letter-spacing: 0;
}

.showroom-titleblock span {
  font-size: 12px;
  color: var(--color-text-muted, #94a3b8);
}

.showroom-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.showroom-actions button {
  height: 32px;
  border: 1px solid rgba(148, 163, 184, 0.4);
  border-radius: 8px;
  padding: 0 12px;
  background: #fff;
  color: #334155;
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
}

.showroom-actions button:hover {
  border-color: #0891b2;
  color: #0e7490;
  background: #ecfeff;
}

.speed-control {
  height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  border: 1px solid rgba(148, 163, 184, 0.4);
  border-radius: 8px;
  background: #fff;
  color: #334155;
  font-size: 12px;
  font-weight: 700;
}

.speed-control input {
  width: 112px;
  accent-color: #0891b2;
}

.showroom-viewport {
  position: relative;
  flex: 1;
  min-height: 620px;
  overflow: hidden;
  contain: paint;
  touch-action: none;
  user-select: none;
  border: 1px solid rgba(15, 23, 42, 0.18);
  border-radius: 10px;
  background: #12171d;
  box-shadow: 0 18px 44px rgba(15, 23, 42, 0.18);
  cursor: grab;
}

.showroom-viewport:active {
  cursor: grabbing;
}

.showroom-viewport :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}

.viewport-state {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.86);
  background: #12171d;
  font-size: 14px;
  font-weight: 700;
  z-index: 2;
}

.viewport-error {
  color: #fecaca;
  padding: 24px;
  text-align: center;
}

@media (max-width: 760px) {
  .showroom-page {
    min-height: calc(100vh - 136px);
  }

  .showroom-viewport {
    min-height: 520px;
  }
}
</style>
