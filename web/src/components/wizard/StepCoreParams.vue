<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWizardStore, CORE_PARAMS } from '@/stores/wizard'
import { useAppStore } from '@/stores/app'
import { useSchemaStore } from '@/stores/schema'
import { useParamsStore } from '@/stores/params'
import ParamField from '@/components/param/ParamField.vue'
import type { ParamDef } from '@/api/types'

const { t } = useI18n()
const wizard = useWizardStore()
const appStore = useAppStore()
const schemaStore = useSchemaStore()
const paramsStore = useParamsStore()

function tName(name: string) {
  return t(`names.${name}`, name)
}

// Get the core param keys for the current component
const coreKeys = computed(() => {
  return CORE_PARAMS[appStore.componentId || ''] || []
})

// Filter schema params to only core ones
const coreParamDefs = computed<ParamDef[]>(() => {
  const comp = schemaStore.currentComponent
  if (!comp) return []
  const keys = new Set(coreKeys.value)
  return comp.params.filter((pd) => keys.has(pd.k))
})

// Presets for current component
const presets = computed(() => {
  return schemaStore.currentComponent?.style_presets || []
})

function onPresetChange(presetId: string) {
  const preset = presets.value.find((p) => p.id === presetId)
  if (preset) {
    appStore.setPreset(presetId)
    paramsStore.setFromPreset(preset.params)
  }
}
</script>

<template>
  <div class="step-core">
    <h2 class="scp-title">{{ t('wizard.setCoreParams') }}</h2>
    <p class="scp-subtitle">
      {{ t('wizard.coreParamsHint') }}
    </p>

    <!-- Preset selector -->
    <div v-if="presets.length > 0" class="scp-preset">
      <label class="scp-label">{{ t('ui.labelPreset') }}</label>
      <el-select
        :model-value="appStore.presetId || undefined"
        @update:model-value="(v: string) => onPresetChange(v)"
        size="default"
        style="width: 260px"
      >
        <el-option
          v-for="p in presets"
          :key="p.id"
          :value="p.id"
          :label="tName(p.name)"
        />
      </el-select>
    </div>

    <!-- Core params -->
    <div class="scp-params">
      <ParamField
        v-for="pd in coreParamDefs"
        :key="pd.k"
        :param-def="pd"
      />
    </div>

    <div class="scp-nav">
      <el-button @click="wizard.prev()">{{ t('wizard.btnBack') }}</el-button>
      <el-button type="primary" @click="wizard.next()">{{ t('wizard.btnNext') }}</el-button>
    </div>
  </div>
</template>

<style scoped>
.step-core {
  max-width: 500px;
  margin: 0 auto;
  padding: 32px 20px;
}

.scp-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 6px;
  color: #1e293b;
}

.scp-subtitle {
  color: #64748b;
  font-size: 13px;
  margin: 0 0 24px;
}

.scp-preset {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f1f5f9;
}

.scp-label {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  white-space: nowrap;
}

.scp-params {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 28px;
}

.scp-nav {
  display: flex;
  justify-content: space-between;
}
</style>
