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
  }

  function toggleAssemblyMode() {
    assemblyMode.value = assemblyMode.value === 'assembled' ? 'exploded' : 'assembled'
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
    clearAll,
    toggleAssemblyMode,
  }
})
