import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import type { PendingSTL } from '@/api/types'

export const useViewerStore = defineStore('viewer', () => {
  // Serializable metadata only - actual Three.js meshes are NOT stored here
  const sessionModelIds = ref<string[]>([])
  const modelVisibility = reactive<Record<string, boolean>>({})
  const modelColors = reactive<Record<string, number>>({})

  const pendingSTLs = reactive<Record<string, PendingSTL>>({})
  const assemblyMode = ref<'assembled' | 'exploded'>('assembled')
  const wireframeMode = ref(false)
  const autoRotate = ref(false)
  const clipEnabled = ref(false)
  const clipAxis = ref<'x' | 'y' | 'z'>('x')
  const clipPosition = ref(50)   // 0-100 slider percent, default middle
  const clipFlip = ref(false)    // flip clipping direction
  const modalOpen = ref(false)
  // 后端计算的装配位置 {component_id: {dz: number, description: string}}
  const assemblyPositions = reactive<Record<string, { dz: number; description: string }>>({})
  const loadingProgress = ref(0)
  const isLoading = ref(false)
  const transformMode = ref<'translate' | 'rotate' | 'scale'>('translate')
  const selectedComponentId = ref<string | null>(null)
  // ── Drag Handle 拖拽编辑 ──
  const handleEditMode = ref(false)
  // 显式标志：下次加载时先清空场景（由 clearAll 设置，供展览馆等全量替换场景使用）
  const clearSceneOnNextLoad = ref(false)
  // 模式隔离：标记当前模型来自哪个模式，跨模式自动清空旧模型
  const sessionSource = ref<'workflow' | 'gallery' | 'vlm' | null>(null)
  // 暂存拖拽产生的参数变更 {componentId: {paramKey: newValue}}
  const pendingParamChanges = reactive<Record<string, Record<string, number>>>({})
  // 渲染模式：simple = 固定颜色, realistic = 参考图真实材质
  const renderMode = ref<'simple' | 'realistic'>('simple')

  const totalModels = computed(() => {
    const ids = new Set([...sessionModelIds.value, ...Object.keys(pendingSTLs)])
    return ids.size
  })

  const modelNames = computed(() => {
    return [...new Set([...sessionModelIds.value, ...Object.keys(pendingSTLs)])]
  })

  const hasPending = computed(() => Object.keys(pendingSTLs).length > 0)
  const hasModels = computed(() => sessionModelIds.value.length > 0)

  function storePendingSTL(componentId: string, url: string, params: Record<string, any>) {
    pendingSTLs[componentId] = { url, params: JSON.parse(JSON.stringify(params)) }
  }

  function clearPending() {
    for (const k of Object.keys(pendingSTLs)) {
      delete pendingSTLs[k]
    }
  }

  function addModel(componentId: string, color: number) {
    if (!sessionModelIds.value.includes(componentId)) {
      sessionModelIds.value.push(componentId)
    }
    modelVisibility[componentId] = true
    modelColors[componentId] = color
  }

  function removeModelMeta(componentId: string) {
    sessionModelIds.value = sessionModelIds.value.filter((id) => id !== componentId)
    delete modelVisibility[componentId]
    delete modelColors[componentId]
  }

  function toggleVisibility(componentId: string) {
    modelVisibility[componentId] = !modelVisibility[componentId]
  }

  function setAssemblyPositions(positions: Record<string, { dz: number; description: string }>) {
    for (const k of Object.keys(assemblyPositions)) delete assemblyPositions[k]
    Object.assign(assemblyPositions, positions)
  }

  function clearAll() {
    sessionModelIds.value = []
    for (const k of Object.keys(modelVisibility)) delete modelVisibility[k]
    for (const k of Object.keys(modelColors)) delete modelColors[k]
    for (const k of Object.keys(pendingSTLs)) delete pendingSTLs[k]
    for (const k of Object.keys(assemblyPositions)) delete assemblyPositions[k]
    clearSceneOnNextLoad.value = true
    sessionSource.value = null
  }

  function toggleAssemblyMode() {
    assemblyMode.value = assemblyMode.value === 'assembled' ? 'exploded' : 'assembled'
  }

  // ── Drag Handle helpers ──

  function storePendingParam(componentId: string, paramKey: string, value: number) {
    if (!pendingParamChanges[componentId]) {
      pendingParamChanges[componentId] = {}
    }
    pendingParamChanges[componentId][paramKey] = value
  }

  function getPendingParams(): Record<string, Record<string, number>> {
    return { ...pendingParamChanges }
  }

  function hasPendingParamChanges(): boolean {
    return Object.keys(pendingParamChanges).length > 0
  }

  function clearPendingParams() {
    for (const k of Object.keys(pendingParamChanges)) {
      delete pendingParamChanges[k]
    }
  }

  return {
    sessionModelIds,
    modelVisibility,
    modelColors,
    pendingSTLs,
    assemblyMode,
    wireframeMode,
    autoRotate,
    clipEnabled,
    clipAxis,
    clipPosition,
    clipFlip,
    modalOpen,
    assemblyPositions,
    loadingProgress,
    isLoading,
    transformMode,
    selectedComponentId,
    totalModels,
    modelNames,
    hasPending,
    hasModels,
    storePendingSTL,
    setAssemblyPositions,
    clearPending,
    addModel,
    removeModelMeta,
    toggleVisibility,
    handleEditMode,
    clearSceneOnNextLoad,
    sessionSource,
    pendingParamChanges,
    clearAll,
    toggleAssemblyMode,
    storePendingParam,
    getPendingParams,
    hasPendingParamChanges,
    clearPendingParams,
    renderMode,
  }
})
