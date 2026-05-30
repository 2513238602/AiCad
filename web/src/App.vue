<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import { useSchemaStore } from '@/stores/schema'
import { useParamsStore } from '@/stores/params'
import { useWizardStore, WizardStep } from '@/stores/wizard'
import { useConstraintSync } from '@/composables/useConstraintSync'
import * as api from '@/api/client'
import AppHeader from '@/components/layout/AppHeader.vue'
import LeftPanel from '@/components/layout/LeftPanel.vue'
import RightPanel from '@/components/layout/RightPanel.vue'
import OutputPanel from '@/components/layout/OutputPanel.vue'
import FailPopup from '@/components/common/FailPopup.vue'
import ViewerModal from '@/components/viewer/ViewerModal.vue'
import WizardNav from '@/components/wizard/WizardNav.vue'
import StepLanding from '@/components/wizard/StepLanding.vue'
import StepProduct from '@/components/wizard/StepProduct.vue'
import StepComponent from '@/components/wizard/StepComponent.vue'
import StepCoreParams from '@/components/wizard/StepCoreParams.vue'
import StepChoice from '@/components/wizard/StepChoice.vue'
import StepFineTune from '@/components/wizard/StepFineTune.vue'
import StepGenerate from '@/components/wizard/StepGenerate.vue'
import StepImageImport from '@/components/wizard/StepImageImport.vue'
import GalleryPage from '@/components/gallery/GalleryPage.vue'
import ShowroomPage from '@/components/showroom/ShowroomPage.vue'

const appStore = useAppStore()
const schemaStore = useSchemaStore()
const paramsStore = useParamsStore()
const wizard = useWizardStore()

// Watch componentId changes → immediately fetch & apply cross-component constraints
useConstraintSync()

onMounted(async () => {
  const urlMode = new URLSearchParams(window.location.search).get('mode')
  if (urlMode === 'wizard' || urlMode === 'classic' || urlMode === 'gallery' || urlMode === 'showroom') {
    wizard.setMode(urlMode)
  }

  // Load schema
  const schema = await api.fetchSchema()
  schemaStore.setSchema(schema)

  // Set initial selections (for classic mode or wizard fallback)
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
  <!-- Gallery mode -->
  <template v-if="wizard.appMode === 'gallery'">
    <div class="wrap">
      <AppHeader />
      <GalleryPage />
    </div>
  </template>

  <!-- Virtual showroom mode -->
  <template v-else-if="wizard.appMode === 'showroom'">
    <div class="wrap showroom-wrap">
      <AppHeader />
      <ShowroomPage />
    </div>
  </template>

  <!-- Wizard mode -->
  <template v-else-if="wizard.appMode === 'wizard'">
    <div class="wrap">
      <AppHeader />
      <WizardNav />
      <div class="wizard-content">
        <StepLanding v-if="wizard.currentStep === WizardStep.Landing" />
        <StepProduct v-else-if="wizard.currentStep === WizardStep.Product" />
        <StepComponent v-else-if="wizard.currentStep === WizardStep.Component" />
        <StepCoreParams v-else-if="wizard.currentStep === WizardStep.CoreParams" />
        <StepChoice v-else-if="wizard.currentStep === WizardStep.Choice" />
        <StepFineTune v-else-if="wizard.currentStep === WizardStep.FineTune" />
        <StepGenerate v-else-if="wizard.currentStep === WizardStep.Generate" />
        <StepImageImport v-else-if="wizard.currentStep === WizardStep.ImageImport" />
      </div>
    </div>
  </template>

  <!-- Classic mode -->
  <template v-else>
    <div class="wrap">
      <AppHeader />
      <div class="grid">
        <LeftPanel />
        <RightPanel />
      </div>
      <OutputPanel />
    </div>
  </template>

  <FailPopup />
  <ViewerModal />
</template>

<style scoped>
.wizard-content {
  min-height: 460px;
}

.showroom-wrap {
  max-width: none;
  padding-left: 18px;
  padding-right: 18px;
}
</style>
