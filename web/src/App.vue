<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import { useSchemaStore } from '@/stores/schema'
import { useParamsStore } from '@/stores/params'
import * as api from '@/api/client'
import AppHeader from '@/components/layout/AppHeader.vue'
import LeftPanel from '@/components/layout/LeftPanel.vue'
import RightPanel from '@/components/layout/RightPanel.vue'
import OutputPanel from '@/components/layout/OutputPanel.vue'
import FailPopup from '@/components/common/FailPopup.vue'
import ViewerModal from '@/components/viewer/ViewerModal.vue'

const appStore = useAppStore()
const schemaStore = useSchemaStore()
const paramsStore = useParamsStore()

onMounted(async () => {
  // Load schema
  const schema = await api.fetchSchema()
  schemaStore.setSchema(schema)

  // Set initial selections
  if (schema.products.length > 0) {
    const prod = schema.products[0]
    appStore.setProduct(prod.id)
    if (prod.components.length > 0) {
      const comp = prod.components[0]
      appStore.setComponent(comp.id)
      if (comp.style_presets && comp.style_presets.length > 0) {
        appStore.setPreset(comp.style_presets[0].id)
        paramsStore.setFromPreset(comp.style_presets[0].params)
      }
    }
  }

  // Clear backend state on page load (prevent ghost constraints)
  try {
    await api.deleteAllGenerated()
  } catch {}
})
</script>

<template>
  <div class="wrap">
    <AppHeader />
    <div class="grid">
      <LeftPanel />
      <RightPanel />
    </div>
    <OutputPanel />
  </div>
  <FailPopup />
  <ViewerModal />
</template>
