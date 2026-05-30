<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWizardStore, FINE_TUNE_MODULES, CORE_PARAMS } from '@/stores/wizard'
import { useAppStore } from '@/stores/app'
import { useSchemaStore } from '@/stores/schema'
import ParamField from '@/components/param/ParamField.vue'
import type { ParamDef } from '@/api/types'

const { t } = useI18n()
const wizard = useWizardStore()
const appStore = useAppStore()
const schemaStore = useSchemaStore()

// Modules for current component
const modules = computed(() => {
  return FINE_TUNE_MODULES[appStore.componentId || ''] || []
})

// All schema params for current component
const allParams = computed<ParamDef[]>(() => {
  return schemaStore.currentComponent?.params || []
})

// Core keys to exclude from fine-tune
const coreKeySet = computed(() => {
  return new Set(CORE_PARAMS[appStore.componentId || ''] || [])
})

// Params for the currently selected module
const moduleParams = computed<ParamDef[]>(() => {
  const mod = modules.value.find((m) => m.id === wizard.activeModule)
  if (!mod) return []
  return allParams.value.filter((pd) => {
    // Exclude core params
    if (coreKeySet.value.has(pd.k)) return false
    // Match against module patterns
    return mod.paramPatterns.some((pat) => {
      if (pat.endsWith('.')) {
        return pd.k.startsWith(pat)
      }
      return pd.k === pat
    })
  })
})

function onModuleChange(moduleId: string) {
  wizard.setActiveModule(moduleId)
}
</script>

<template>
  <div class="step-finetune">
    <h2 class="sf-title">{{ t('wizard.fineTuneTitle') }}</h2>
    <p class="sf-desc">{{ t('wizard.fineTuneHint') }}</p>

    <!-- Module selector -->
    <div class="sf-module-select">
      <label class="sf-label">{{ t('wizard.selectModule') }}</label>
      <el-select
        :model-value="wizard.activeModule || undefined"
        @update:model-value="(v: string) => onModuleChange(v)"
        :placeholder="t('wizard.modulePlaceholder')"
        size="default"
        style="width: 240px"
      >
        <el-option
          v-for="mod in modules"
          :key="mod.id"
          :value="mod.id"
          :label="t(mod.labelKey)"
        />
      </el-select>
    </div>

    <!-- Module params -->
    <div v-if="wizard.activeModule && moduleParams.length > 0" class="sf-params">
      <ParamField
        v-for="pd in moduleParams"
        :key="pd.k"
        :param-def="pd"
      />
    </div>

    <div v-else-if="wizard.activeModule" class="sf-empty">
      {{ t('wizard.noModuleParams') }}
    </div>

    <div class="sf-nav">
      <el-button @click="wizard.prev()">{{ t('wizard.btnBack') }}</el-button>
      <el-button type="primary" @click="wizard.next()">
        {{ t('wizard.btnGenerate') }}
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.step-finetune {
  max-width: 760px;
  margin: 0 auto;
  padding: 32px 20px;
}

.sf-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 6px;
  color: #1e293b;
}

.sf-desc {
  color: #64748b;
  font-size: 13px;
  margin: 0 0 20px;
}

.sf-module-select {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.sf-label {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  white-space: nowrap;
}

.sf-params {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 28px;
  padding: 16px;
  background: #fafbfc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: visible;
}

.sf-empty {
  color: #94a3b8;
  font-size: 13px;
  padding: 20px;
  text-align: center;
  margin-bottom: 28px;
}

.sf-nav {
  display: flex;
  justify-content: space-between;
}
</style>
