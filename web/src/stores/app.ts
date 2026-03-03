import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { GenerateResponse } from '@/api/types'

export const useAppStore = defineStore('app', () => {
  const productId = ref<string | null>(null)
  const componentId = ref<string | null>(null)
  const presetId = ref<string | null>(null)
  const autoGenerate = ref(false)
  const filterText = ref('')
  const generating = ref(false)
  const genMessage = ref('')
  const genMessageIsError = ref(false)
  const lastResponse = ref<GenerateResponse | null>(null)

  function setProduct(id: string) {
    productId.value = id
  }

  function setComponent(id: string) {
    componentId.value = id
    presetId.value = null
  }

  function setPreset(id: string | null) {
    presetId.value = id
  }

  function setGenerating(val: boolean) {
    generating.value = val
  }

  function setGenMessage(msg: string, isError = false) {
    genMessage.value = msg
    genMessageIsError.value = isError
  }

  function setLastResponse(res: GenerateResponse | null) {
    lastResponse.value = res
  }

  return {
    productId,
    componentId,
    presetId,
    autoGenerate,
    filterText,
    generating,
    genMessage,
    genMessageIsError,
    lastResponse,
    setProduct,
    setComponent,
    setPreset,
    setGenerating,
    setGenMessage,
    setLastResponse,
  }
})
