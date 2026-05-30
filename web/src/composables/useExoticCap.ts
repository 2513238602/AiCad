import { ref } from 'vue'
import type { ExoticPreset, ExoticCapGenerateResponse } from '@/api/types'
import { useViewerStore } from '@/stores/viewer'
import * as api from '@/api/client'

const presets = ref<ExoticPreset[]>([])
const loading = ref(false)
const generating = ref(false)
const error = ref('')
const lastResult = ref<ExoticCapGenerateResponse | null>(null)

export function useExoticCap() {
  const viewerStore = useViewerStore()

  async function loadPresets() {
    loading.value = true
    error.value = ''
    try {
      presets.value = await api.fetchExoticPresets()
    } catch (e: any) {
      error.value = String(e)
    } finally {
      loading.value = false
    }
  }

  async function generate(opts: {
    presetId: string
    targetOd?: number
    targetHeight?: number | null
  }) {
    generating.value = true
    error.value = ''
    lastResult.value = null
    try {
      const res = await api.generateExoticCap({
        preset_id: opts.presetId,
        target_od_mm: opts.targetOd,
        target_height_mm: opts.targetHeight,
      })
      lastResult.value = res
      if (res.ok && res.stl_url) {
        // 模式隔离
        if (viewerStore.sessionSource && viewerStore.sessionSource !== 'workflow') {
          viewerStore.clearAll()
        }
        viewerStore.sessionSource = 'workflow'
        viewerStore.storePendingSTL('cap', res.stl_url, res.final_params || {})
        // 装配位置
        if (res.assembly?.positions) {
          viewerStore.setAssemblyPositions(res.assembly.positions)
        }
        viewerStore.modalOpen = true
      } else if (res.error) {
        error.value = res.error
      }
    } catch (e: any) {
      error.value = String(e)
    } finally {
      generating.value = false
    }
  }

  return {
    presets,
    loading,
    generating,
    error,
    lastResult,
    loadPresets,
    generate,
  }
}
