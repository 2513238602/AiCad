import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Schema, Product, Component, Preset } from '@/api/types'
import { useAppStore } from './app'

export const useSchemaStore = defineStore('schema', () => {
  const schema = ref<Schema | null>(null)
  const loaded = ref(false)

  function setSchema(s: Schema) {
    schema.value = s
    loaded.value = true
  }

  const products = computed<Product[]>(() => schema.value?.products || [])

  const currentProduct = computed<Product | null>(() => {
    const appStore = useAppStore()
    if (!schema.value || !appStore.productId) return null
    return schema.value.products.find((p) => p.id === appStore.productId) || null
  })

  const currentComponent = computed<Component | null>(() => {
    const appStore = useAppStore()
    const prod = currentProduct.value
    if (!prod || !appStore.componentId) return null
    return prod.components.find((c) => c.id === appStore.componentId) || null
  })

  const currentPreset = computed<Preset | null>(() => {
    const appStore = useAppStore()
    const comp = currentComponent.value
    if (!comp || !appStore.presetId) return null
    return (comp.style_presets || []).find((s) => s.id === appStore.presetId) || null
  })

  return {
    schema,
    loaded,
    products,
    currentProduct,
    currentComponent,
    currentPreset,
    setSchema,
  }
})
